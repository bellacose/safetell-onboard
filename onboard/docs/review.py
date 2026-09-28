"""Turning a manual or spec into reviewed requirements. The rules match SafeTell's:
every numbered paragraph must end up Accepted or Skipped (with a reason) before the review
can close, quotes and numbers are checked here rather than trusted, and an unverified quote
needs a replacement or an explicit "accept without a verified quote"."""
from __future__ import annotations
from ..models import Draft, Skip, SourceDocument, Upload
from .drafting import draft_requirements
from .extract import extract_text
from .paragraphs import split_paragraphs
from .verify import quote_verified, unmatched_numbers


class ReviewError(Exception):
    pass


def paragraph_text(doc: SourceDocument, ref: str) -> str | None:
    return next((p['text'] for p in doc.paragraphs if p['ref'] == ref), None)


def create_document(session, engagement, upload: Upload, data: bytes, title: str, project_code: str | None = None) -> SourceDocument:
    if upload.kind not in ('company_manual', 'owner_spec'):
        raise ReviewError('Only a company manual or an owner spec can be reviewed into requirements')
    text = extract_text(upload.filename, data)
    doc = SourceDocument(engagement=engagement, upload_id=upload.id, kind=upload.kind, title=title, project_code=project_code,
                         text=text, paragraphs=split_paragraphs(text))
    session.add(doc)
    return doc


def _check(doc: SourceDocument, d: Draft):
    pt = paragraph_text(doc, d.paragraph_ref)
    if pt is None:
        raise ReviewError(f'Paragraph "{d.paragraph_ref}" is not in this document')
    d.quote_verified = quote_verified(d.quote, pt)
    d.unmatched_numbers = unmatched_numbers(d.requirement_text, pt)


def add_draft(session, doc: SourceDocument, *, paragraph_ref, title, requirement_text, category=None, high_risk=False, quote=None, origin='manual') -> Draft:
    if doc.review_complete:
        raise ReviewError('This review is complete - reopen it to change drafts')
    if not title.strip() or not requirement_text.strip():
        raise ReviewError('A draft needs a title and requirement text')
    if paragraph_text(doc, paragraph_ref) is None:
        raise ReviewError(f'Paragraph "{paragraph_ref}" is not in this document')
    d = Draft(paragraph_ref=paragraph_ref, title=title.strip(), requirement_text=requirement_text.strip(),
              category=category, high_risk=bool(high_risk), quote=quote, origin=origin, status='pending', accepted_without_quote=False)
    d.document = doc
    _check(doc, d)
    session.add(d)
    return d


def run_ai(session, doc: SourceDocument, upload: Upload | None, provider=None, replay_path=None) -> dict:
    """Ask the AI for drafts. Refused when the customer said this file must not go to AI."""
    if upload is not None and upload.no_ai:
        raise ReviewError('The customer asked that this document is not sent to AI - draft it by hand')
    if doc.review_complete:
        raise ReviewError('This review is complete - reopen it first')
    if any(d.origin == 'ai' for d in doc.drafts):
        raise ReviewError('AI drafts already exist for this document - review those (re-running would duplicate them)')
    drafts = draft_requirements(doc.paragraphs, doc.kind, doc.title, provider=provider, replay_path=replay_path)
    doc.ai_provider = provider or 'default'
    added, rejected = 0, []
    for x in drafts:
        try:
            add_draft(session, doc, paragraph_ref=x['paragraph_ref'], title=x.get('title', ''), requirement_text=x.get('requirement_text', ''),
                      category=x.get('category'), high_risk=x.get('high_risk', False), quote=x.get('quote'), origin='ai')
            added += 1
        except ReviewError as e:
            rejected.append({'ref': x.get('paragraph_ref'), 'error': str(e)})
    return {'added': added, 'rejected': rejected}


def skip_paragraph(session, doc, ref, reason):
    if doc.review_complete:
        raise ReviewError('This review is complete - reopen it first')
    if not reason or not reason.strip():
        raise ReviewError('Say why this paragraph is not a requirement')
    if paragraph_text(doc, ref) is None:
        raise ReviewError(f'Paragraph "{ref}" is not in this document')
    existing = next((s for s in doc.skips if s.paragraph_ref == ref), None)
    if existing:
        existing.reason = reason.strip()
    else:
        session.add(Skip(document=doc, paragraph_ref=ref, reason=reason.strip()))


