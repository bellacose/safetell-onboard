"""Deterministic numbered-paragraph splitter (no AI).

Ported from SafeTell's supabase/functions/_shared/paragraphs.ts so both apps cut a
document the same way, with two fixes found in the Brightwater run:
  * CSI MasterFormat sections ("SECTION 01 35 23") keep their full number, and in a
    document with several sections the paragraph refs are prefixed with it
    ("01 35 13.13 1.3.A") instead of getting "(2)" suffixes.
  * A table fragment such as "3.0 or less" does not open a paragraph.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field

NUM = re.compile(r'^(\d{1,3}(?:\.\d{1,3})+)\.?\s+(?=\S)')
NUMLET = re.compile(r'^(\d{1,3}(?:\.\d{1,3})*\.[A-Z])[.)]?\s+(?=\S)')
TOP = re.compile(r'^(\d{1,3})[.)]\s+(?=\S)')
TOPBARE = re.compile(r'^(\d{1,3})\s+(?=[A-Z][A-Z&/\- ]{2,})')
CSI = re.compile(r'^SECTION\s+(\d{2}\s\d{2}\s\d{2}(?:\.\d{2})?)\b\s*[.:\-–—]?\s*', re.I)
SECTION = re.compile(r'^(Section|Article|Part|Chapter)\s+(\d{1,3}[A-Za-z]?(?:\.\d{1,3})*)\b\s*[.:\-–—]?\s*', re.I)
LETTER = re.compile(r'^([A-Z])[.)]\s+(?=\S)')
PAREN = re.compile(r'^\(([a-z]|[ivx]{1,4}|\d{1,2})\)\s+(?=\S)')
END_OF_SECTION = re.compile(r'^END OF SECTION\b', re.I)
CONTINUATION = re.compile(r'^\d[\d.]*\s+[a-z]')  # "3.0 or less": real numbered paragraphs start with a capital


@dataclass
class Paragraph:
    ref: str
    text: str
    start: int
    end: int
    heading: bool = False
    body_start: int = field(default=0, repr=False)

    def as_dict(self):
        d = {'ref': self.ref, 'text': self.text, 'start': self.start, 'end': self.end}
        if self.heading:
            d['heading'] = True
        return d


def _is_heading(body: str) -> bool:
    t = body.strip()
    if not t:
        return True
    if len(t) > 90 or re.search(r'[.;:]$', t):
        return False
    return t == t.upper() or len(t.split()) <= 8


def split_paragraphs(text: str) -> list[dict]:
    out: list[Paragraph] = []
    cur: Paragraph | None = None
    base = ''
    letter_ctx = ''
    last_top = 0
    last_sub = 0
    csi = ''            # current CSI section number, if any
    seen: dict[str, int] = {}

    def open_(ref, line_start, body_start, line_end):
        nonlocal cur
        if cur:
            out.append(cur)
        n = seen.get(ref, 0) + 1
        seen[ref] = n
        cur = Paragraph(ref=f'{ref} ({n})' if n > 1 else ref, text='', start=line_start, end=line_end, body_start=body_start)

    def plausible_top(n):
        return last_top == 0 or (last_top <= n <= last_top + 5)

    def scoped(ref):
        return f'{csi} {ref}' if csi else ref

    pos = 0
    for raw in text.split('\n'):
        line_start, line_end = pos, pos + len(raw)
        pos = line_end + 1
        lead = len(raw) - len(raw.lstrip())
        line = raw.strip()
        if not line:
            continue
        s0 = line_start + lead
        if END_OF_SECTION.match(line):
            if cur:
                out.append(cur)
                cur = None
            continue
        m = CSI.match(line)
        if m:
            csi = m.group(1)
            base, letter_ctx, last_sub, last_top = csi, '', 0, 0
            open_(f'Section {csi}', s0, s0 + m.end(), line_end)
            continue
        m = SECTION.match(line)
        if m:
            ref = f'{m.group(1)[0].upper()}{m.group(1)[1:].lower()} {m.group(2)}'
            base, letter_ctx, last_sub = ref, '', 0
            open_(scoped(ref), s0, s0 + m.end(), line_end)
            continue
        m = NUMLET.match(line)
        if m:
            letter_ctx, last_sub = m.group(1), 0
            open_(scoped(m.group(1)), s0, s0 + m.end(), line_end)
            continue
        m = NUM.match(line)
        if m and plausible_top(int(m.group(1).split('.')[0])) and not CONTINUATION.match(line):
            base, letter_ctx, last_sub = m.group(1), '', 0
            last_top = int(m.group(1).split('.')[0])
            open_(scoped(m.group(1)), s0, s0 + m.end(), line_end)
            continue
        m = TOP.match(line)
        if m and int(m.group(1)) <= 200:
            n = int(m.group(1))
            if letter_ctx and (n == last_sub + 1 or n == 1) and not (n == last_top + 1 and n != last_sub + 1):
                last_sub = n
                open_(scoped(f'{letter_ctx}.{n}'), s0, s0 + m.end(), line_end)
            elif plausible_top(n) and n != last_top:
                base, letter_ctx, last_sub, last_top = str(n), '', 0, n
                open_(scoped(str(n)), s0, s0 + m.end(), line_end)
            elif cur:
                cur.end = line_end
            continue
        m = TOPBARE.match(line)
        if m and int(m.group(1)) <= 200 and (last_top == 0 or int(m.group(1)) == last_top + 1):
            base, letter_ctx, last_sub, last_top = m.group(1), '', 0, int(m.group(1))
            open_(scoped(m.group(1)), s0, s0 + m.end(), line_end)
            continue
        m = LETTER.match(line) if base else None
        if m:
            letter_ctx, last_sub = f'{base}.{m.group(1)}', 0
            open_(scoped(letter_ctx), s0, s0 + m.end(), line_end)
            continue
        m = PAREN.match(line) if cur else None
        if m:
            owner = re.sub(r'\([a-z0-9ivx]+\)$', '', re.sub(r' \(\d+\)$', '', cur.ref))
            open_(f'{owner}({m.group(1)})', s0, s0 + m.end(), line_end)
            continue
        if cur:
            cur.end = line_end
    if cur:
        out.append(cur)

    # Only prefix refs with the CSI number when the document has more than one CSI section.
    sections = [p.ref for p in out if p.ref.startswith('Section ') and re.match(r'Section \d{2} \d{2} \d{2}', p.ref)]
    result = []
    for p in out:
        body = text[p.body_start:p.end]
        body = re.sub(r'[ \t]+', ' ', body)
        body = re.sub(r'\s*\n\s*', '\n', body).strip()
        ref = p.ref
        if len(sections) <= 1:
            ref = re.sub(r'^\d{2} \d{2} \d{2}(?:\.\d{2})? ', '', ref)
        result.append(Paragraph(ref=ref, text=body, start=p.start, end=p.end, heading=_is_heading(body)).as_dict())
    return result
