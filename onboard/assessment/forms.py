"""Forms A-C of the staged client assessment (docs/client-assessment in the SafeTell repo),
and the Form B scoring. Wording is taken from the forms; scoring rules are Form B's own."""
from __future__ import annotations
import datetime as dt

A4_QUESTIONS = [
    ('written_policy_signed', 'Do you have a written safety policy signed by senior leadership?'),
    ('procedures_high_risk', 'Do you have written procedures for the high-risk work you perform?'),
    ('orientation_everyone', 'Does every worker, including subcontractors, receive a site orientation before starting?'),
    ('risk_assessed_recorded', 'Do you assess risk before high-risk tasks, and record it?'),
    ('contractors_selected_on_safety', 'Are contractors selected partly on their safety record?'),
    ('investigate_beyond_immediate', 'Are incidents investigated beyond the immediate cause?'),
    ('serious_injury_5yr', 'Has anyone been seriously injured or killed at your work in the last five years?'),
    ('open_citations', 'Do you have any open or unresolved regulatory citations or notices?'),
    ('fixed_deadline', 'Is there a fixed deadline driving this enquiry - audit, bid, certification?'),
    ('client_asked_for_sms', 'Has a client, insurer or owner asked you to demonstrate a safety management system?'),
]

# Form B1: activity -> preset severity
B1_ACTIVITIES = [
    ('Work at height, edges and openings', 5), ('Excavation, trenching and shoring', 5), ('Confined space entry', 5),
    ('Control of hazardous energy and live electrical work', 5), ('Crane and heavy load lifting', 5), ('Mobile plant and vehicle movements', 5),
    ('Demolition or structural alteration', 5), ('Flammable, explosive or highly toxic substances', 5), ('Driving and fleet operations', 5),
    ('Marine, offshore or over-water work', 5),
    ('Scaffolding and elevated platforms', 4), ('Hot work — welding, cutting, grinding', 4), ('Pressure systems and pressure testing', 4),
    ('Asbestos, lead or legacy hazardous materials', 4), ('Respirable dust including silica', 4), ('Radiation sources or radiography', 4),
    ('Work adjacent to live traffic', 4), ('Remote or isolated working', 4),
    ('Fumes, solvents and chemical handling', 3), ('High noise environments', 3), ('Extreme heat or cold', 3),
    ('Manual handling and repetitive strain', 3), ('Hand and power tool use', 3), ('Fatigue from shift pattern or extended hours', 3),
]
SEVERITY = dict(B1_ACTIVITIES)

B2_BANDS = [
    (5, 'Rates below benchmark, no serious outcomes, EMR below 0.9, trend improving'),
    (12, 'Rates near benchmark, EMR 0.9 to 1.0, trend flat'),
    (19, 'Rates above benchmark, or EMR above 1.0, or trend worsening, or a recurring incident type'),
    (25, 'A fatality or life-altering injury in the last five years, or a high-potential event with no change to controls since'),
]
B2_INTEGRITY_UNFAVOURABLE = {'hours_include_contractors': {'No', 'Partly'}, 'first_aid_logged': {'No'},
                             'bonus_tied_to_injuries': {'Yes'}, 'near_misses_honest': {'No', 'Unsure'}}
B3_TIERS = ['None', 'Basic', 'Partial', 'Documented', 'Managed', 'Comprehensive']
B4_FACTORS = ['workforce_stability', 'subcontracting', 'complexity_and_change', 'schedule_pressure', 'safety_resourcing']
RANKS = [(25, 'R1', 'Low'), (50, 'R2', 'Moderate'), (75, 'R3', 'High'), (100, 'R4', 'Critical')]
REQUIRED_TIER = {'R1': 3, 'R2': 3, 'R3': 4, 'R4': 5}  # default; the forms leave this open

# Form C: ref, section, title, level (core | extended | full = first level that asks for it)
FORM_C = [
    ('D01', 'Direction and structure', 'Safety policy statement', 'core'),
    ('D02', 'Direction and structure', 'Safety manual, handbook or system description', 'core'),
    ('D03', 'Direction and structure', 'Organisation chart showing safety responsibilities', 'core'),
    ('D04', 'Direction and structure', 'Safety objectives or goals for the current year', 'extended'),
    ('D05', 'Risk and planning', 'Risk assessment method or template', 'core'),
    ('D06', 'Risk and planning', 'Current risk register, or two completed assessments', 'core'),
    ('D07', 'Risk and planning', 'Two completed task-level plans for high-risk work', 'core'),
    ('D08', 'Risk and planning', 'Register of legal and client requirements', 'extended'),
    ('D09', 'High-risk work procedures', 'Procedures for the three highest-scoring activities in Form B1', 'core'),
    ('D10', 'High-risk work procedures', 'Permit to work forms and two completed examples', 'extended'),
    ('D11', 'High-risk work procedures', 'Remaining high-risk procedures', 'full'),
    ('D12', 'High-risk work procedures', 'Emergency plan for one representative site', 'core'),
    ('D13', 'High-risk work procedures', 'Record of the last emergency exercise', 'extended'),
    ('D14', 'People', 'Training matrix or competence requirements by role', 'core'),
    ('D15', 'People', 'Training records for one crew, including subcontractors', 'extended'),
    ('D16', 'People', 'Site orientation content and a signed attendance sheet', 'core'),
    ('D17', 'People', 'Supervisor safety training records', 'full'),
    ('D18', 'Contractors', 'Contractor prequalification form or criteria', 'core'),
    ('D19', 'Contractors', 'Safety clauses from a live contract', 'extended'),
    ('D20', 'Contractors', 'One accepted subcontractor safety plan', 'extended'),
    ('D21', 'Contractors', 'Record of contractor monitoring or a performance score', 'full'),
    ('D22', 'Checking and learning', 'Two completed site inspection reports', 'core'),
    ('D23', 'Checking and learning', 'Two incident investigation reports, one serious if available', 'core'),
    ('D24', 'Checking and learning', 'Corrective action register or tracker', 'extended'),
    ('D25', 'Checking and learning', 'Most recent internal audit report', 'extended'),
    ('D26', 'Checking and learning', 'Most recent management review minutes', 'extended'),
    ('D27', 'Checking and learning', 'Any exposure monitoring results — noise, dust, chemical', 'full'),
    ('D28', 'Checking and learning', 'Safety performance report as sent to leadership', 'full'),
    ('D29', 'Checking and learning', 'Equipment inspection or maintenance schedule with completion data', 'full'),
]
LEVELS = {'core': 1, 'extended': 2, 'full': 3}
RANK_LEVEL = {'R1': 'core', 'R2': 'extended', 'R3': 'extended', 'R4': 'full'}

