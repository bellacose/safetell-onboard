# Hand-off formats (SafeTell Onboard → SafeTell)

SafeTell validates everything again on import; these files only have to be in its formats.

| File | SafeTell screen | Format |
|---|---|---|
| `SafeTell-Onboarding-Workbook_<customer>.xlsx` | Onboarding → upload workbook (`import_onboarding_workbook`) | SafeTell's template (`public/templates/SafeTell-Onboarding-Workbook.xlsx`, contract in `docs/onboarding-workbook.md` in the SafeTell repo). Company and Contractors tabs are pre-filled. Contractors with no email get "Send invitation now? = N". |
| `history_corrective_actions.xlsx`, `history_injuries.xlsx`, `history_hours.xlsx` (and `history_permits.xlsx` later) | Onboarding → Import history (`import_history`) | One sheet per section. The headers are SafeTell's field labels, so its column matching maps every column automatically (tested with SafeTell's `src/lib/historyImport.ts`). |
| `checklist_<name>.xlsx` | Inspection templates → Import Excel | Columns: Category, Category Weight, Question, Severity, Points, Requirement Code, Life Critical. Only the life-critical items a person confirmed are marked Yes (and critical). |
| `requirements.json` | *Not yet in SafeTell* | A list of `{layer: company\|project, project_code, source_title, paragraph_ref, source_citation, title, requirement_text, category, high_risk, quote, quote_verified}`. SafeTell needs a plain `import_requirements(org, payload, dry_run)` that creates a requirement plus version 1 per row, in the company layer or pinned to the project. |
