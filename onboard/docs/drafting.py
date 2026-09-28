"""THE replaceable AI step: numbered paragraphs in, one draft per obligation out.

The prompt is SafeTell's extract-requirements prompt (supabase/functions/extract-requirements/draft.ts),
which found 61/61 manual rules and 14/14 spec rules in the Brightwater blind test. Providers:
  anthropic   ANTHROPIC_API_KEY, model ONBOARD_AI_MODEL (default claude-haiku-4-5-20251001)
  openrouter  OPENROUTER_API_KEY, model ONBOARD_AI_MODEL (e.g. openai/gpt-4.1-mini)
  replay      a JSON file of drafts (tests, or drafts made elsewhere)
Everything the AI returns is checked afterwards (verify.py) and a person approves every draft.
"""
from __future__ import annotations
import json, os, re

CATEGORIES = ["program", "prequalification", "insurance", "orientation_training", "inspection", "corrective_action", "escalation",
              "contractor_evaluation", "submittals", "permits", "fall_protection", "excavation", "crane_rigging", "electrical_loto",
              "hot_work", "confined_space", "health_hazards", "ppe", "fire_protection", "infection_control", "environmental",
              "emergency", "incident_reporting", "general"]

KIND_TEXT = {'company_manual': "the general contractor's company safety manual",
             'owner_spec': "a project owner's safety specification"}


def build_prompt(kind: str, title: str) -> str:
    return f"""You turn a construction safety document into requirements for a contractor-safety system.
Document: "{title}" ({KIND_TEXT.get(kind, 'a safety document')}).

You get a JSON list of numbered paragraphs {{ref, text}}. Return one draft for EVERY paragraph that states an obligation, rule, limit, threshold or required action — for anyone (contractors, the GC's staff, reviewers, the company itself).

These ARE requirements and must not be skipped:
- safety program requirements (written programs, plans, competent persons)
- prequalification rules and thresholds (EMR, TRIR, DART, citations, approval / escalation criteria)
- insurance minimums and certificate rules
- orientation and training rules
- inspection and audit frequencies
- corrective-action rules (classes, days to correct, stop-work)
- escalation rules (who is notified, when)
- contractor evaluation, scoring, tier and performance rules
- permit, submittal and notice rules

These are NOT requirements (return nothing for them): definitions, purpose / scope statements, headings, references lists, revision history, boilerplate.

For each draft:
- paragraph_ref: exactly the ref you were given. One paragraph may yield more than one draft only if it states clearly separate obligations.
- title: short (max ~8 words).
- requirement_text: the obligation in one or two plain sentences. Keep every number, unit and limit exactly as written; do not add numbers that are not in the paragraph.
- category: one of {', '.join(CATEGORIES)}.
- high_risk: true for life-critical work (falls, excavation, cranes/critical lifts, energized electrical, confined space, hot work) or knock-out thresholds.
- suggested_layer: "company" if it applies across all projects, "project" if specific to one project/site/owner.
- quote: copy an exact, contiguous, character-for-character substring of the paragraph text (10-40 words) that supports the draft. Do NOT paraphrase, fix typos, reorder or join separate parts. If unsure, copy a shorter exact piece.

Answer with JSON only: {{"drafts": [ ... ]}}"""


def _parse(text: str) -> list[dict]:
    m = re.search(r'\{.*\}', text, re.S)
    data = json.loads(m.group(0) if m else text)
    return data.get('drafts', [])


def draft_requirements(paragraphs: list[dict], kind: str, title: str, provider: str | None = None, replay_path: str | None = None) -> list[dict]:
    provider = provider or os.environ.get('ONBOARD_AI_PROVIDER', 'anthropic')
    paras = [{'ref': p['ref'], 'text': p['text']} for p in paragraphs if not p.get('heading')]
    if not paras:
        return []
    if provider == 'replay':
        return _parse(open(replay_path).read())
    system, user = build_prompt(kind, title), json.dumps(paras)
    if provider == 'anthropic':
        import anthropic
        client = anthropic.Anthropic()
        msg = client.messages.create(model=os.environ.get('ONBOARD_AI_MODEL', 'claude-haiku-4-5-20251001'), max_tokens=16000,
                                     system=system, messages=[{'role': 'user', 'content': user}])
        return _parse(''.join(b.text for b in msg.content if b.type == 'text'))
    if provider == 'openrouter':
        import urllib.request
        req = urllib.request.Request('https://openrouter.ai/api/v1/chat/completions', method='POST',
            headers={'Authorization': f"Bearer {os.environ['OPENROUTER_API_KEY']}", 'Content-Type': 'application/json'},
            data=json.dumps({'model': os.environ.get('ONBOARD_AI_MODEL', 'openai/gpt-4.1-mini'), 'response_format': {'type': 'json_object'},
                             'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}]}).encode())
        with urllib.request.urlopen(req, timeout=600) as r:
            return _parse(json.load(r)['choices'][0]['message']['content'])
    raise ValueError(f'Unknown AI provider {provider}')
