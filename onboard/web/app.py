"""SafeTell Onboard: the workbench our team uses to assess a new customer and prepare
their data for SafeTell. Customers never log in here; SafeTell's own importers do the
final validation."""
from __future__ import annotations
import datetime as dt, functools, hmac, json, os, uuid
from flask import Flask, abort, flash, redirect, render_template, request, send_file, session as web, url_for
import io

from ..models import UPLOAD_KINDS, Assessment, Draft, Engagement, SourceDocument, Upload, make_session
from ..docs import review
from ..docs.drafting import CATEGORIES
from ..sheets import tables, lifecritical
from ..outputs import package
from ..assessment import forms


def create_app(db_url: str | None = None, data_dir: str | None = None) -> Flask:
    app = Flask(__name__)
    app.secret_key = os.environ.get('ONBOARD_SECRET', 'dev-only-change-me')
    data_dir = data_dir or os.environ.get('ONBOARD_DATA', 'data')
    files_dir = os.path.join(data_dir, 'files')
    os.makedirs(files_dir, exist_ok=True)
    Session = make_session(db_url)
    password = os.environ.get('ONBOARD_PASSWORD')

    @app.before_request
    def open_db():
        request.db = Session()

    @app.teardown_request
    def close_db(exc):
        db = getattr(request, 'db', None)
        if db is not None:
            (db.rollback if exc else db.commit)()
            db.close()

    def login_required(f):
        @functools.wraps(f)
        def w(*a, **k):
            if password and not web.get('ok'):
                return redirect(url_for('login', next=request.path))
            return f(*a, **k)
        return w

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST' and password and hmac.compare_digest(request.form.get('password', ''), password):
            web['ok'] = True
            return redirect(request.args.get('next') or url_for('index'))
        return render_template('login.html')

    def eng(eid) -> Engagement:
        e = request.db.get(Engagement, eid)
        if not e: abort(404)
        return e

    def read_upload(u: Upload) -> bytes:
        return open(u.path, 'rb').read()

    # ------------------------------------------------------------ engagements
    @app.route('/')
    @login_required
    def index():
        es = request.db.query(Engagement).order_by(Engagement.created_at.desc()).all()
        return render_template('index.html', engagements=es)

    @app.post('/engagements')
    @login_required
    def new_engagement():
        name = request.form.get('name', '').strip()
        if not name:
            flash('Give the customer a name'); return redirect(url_for('index'))
        e = Engagement(name=name, contact_name=request.form.get('contact_name'), contact_email=request.form.get('contact_email'))
        request.db.add(e); request.db.flush()
        return redirect(url_for('engagement', eid=e.id))

    @app.route('/e/<int:eid>')
    @login_required
    def engagement(eid):
        e = eng(eid)
        a = e.assessment
        docs = [(d, review.coverage(d)) for d in e.documents]
        return render_template('engagement.html', e=e, a=a, docs=docs, kinds=UPLOAD_KINDS)

    # ------------------------------------------------------------ files
    @app.post('/e/<int:eid>/upload')
    @login_required
    def upload(eid):
        e = eng(eid)
        f = request.files.get('file')
        if not f or not f.filename:
            flash('Choose a file'); return redirect(url_for('engagement', eid=eid))
        kind = request.form.get('kind', 'other')
        safe = f'{uuid.uuid4().hex}_{os.path.basename(f.filename)}'
        path = os.path.join(files_dir, safe)
        f.save(path)
        u = Upload(engagement=e, kind=kind, filename=f.filename, path=path, no_ai=bool(request.form.get('no_ai')),
                   form_c_ref=request.form.get('form_c_ref') or None)
        request.db.add(u); request.db.flush()
        if kind in ('company_manual', 'owner_spec'):
            try:
                d = review.create_document(request.db, e, u, read_upload(u), request.form.get('title') or f.filename,
                                           request.form.get('project_code') or None)
                request.db.flush()
                return redirect(url_for('document', eid=eid, did=d.id))
            except Exception as ex:
                flash(f'Could not read {f.filename}: {ex}')
        elif f.filename.lower().endswith(('.xlsx', '.xlsm', '.csv')):
            return redirect(url_for('sheet', eid=eid, uid=u.id))
        return redirect(url_for('engagement', eid=eid))

    @app.route('/e/<int:eid>/file/<int:uid>')
    @login_required
    def download_upload(eid, uid):
        u = request.db.get(Upload, uid)
        if not u or u.engagement_id != eid: abort(404)
        return send_file(u.path, download_name=u.filename, as_attachment=True)

    # ------------------------------------------------------------ document review
    @app.route('/e/<int:eid>/doc/<int:did>')
    @login_required
    def document(eid, did):
        e = eng(eid)
        d = request.db.get(SourceDocument, did)
        if not d or d.engagement_id != eid: abort(404)
        up = request.db.get(Upload, d.upload_id) if d.upload_id else None
        c = review.coverage(d)
        by_ref = {}
        for dr in d.drafts:
            by_ref.setdefault(dr.paragraph_ref, []).append(dr)
        skips = {s.paragraph_ref: s.reason for s in d.skips}
        return render_template('document.html', e=e, d=d, up=up, c=c, by_ref=by_ref, skips=skips, categories=CATEGORIES,
                               ai_ready=bool(os.environ.get('ANTHROPIC_API_KEY') or os.environ.get('OPENROUTER_API_KEY')))

    @app.post('/e/<int:eid>/doc/<int:did>/<action>')
    @login_required
    def document_action(eid, did, action):
        d = request.db.get(SourceDocument, did)
        if not d or d.engagement_id != eid: abort(404)
        f = request.form
        try:
            if action == 'ai':
                up = request.db.get(Upload, d.upload_id) if d.upload_id else None
                r = review.run_ai(request.db, d, up)
                flash(f"AI drafted {r['added']} requirement(s)" + (f", {len(r['rejected'])} pointed at paragraphs that don't exist and were dropped" if r['rejected'] else ''))
            elif action == 'draft':
                review.add_draft(request.db, d, paragraph_ref=f['ref'], title=f['title'], requirement_text=f['requirement_text'],
                                 category=f.get('category'), high_risk=bool(f.get('high_risk')), quote=f.get('quote'))
            elif action == 'skip':
                review.skip_paragraph(request.db, d, f['ref'], f.get('reason', ''))
            elif action == 'unskip':
                review.unskip(request.db, d, f['ref'])
            elif action == 'decide':
                dr = request.db.get(Draft, int(f['draft_id']))
                if not dr or dr.document_id != d.id: abort(404)
                review.decide(request.db, dr, f['decision'], note=f.get('note'), title=f.get('title'), requirement_text=f.get('requirement_text'),
                              high_risk=bool(f.get('high_risk')) if 'title' in f else None, category=f.get('category'),
                              quote=f.get('quote') if 'quote' in f else None, without_quote=bool(f.get('without_quote')))
            elif action == 'accept_verified':
                flash(f'Accepted {review.accept_all_verified(request.db, d)} draft(s) with a verified quote and matching numbers; the rest need a look')
            elif action == 'complete':
                review.complete_review(d); flash('Review complete')
            elif action == 'reopen':
                review.reopen(d)
            else:
                abort(404)
        except review.ReviewError as ex:
            flash(str(ex))
        except Exception as ex:  # AI provider errors etc.
            flash(f'Failed: {ex}')
        return redirect(url_for('document', eid=eid, did=did) + (f"#p-{f.get('ref')}" if f.get('ref') else ''))

    # ------------------------------------------------------------ spreadsheet mapping
    @app.route('/e/<int:eid>/sheet/<int:uid>', methods=['GET', 'POST'])
    @login_required
    def sheet(eid, uid):
        e = eng(eid)
        u = request.db.get(Upload, uid)
        if not u or u.engagement_id != eid: abort(404)
        sheets = tables.read_sheets(u.filename, read_upload(u))
        m = dict(u.mapping or {})
        default_target = {'vendor_list': 'contractors', 'ca_log': 'corrective_actions', 'injury_log': 'injuries', 'hours': 'hours', 'checklist': 'checklist'}.get(u.kind, 'contractors')
        sheet_name = request.values.get('sheet') or m.get('sheet') or next(iter(sheets))
        target = request.values.get('target') or m.get('target') or default_target
        grid = sheets.get(sheet_name) or next(iter(sheets.values()))
        header = int(request.values['header']) - 1 if request.values.get('header') else (m.get('header') if m.get('sheet') == sheet_name and m.get('target') == target else tables.detect_header(grid, target))
        headers = grid[header] if header < len(grid) else []
        if request.method == 'POST' and request.form.get('save'):
            cols = {k: request.form.get(f'col_{k}', '') for k, *_ in tables.TARGETS[target]['fields']}
            extra = {}
            if target == 'checklist':
                extra['life_critical'] = sorted(int(x) for x in request.form.getlist('lc'))
            if target == 'contractors':
                extra['exclude_rows'] = sorted(int(x) for x in request.form.getlist('exclude'))
            u.mapping = {'sheet': sheet_name, 'target': target, 'header': header, 'columns': cols, **extra}
            flash('Mapping saved')
            return redirect(url_for('sheet', eid=eid, uid=uid))
        cols = m.get('columns') if (m.get('sheet') == sheet_name and m.get('target') == target and m.get('header') == header) else tables.auto_map(headers, target)
        recs = tables.records(grid, header, cols) if headers else []
        info = {}
        if target == 'checklist':
            lc_list = _life_critical_list(e)
            info['suggestions'] = lifecritical.suggestions(recs, lc_list)
            info['life_critical_list'] = lc_list
            info['confirmed'] = set(m.get('life_critical', [])) if m.get('life_critical') is not None else {s['index'] for s in info['suggestions'] if s['list_match'] or s['column_says_critical']}
        if target == 'contractors':
            info['duplicates'] = package.possible_duplicates(recs)
            info['exclude'] = set(m.get('exclude_rows', []))
        return render_template('sheet.html', e=e, u=u, sheets=list(sheets), sheet_name=sheet_name, target=target, targets=tables.TARGETS,
                               grid=grid[:header + 12], header=header, headers=headers, cols=cols, recs=recs,
                               missing=tables.missing_required(cols, target), info=info, saved=bool(u.mapping))

    def _life_critical_list(e: Engagement) -> list[str]:
        items = (e.assessment.answers.get('life_critical_items') if e.assessment else None) or []
        if not items and e.assessment:  # suggest from Form B1: severity-5 activities they do
            items = [h['activity'] for h in (e.assessment.scores or {}).get('hazards', []) if h['severity'] == 5]
        return items

    # ------------------------------------------------------------ assessment
    @app.route('/e/<int:eid>/assessment', methods=['GET', 'POST'])
    @login_required
    def assessment(eid):
        e = eng(eid)
        a = e.assessment or Assessment(engagement=e, answers={}, scores={})
        if request.method == 'POST':
            ans = json.loads(json.dumps(a.answers or {}))
            f = request.form
            ans['A5'] = {**ans.get('A5', {}), 'deadline': f.get('deadline', ''), 'deadline_date': f.get('deadline_date', '')}
            ans['A4'] = {k: f.get(f'a4_{k}', '') for k, _ in forms.A4_QUESTIONS}
            b1 = []
            for i, (act, sev) in enumerate(forms.B1_ACTIVITIES):
                done = bool(f.get(f'b1_done_{i}'))
                b1.append([act, done, int(f.get(f'b1_freq_{i}') or 0) or None, bool(f.get(f'b1_proc_{i}'))])
            for j in range(2):
                name = f.get(f'b1_other_{j}', '').strip()
                if name:
                    b1.append([name if name.lower().startswith('other') else 'Other: ' + name, True, int(f.get(f'b1_other_freq_{j}') or 0) or None, bool(f.get(f'b1_other_proc_{j}'))])
            ans['B1'] = b1
            ans['B2'] = {**ans.get('B2', {}), 'band_selected': f.get('b2_band', ''),
                         'integrity': {k: f.get(f'b2i_{k}', '') for k in forms.B2_INTEGRITY_UNFAVOURABLE}}
            ans['B3'] = {**ans.get('B3', {}), 'declared_tier': int(f['b3_tier']) if f.get('b3_tier') not in (None, '') else None}
            ans['B4'] = {k: int(f.get(f'b4_{k}') or 0) for k in forms.B4_FACTORS}
            ans['C'] = {ref: [f.get(f'c_{ref}', ans.get('C', {}).get(ref, ['', ''])[0]), f.get(f'cf_{ref}', '')] for ref, *_ in forms.FORM_C if f.get(f'c_{ref}') is not None}
            ans['life_critical_items'] = [x.strip() for x in f.get('life_critical_items', '').splitlines() if x.strip()]
            a.answers = ans
            request.db.add(a)
            flash('Saved')
            return redirect(url_for('assessment', eid=eid))
        ans = a.answers or {}
        if ans:
            dl = ans.get('A5', {}).get('deadline_date')
            a.scores = forms.score(ans, deadline=dt.date.fromisoformat(dl) if dl else None)
            request.db.add(a)
        return render_template('assessment.html', e=e, a=a, ans=ans, sc=a.scores or {}, forms=forms,
                               b1={r[0]: r for r in ans.get('B1', [])}, others=[r for r in ans.get('B1', []) if r[0] not in forms.SEVERITY])

    @app.post('/e/<int:eid>/assessment/import')
    @login_required
    def assessment_import(eid):
        """Load Form A-C answers from JSON (e.g. the prospect's intake, or a test customer)."""
        e = eng(eid)
        f = request.files.get('file')
        try:
            ans = json.load(f)
        except Exception:
            flash('That is not a JSON answers file'); return redirect(url_for('assessment', eid=eid))
        a = e.assessment or Assessment(engagement=e)
        a.answers = ans
        request.db.add(a)
        return redirect(url_for('assessment', eid=eid))

    # ------------------------------------------------------------ package
    @app.route('/e/<int:eid>/package')
    @login_required
    def package_view(eid):
        e = eng(eid)
        return render_template('package.html', e=e, **_package_parts(e))

    def _package_parts(e: Engagement) -> dict:
        parts = {'contractors': [], 'history': {}, 'checklists': [], 'requirements': [], 'warnings': []}
        hist = {'corrective_actions': [], 'injuries': [], 'hours': []}
        for u in e.uploads:
            m = u.mapping
            if not m: continue
            grid = tables.read_sheets(u.filename, read_upload(u)).get(m['sheet'])
            if grid is None: continue
            recs = tables.records(grid, m['header'], m['columns'])
            if m['target'] == 'contractors':
                ex = set(m.get('exclude_rows', []))
                parts['contractors'] += [r for r in recs if r['_row'] not in ex]
            elif m['target'] in hist:
                hist[m['target']] += recs
            elif m['target'] == 'checklist':
                parts['checklists'].append((u, recs, set(m.get('life_critical', []))))
        parts['history'] = hist
        for d in e.documents:
            if d.review_complete:
                parts['requirements'] += review.export_requirements(d)
            else:
                parts['warnings'].append(f'{d.title}: review not complete - its requirements are left out')
        for dup in package.possible_duplicates(parts['contractors']):
            parts['warnings'].append(f"Possible duplicate contractors: {dup['companies'][0]} / {dup['companies'][1]} ({dup['why']})")
        return parts

    @app.route('/e/<int:eid>/package.zip')
    @login_required
    def package_zip(eid):
        e = eng(eid)
        p = _package_parts(e)
        a = (e.assessment.answers if e.assessment else {}) or {}
        a1, a2 = a.get('A1', {}), a.get('A2', {})
        company = {'Legal name': a1.get('legal_name') or e.name, 'Trading name': a1.get('trading_name'), 'Website': a1.get('website'),
                   'Primary admin (name)': e.contact_name, 'Primary admin (email)': e.contact_email}
        files = {}
        files[f'SafeTell-Onboarding-Workbook_{_slug(e.name)}.xlsx'] = package.build_workbook(company=company, contractors=p['contractors'])
        h = package.build_history(**p['history'])
        for section, rows in h.items():
            if rows and section in package.HISTORY_LABELS:
                files[f'history_{section}.xlsx'] = package.build_history_sheet(section, rows)
        for u, recs, lc in p['checklists']:
            files[f'checklist_{_slug(os.path.splitext(u.filename)[0])}.xlsx'] = package.build_checklist(recs, {i for i in lc})
        if p['requirements']:
            files['requirements.json'] = json.dumps(p['requirements'], indent=1)
        files['README.txt'] = render_template('package_readme.txt', e=e, p=p, files=list(files))
        return send_file(io.BytesIO(package.build_zip(files)), download_name=f'{_slug(e.name)}-safetell-package.zip', as_attachment=True)

    return app


def _slug(s: str) -> str:
    import re
    return re.sub(r'[^A-Za-z0-9]+', '_', s).strip('_')[:60]
