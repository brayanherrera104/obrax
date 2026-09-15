from flask import request, redirect, url_for, session, flash
from app import app, db, login_required


def ensure_budget_coverage_table():
    c = db()
    c.execute('''CREATE TABLE IF NOT EXISTS budget_coverage(
        budget_id INTEGER PRIMARY KEY,
        company_id INTEGER NOT NULL,
        coverage_status TEXT NOT NULL DEFAULT 'Parcial'
    )''')
    c.commit(); c.close()


def get_coverage(c, budget_id, company_id):
    row = c.execute('SELECT coverage_status FROM budget_coverage WHERE budget_id=? AND company_id=?', (budget_id, company_id)).fetchone()
    return row['coverage_status'] if row else 'Parcial'


def project_budget_state(c, project_id, company_id):
    budgets = c.execute('SELECT id FROM budgets WHERE project_id=? AND company_id=?', (project_id, company_id)).fetchall()
    total = 0.0
    complete = False
    for b in budgets:
        rows = c.execute('SELECT quantity,unit_price FROM budget_items WHERE budget_id=?', (b['id'],)).fetchall()
        total += sum(float(x['quantity'] or 0) * float(x['unit_price'] or 0) for x in rows)
        if get_coverage(c, b['id'], company_id) == 'Definitivo':
            complete = True
    return total, complete, len(budgets)


@app.route('/budget/<int:i>/coverage', methods=['POST'])
@login_required
def update_budget_coverage(i):
    ensure_budget_coverage_table()
    cid = session['company_id']
    status = request.form.get('coverage_status', 'Parcial')
    if status not in ('Parcial', 'Definitivo'):
        status = 'Parcial'
    c = db()
    budget = c.execute('SELECT id FROM budgets WHERE id=? AND company_id=?', (i, cid)).fetchone()
    if not budget:
        c.close(); return 'Presupuesto no encontrado', 404
    old = c.execute('SELECT budget_id FROM budget_coverage WHERE budget_id=? AND company_id=?', (i, cid)).fetchone()
    if old:
        c.execute('UPDATE budget_coverage SET coverage_status=? WHERE budget_id=? AND company_id=?', (status, i, cid))
    else:
        c.execute('INSERT INTO budget_coverage(budget_id,company_id,coverage_status) VALUES(?,?,?)', (i, cid, status))
    c.commit(); c.close()
    flash('Cobertura del presupuesto actualizada.')
    return redirect(url_for('budget_detail', i=i))


@app.context_processor
def inject_budget_coverage():
    def budget_coverage_status(budget_id):
        if not session.get('company_id'):
            return 'Parcial'
        ensure_budget_coverage_table()
        c = db(); status = get_coverage(c, budget_id, session['company_id']); c.close()
        return status
    return {'budget_coverage_status': budget_coverage_status}

ensure_budget_coverage_table()
