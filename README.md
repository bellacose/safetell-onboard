# SafeTell Onboard

The workbench our team uses to **assess a new SafeTell customer and prepare their data** for SafeTell. It is a separate app on purpose: SafeTell stays clean of import prep and AI reading, and only runs its own strict importers on the clean files this app produces.

Customers never log in here. Nothing here writes to SafeTell's database.

## What it does

| Step | Screen | What happens |
|---|---|---|
| 1 | Assessment | Forms A–C answers (from the prospect or loaded from JSON). Form B is scored with its own rules: B1–B4, composite, rank R1–R4, required tier, the evidence set for Form C, priority routing flags and automatic P1 gaps. |
| 2 | Files | Everything the customer sent, stored as sent. Each file is tagged with its type and Form C ref, plus a **"do not send to AI"** flag when the customer asks for it. |
| 3 | Manuals & specs | A .docx/.pdf is split into numbered paragraphs by rules (no AI), the AI drafts requirements, and every quote and number is checked against its paragraph. A person accepts, edits or rejects each draft, or skips the paragraph with a reason. The review can't close while any paragraph is uncovered. |
| 4 | Spreadsheets | Their vendor list, corrective-action log, injury log, man-hours and inspection form. The app finds the real header row and maps their columns to ours for a person to confirm. It also flags duplicate vendors and suggests life-critical checklist items from their list. |
| 5 | Package | A zip in SafeTell's import formats: the pre-filled Onboarding Workbook, one history sheet per section (columns named exactly as SafeTell's Import history screen expects), a checklist in SafeTell's template format, and `requirements.json`. |

The Brightwater mock customer is the test suite (`tests/`). Its package imports into a copy of SafeTell's database with zero errors.

## Run it

```bash
pip install -r requirements.txt
python scripts/demo_brightwater.py      # optional: loads the mock customer
ONBOARD_PASSWORD=choose-one ANTHROPIC_API_KEY=... python wsgi.py   # http://localhost:5055
python -m pytest -q
```

Docker: `docker build -t safetell-onboard . && docker run -p 5055:5055 -v onboard-data:/data -e ONBOARD_PASSWORD=... -e ANTHROPIC_API_KEY=... safetell-onboard`

| Setting | Meaning |
|---|---|
| `ONBOARD_PASSWORD` | Team password (no password = open, local use only) |
| `ONBOARD_SECRET` | Session secret |
| `ONBOARD_DATA` | Where the database and uploaded files live (default `./data`) |
| `ONBOARD_AI_PROVIDER` | `anthropic` (default) or `openrouter` |
| `ANTHROPIC_API_KEY` / `OPENROUTER_API_KEY` | Key for the provider |
| `ONBOARD_AI_MODEL` | Model name for the provider |

## Data handling

- Only the numbered paragraphs of a manual or spec are sent to the AI. Logs, injuries, hours, contacts and certificates never are.
- A file marked "do not send to AI" can't be sent at all.
- Uploaded files stay in `ONBOARD_DATA`.

## Still to build

- Forms D and E: the consultant's analysis and the gap register/plan.
- The customer-facing prospect link for Forms A–C.
- Permit transcription from owner PDFs.
- Loading `requirements.json` into SafeTell. SafeTell needs a plain requirements import for that; see `docs/handoff-format.md`.
