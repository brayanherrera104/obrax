from datetime import date
from flask import render_template, session, redirect

from app import app, db
import control_obra
import budget_coverage


def _count(c, table, company_id):
    return c.execute(f'SELECT COUNT(*) n FROM {table} WHERE company_id=?', (company_id,)).fetchone()['n']


def _project_finance(c, project, company_id):
    pid = project['id']
    contract = float(project['value'] or 0)
    budget, budget_complete, budget_count = budget_coverage.project_budget_state(c, pid, company_id)
    costs = c.execute('SELECT COALESCE(SUM(amount),0) v FROM project_costs WHERE project_id=? AND company_id=?', (pid, company_id)).fetchone()
    actual = float(costs['v'] or 0)
    activities, weighted = control_obra.activity_data(c, pid, company_id)
    manual = control_obra.manual_progress(c, pid, company_id)
    has_activity_progress = any(float(x['progress'] or 0) > 0 for x in activities)
    progress = weighted if has_activity_progress else manual
    expected_cost = budget * progress / 100 if budget > 0 else 0
    deviation = actual - expected_cost if budget > 0 and progress > 0 else None
    projected_profit = contract - budget if budget > 0 and budget_complete else None
    projected_margin = (projected_profit / contract * 100) if projected_profit is not None and contract > 0 else None
    balance_vs_costs = contract - actual
    if budget <= 0:
        status = 'Sin presupuesto'
    elif not budget_complete:
        status = 'Presupuesto incompleto'
    elif progress <= 0:
        status = 'Sin avance'
    elif actual > expected_cost * 1.05:
        status = 'Sobrecosto'
    elif actual >= expected_cost * .90:
        status = 'Atención'
    else:
        status = 'Controlado'
    return {
        'id': pid, 'name': project['name'], 'client_name': project['client_name'],
        'contract': contract, 'budget': budget, 'budget_complete': budget_complete, 'budget_count': budget_count,
        'actual': actual, 'progress': progress, 'expected_cost': expected_cost, 'deviation': deviation,
        'projected_profit': projected_profit, 'projected_margin': projected_margin,
        'balance_vs_costs': balance_vs_costs, 'finance_status': status, 'status': project['status']
    }


def dashboard_live():
    if not session.get('company_id') and not session.get('demo'):
        return redirect('/login')
    if session.get('demo'):
        demo_project = {'id': 1, 'name': 'Cerramiento estación TM', 'client_name': 'Cliente Demo', 'contract': 185000000, 'budget': 145000000, 'budget_complete': True, 'budget_count': 1, 'actual': 68000000, 'progress': 50, 'expected_cost': 72500000, 'deviation': -4500000, 'projected_profit': 40000000, 'projected_margin': 21.6, 'balance_vs_costs': 117000000, 'finance_status': 'Controlado', 'status': 'En ejecución'}
        return render_template('dashboard.html', company={'name':'Constructora Demo S.A.S.'}, projects=[demo_project], apus_count=12, clients_count=8, budgets_count=5, quotes_count=3, quoted_total=505000000, projects_count=1, active_projects=1, contracted_total=185000000, committed_total=68000000, pending_total=18000000, overdue_total=6000000, balance_vs_costs=117000000, projected_profit_total=40000000, complete_budget_total=145000000, partial_budget_total=0, budget_total=145000000, incomplete_projects=0, demo=True)

    cid = session['company_id']
    control_obra.ensure_cost_table(); budget_coverage.ensure_budget_coverage_table()
    c = db()
    co = c.execute('SELECT * FROM companies WHERE id=?', (cid,)).fetchone()
    raw_projects = c.execute("""SELECT p.*,COALESCE(cl.name,p.client,'') client_name
        FROM projects p LEFT JOIN clients cl ON cl.id=p.client_id
        WHERE p.company_id=? ORDER BY p.id DESC""", (cid,)).fetchall()
    finance_projects = [_project_finance(c, p, cid) for p in raw_projects]
    projects_count = len(raw_projects)
    apus_count = _count(c, 'apus', cid); clients_count = _count(c, 'clients', cid); budgets_count = _count(c, 'budgets', cid); quotes_count = _count(c, 'quotations', cid)
    active_projects = sum(1 for p in raw_projects if str(p['status'] or '').lower() not in ('finalizada','finalizado','terminada','terminado','cerrada','cerrado'))
    contracted_total = sum(p['contract'] for p in finance_projects)
    budget_total = sum(p['budget'] for p in finance_projects)
    complete_budget_total = sum(p['budget'] for p in finance_projects if p['budget_complete'])
    partial_budget_total = sum(p['budget'] for p in finance_projects if p['budget'] > 0 and not p['budget_complete'])
    incomplete_projects = sum(1 for p in finance_projects if p['budget'] > 0 and not p['budget_complete'])
    projected_profit_total = sum(p['projected_profit'] or 0 for p in finance_projects)
    costs = c.execute('SELECT amount,payment_status,due_date FROM project_costs WHERE company_id=?', (cid,)).fetchall()
    committed_total = sum(float(x['amount'] or 0) for x in costs)
    pending_total = sum(float(x['amount'] or 0) for x in costs if x['payment_status']=='Pendiente')
    today = date.today().isoformat()
    overdue_total = sum(float(x['amount'] or 0) for x in costs if x['payment_status']=='Pendiente' and x['due_date'] and x['due_date'] < today)
    balance_vs_costs = contracted_total - committed_total
    quote_rows = c.execute('SELECT budget_id FROM quotations WHERE company_id=?', (cid,)).fetchall(); quoted_total = 0
    for q in quote_rows:
        rows = c.execute('SELECT quantity,unit_price FROM budget_items WHERE budget_id=?', (q['budget_id'],)).fetchall()
        quoted_total += sum(float(x['quantity'] or 0)*float(x['unit_price'] or 0) for x in rows)
    c.close()
    return render_template('dashboard.html', company=co, projects=finance_projects[:6], apus_count=apus_count, clients_count=clients_count, budgets_count=budgets_count, quotes_count=quotes_count, quoted_total=quoted_total, projects_count=projects_count, active_projects=active_projects, contracted_total=contracted_total, budget_total=budget_total, complete_budget_total=complete_budget_total, partial_budget_total=partial_budget_total, incomplete_projects=incomplete_projects, projected_profit_total=projected_profit_total, committed_total=committed_total, pending_total=pending_total, overdue_total=overdue_total, balance_vs_costs=balance_vs_costs, demo=False)

app.view_functions['dashboard'] = dashboard_live
