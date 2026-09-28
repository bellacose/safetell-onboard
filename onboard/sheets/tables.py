"""Reading a customer's own spreadsheet: find the real header row, map their columns to
ours, and turn rows into records. No AI - every mapping is shown to a person to confirm."""
from __future__ import annotations
import csv, datetime as dt, io, re

# Target tables. Each field: key, label, required, header hints (normalized).
TARGETS: dict[str, dict] = {
    'contractors': {'label': 'Vendor / subcontractor list', 'fields': [
        ('company', 'Company legal name', True, ['company', 'company name', 'vendor', 'subcontractor', 'legal name', 'name']),
        ('trade', 'Trade', False, ['trade', 'trade csi', 'scope', 'csi']),
        ('contact_name', 'Contact name', False, ['contact', 'contact name', 'primary contact']),
        ('contact_email', 'Contact email', False, ['e mail', 'email', 'contact email']),
        ('phone', 'Phone', False, ['phone', 'telephone', 'tel']),
        ('city', 'City', False, ['city']),
        ('state', 'State', False, ['state', 'st']),
        ('emr', 'EMR', False, ['emr', 'mod rate', 'experience mod']),
        ('notes', 'Notes', False, ['notes', 'comments'])]},
    'corrective_actions': {'label': 'Corrective action log', 'fields': [
        ('ref', 'Their reference', True, ['ca', 'ca #', 'ref', 'no', 'number', 'id', 'item']),
        ('found_date', 'Date found', True, ['date found', 'date', 'found', 'date identified', 'opened']),
        ('contractor', 'Contractor', True, ['subcontractor', 'contractor', 'company', 'responsible']),
        ('location', 'Location', False, ['area location', 'location', 'area']),
        ('description', 'Description', True, ['deficiency', 'description', 'finding', 'issue', 'observation']),
        ('class', 'Class / severity', True, ['class', 'severity', 'classification', 'priority']),
        ('due_date', 'Due date', True, ['due', 'due date', 'correct by']),
        ('status', 'Status', True, ['status', 'open closed']),
        ('closed_date', 'Closed date', False, ['date closed', 'closed', 'closed date', 'completed']),
        ('package_code', 'Package code', False, ['package', 'work package', 'phase'])]},
    'injuries': {'label': 'Injury log', 'fields': [
        ('case_ref', 'Case number', True, ['case', 'case #', 'case no', 'case number']),
        ('date', 'Date', True, ['date', 'date of injury', 'injury date']),
        ('employer', 'Employer', True, ['employer', 'company', 'subcontractor', 'contractor']),
        ('employee', 'Employee', False, ['employee', 'name', 'employee name']),
        ('job_title', 'Job title', False, ['job title', 'title', 'occupation', 'trade']),
        ('description', 'Description', True, ['description', 'injury', 'what happened']),
        ('classification', 'Classification', True, ['classification', 'class', 'type', 'outcome']),
        ('days_away', 'Days away', False, ['days away', 'lost days', 'days away from work']),
        ('days_restricted', 'Days restricted', False, ['days restricted', 'restricted days', 'days on restriction'])]},
    'hours': {'label': 'Man-hours', 'fields': [
        ('contractor', 'Contractor', True, ['subcontractor', 'contractor', 'company', 'employer']),
        ('month', 'Month', True, ['month', 'period']),
        ('hours', 'Hours', True, ['hours', 'man hours', 'manhours', 'hours worked'])]},
    'checklist': {'label': 'Inspection checklist', 'fields': [
        ('text', 'Item text', True, ['item', 'question', 'description', 'checklist item', 'requirement', 'check']),
        ('section', 'Section / category', False, ['category', 'section', 'group', 'area']),
        ('critical', 'Critical flag', False, ['critical', 'life critical', 'life-critical', 'crit']),
        ('severity', 'Severity', False, ['severity', 'risk'])]},
}


def norm(s) -> str:
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9#]+', ' ', str(s or '').lower())).strip()


def cell(v):
    if isinstance(v, dt.datetime): return v.strftime('%Y-%m-%d')
    if isinstance(v, dt.date): return v.isoformat()
    if isinstance(v, float) and v.is_integer(): return str(int(v))
    return '' if v is None else str(v).strip()


def read_sheets(filename: str, data: bytes) -> dict[str, list[list[str]]]:
    """All sheets as grids of strings."""
    if filename.lower().endswith('.csv'):
        return {'Sheet1': [[c.strip() for c in r] for r in csv.reader(io.StringIO(data.decode('utf-8-sig', errors='replace')))]}
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    return {ws.title: [[cell(v) for v in row] for row in ws.iter_rows(values_only=True)] for ws in wb.worksheets if ws.sheet_state == 'visible'}


def detect_header(grid: list[list[str]], target: str) -> int:
    """Index of the header row: the row whose cells best match the target's hints.
    A row of 'Label:' cells (Project: | Date: | Inspector:) is a form header, not a table header."""
    hints = {h for f in TARGETS[target]['fields'] for h in f[3]}
    best, best_score = 0, -1
    for i, row in enumerate(grid[:30]):
        cells = [c for c in row if c]
        if len(cells) < 2:
            continue
        if sum(c.rstrip().endswith(':') for c in cells) >= len(cells) / 2:
            continue
        score = sum(norm(c) in hints for c in cells) * 10 + len(cells)
        if score > best_score:
            best, best_score = i, score
    return best


def auto_map(headers: list[str], target: str) -> dict[str, str]:
    used, m = set(), {}
    for key, _label, _req, hints in TARGETS[target]['fields']:
        hit = next((h for h in headers if h and h not in used and norm(h) in hints), None)
        if hit is None:  # looser: a hint contained in the header
            hit = next((h for h in headers if h and h not in used and any(len(x) > 3 and x in norm(h) for x in hints)), None)
        m[key] = hit or ''
        if hit: used.add(hit)
    return m


def records(grid: list[list[str]], header_row: int, mapping: dict[str, str]) -> list[dict]:
    headers = grid[header_row]
    idx = {h: i for i, h in enumerate(headers) if h}
    out = []
    for n, row in enumerate(grid[header_row + 1:], start=header_row + 2):  # spreadsheet row numbers
        rec = {'_row': n}
        for key, col in mapping.items():
            if col and col in idx and idx[col] < len(row):
                rec[key] = row[idx[col]]
        if any(v for k, v in rec.items() if k != '_row'):
            out.append(rec)
    return out


def missing_required(mapping: dict[str, str], target: str) -> list[str]:
    return [label for key, label, req, _ in TARGETS[target]['fields'] if req and not mapping.get(key)]
