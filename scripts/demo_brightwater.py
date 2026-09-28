"""Load the Brightwater mock customer into a local workbench (./data) so you can click
around: python scripts/demo_brightwater.py && python wsgi.py. AI is replayed from the
test fixtures, so no API key is needed; the review is left open for you to finish."""
import io, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from onboard.docs import review
from onboard.web.app import create_app

F = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tests', 'fixtures')
review.draft_requirements = lambda paras, kind, title, provider=None, replay_path=None: json.load(
    open(os.path.join(F, 'ai_manual.json' if kind == 'company_manual' else 'ai_spec.json')))['drafts']
app = create_app()
c = app.test_client()
os.environ.pop('ONBOARD_PASSWORD', None)
c.post('/engagements', data={'name': 'Brightwater Builders (mock)', 'contact_name': 'Marisol Vance', 'contact_email': 'mvance@brightwaterbuilders.example'})
eid = 1
c.post(f'/e/{eid}/assessment/import', data={'file': (open(os.path.join(F, 'brightwater_assessment.json'), 'rb'), 'a.json')}, content_type='multipart/form-data')
c.get(f'/e/{eid}/assessment')
def up(name, kind, **x):
    return c.post(f'/e/{eid}/upload', data={'file': (open(os.path.join(F, name), 'rb'), name), 'kind': kind, **x}, content_type='multipart/form-data')
up('BWB-Safety-Program-Manual-Rev7.docx', 'company_manual', title='BWB Safety Program Manual Rev 7', form_c_ref='D02')
up('Bayside-Health-Spec-01-35-23-and-01-35-13.13.pdf', 'owner_spec', title='Bayside Health Spec 01 35 23 / 01 35 13.13', project_code='SAMC-EPT')
c.post(f'/e/{eid}/doc/1/ai'); c.post(f'/e/{eid}/doc/2/ai')
for name, kind in [('BWB_Vendor_List_export_2026-09-22.xlsx', 'vendor_list'), ('SAMC_Corrective_Action_Log_2026-09-26.xlsx', 'ca_log'),
                   ('SAMC_Injury_Log_and_Manhours_2026.xlsx', 'injury_log'), ('BWB_SF-12_Weekly_Site_Inspection.xlsx', 'checklist')]:
    up(name, kind)
print('Loaded. Run: python wsgi.py  ->  http://localhost:5055/e/1')