# Form C documents that also feed SafeTell setup, so the customer never sends them twice
FORM_C_TO_SETUP = {'D02': ('company_manual', 'Requirement review'), 'D10': ('permits', 'Permit types'),
                   'D18': ('other', 'Prequalification settings'), 'D22': ('checklist', 'Checklist import'),
                   'D24': ('ca_log', 'History import (corrective actions)')}


def documents_for_rank(rank: str) -> list[tuple]:
    lvl = LEVELS[RANK_LEVEL.get(rank, 'core')]
    return [d for d in FORM_C if LEVELS[d[3]] <= lvl]


def score(answers: dict, today: dt.date | None = None, deadline: dt.date | None = None) -> dict:
    """Form B scoring from the answers dict (see tests/fixtures/brightwater_assessment.json for the shape)."""
    today = today or dt.date.today()
    rows = []
    for act, done, freq, proc in answers.get('B1', []):
        if not done:
            continue
        sev = SEVERITY.get(act, 5 if act.lower().startswith('other') else 3)
        rows.append({'activity': act, 'severity': sev, 'frequency': freq, 'risk': sev * (freq or 0), 'procedure': proc})
    n12 = sum(r['risk'] >= 12 for r in rows)
    any20 = any(r['risk'] >= 20 for r in rows)
    b1 = 25 if (n12 >= 9 or any20) else 18 if n12 >= 4 else 11 if n12 >= 1 else 5

    b2info = answers.get('B2', {})
    band = next((s for s, text in B2_BANDS if text == b2info.get('band_selected')), None)
    unfav = [k for k, bad in B2_INTEGRITY_UNFAVOURABLE.items() if b2info.get('integrity', {}).get(k) in bad]
    b2 = min(25, (band or 0) + (5 if len(unfav) >= 2 else 0))

    tier = answers.get('B3', {}).get('declared_tier')
    b3 = 25 - 5 * tier if tier is not None else None
    b4 = sum(int(answers.get('B4', {}).get(f, 0) or 0) for f in B4_FACTORS)
    composite = b1 + b2 + (b3 or 0) + b4
    rank = next(r for top, r, _ in RANKS if composite <= top)
    required = REQUIRED_TIER[rank]

    a4 = answers.get('A4', {})
    flags = []
    if a4.get('serious_injury_5yr') == 'Yes': flags.append('Fatality or serious injury in the last five years')
    if a4.get('open_citations') == 'Yes': flags.append('Open or unresolved regulatory citation')
    if band == 25: flags.append('Top loss-history band')
    no_proc = [r['activity'] for r in rows if r['severity'] == 5 and not r['procedure']]
    if no_proc: flags.append('Severity-5 activity with no written procedure: ' + '; '.join(no_proc))
    if deadline and 0 <= (deadline - today).days <= 90: flags.append(f'Fixed deadline in {(deadline - today).days} days')
    if a4.get('written_policy_signed') == 'No' and a4.get('procedures_high_risk') == 'No' and any(r['severity'] == 5 for r in rows):
        flags.append('No written arrangements alongside severity-5 work')

    confirm = answers.get('B3', {}).get('confirmation', {})
    tier_doubts = [k for k, v in confirm.items() if v in ('No', 'Unsure')]
    return {'b1': b1, 'b1_rows_12_plus': n12, 'b1_any_20_plus': any20, 'b2': b2, 'b2_band': band, 'b2_unfavourable_integrity': unfav,
            'b3': b3, 'declared_tier': tier, 'b4': b4, 'composite': composite, 'rank': rank, 'required_tier': required,
            'indicative_gap': (required - tier) if tier is not None else None, 'evidence_set': RANK_LEVEL[rank],
            'priority_flags': flags, 'auto_p1_gaps': [f'No written procedure for a severity-5 activity: {a}' for a in no_proc],
            'tier_confirmation_doubts': tier_doubts, 'hazards': rows}