def unskip(session, doc, ref):
    for s in list(doc.skips):
        if s.paragraph_ref == ref:
            doc.skips.remove(s)
            session.delete(s)


def decide(session, d: Draft, action: str, *, note=None, title=None, requirement_text=None, high_risk=None, category=None, quote=None, without_quote=False):
    doc = d.document
    if doc.review_complete:
        raise ReviewError('This review is complete - reopen it to change drafts')
    if action == 'reject':
        if not (note or '').strip():
            raise ReviewError('Rejecting a draft needs a reason')
        d.status, d.note = 'rejected', note.strip()
        return
    if action != 'accept':
        raise ReviewError(f'Unknown action {action}')
    if title is not None: d.title = title.strip()
    if requirement_text is not None: d.requirement_text = requirement_text.strip()
    if high_risk is not None: d.high_risk = bool(high_risk)
    if category is not None: d.category = category
    if quote is not None: d.quote = quote
    _check(doc, d)
    if not d.quote_verified and not without_quote:
        raise ReviewError(f'Quote not found in paragraph {d.paragraph_ref} - pick a quote from the paragraph or accept without a verified quote')
    d.accepted_without_quote = not d.quote_verified
    d.status = 'accepted'


def accept_all_verified(session, doc: SourceDocument) -> int:
    """Bulk-accept pending drafts whose quote was found in the paragraph and whose numbers all
    appear there. Everything else stays pending for a person to look at."""
    n = 0
    for d in doc.drafts:
        if d.status == 'pending' and d.quote_verified and not d.unmatched_numbers:
            decide(session, d, 'accept'); n += 1
    return n


def coverage(doc: SourceDocument) -> dict:
    states = {}
    skipped = {s.paragraph_ref: s.reason for s in doc.skips}
    for p in doc.paragraphs:
        if p.get('heading'):
            states[p['ref']] = 'heading'; continue
        ds = [d for d in doc.drafts if d.paragraph_ref == p['ref'] and d.status != 'rejected']
        if any(d.status == 'accepted' for d in ds): states[p['ref']] = 'accepted'
        elif ds: states[p['ref']] = 'draft'
        elif p['ref'] in skipped: states[p['ref']] = 'skipped'
        else: states[p['ref']] = 'not_covered'
    vals = list(states.values())
    return {'states': states, 'paragraphs': sum(v != 'heading' for v in vals), 'accepted': vals.count('accepted'), 'draft': vals.count('draft'),
            'skipped': vals.count('skipped'), 'not_covered': vals.count('not_covered'),
            'pending_drafts': sum(d.status == 'pending' for d in doc.drafts),
            'unverified_quotes': sum(not d.quote_verified and d.status != 'rejected' for d in doc.drafts),
            'accepted_without_quote': sum(d.accepted_without_quote for d in doc.drafts if d.status == 'accepted'),
            'number_flags': sum(bool(d.unmatched_numbers) and d.status != 'rejected' for d in doc.drafts)}


def complete_review(doc: SourceDocument):
    c = coverage(doc)
    if c['not_covered']:
        raise ReviewError(f"{c['not_covered']} numbered paragraph(s) are not covered - draft a requirement or mark them as not a requirement first")
    if c['pending_drafts']:
        raise ReviewError(f"{c['pending_drafts']} draft(s) still need a decision")
    doc.review_complete = True


def reopen(doc: SourceDocument):
    doc.review_complete = False


def export_requirements(doc: SourceDocument) -> list[dict]:
    """Accepted requirements in the hand-off format (docs/handoff-format.md)."""
    if not doc.review_complete:
        raise ReviewError('Finish the review before exporting')
    out = []
    for d in doc.drafts:
        if d.status != 'accepted':
            continue
        out.append({'layer': 'company' if doc.kind == 'company_manual' else 'project', 'project_code': doc.project_code,
                    'source_title': doc.title, 'paragraph_ref': d.paragraph_ref, 'source_citation': f'{doc.title} {d.paragraph_ref}',
                    'title': d.title, 'requirement_text': d.requirement_text, 'category': d.category, 'high_risk': d.high_risk,
                    'quote': d.quote, 'quote_verified': d.quote_verified})
    return out
