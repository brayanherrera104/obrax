from datetime import date
from flask import render_template, session, redirect

# Load the main app and the operational routes/tables.
from app import app, db
import control_obra


def _count(c, table, company_id):
    return c.execute(f'SELECT COUNT(*) n FROM {table} WHERE company_id=?', (company_id,)).fetchone()['n']


def dashboard_live():
    if not session.get('company_id') and not session.get('demo'):
        return redirect('/login')

    if session.get('demo'):
        return render_template(
            'dashboard.html',
            company={'name': 'Constructora Demo S.A.S.'},
            projects=[{'name': 'Cerramiento estación TM', 'client': 'Cliente Demo', 'value': 185000000, 'status': 'En ejecución'}],
            apus_count=12, clients_count=8, budgets_count=5, quotes_count=3,
            quoted_total=505000000, projects_count=1, active_projects=1,
            contracted_total=185000000, committed_total=92000000,
            pending_total=18000000, overdue_total=6000000,
            current_profit=93000000, demo=True
        )

    cid = session['company_id']
    control_obra.ensure_cost_table()
    c = db()
    co = c.execute('SELECT * FROM companies WHERE id=?', (cid,)).fetchone()
    projects = c.execute("""SELECT p.*,COALESCE(cl.name,p.client,'') client_name
                          FROM projects p LEFT JOIN clients cl ON cl.id=p.client_id
                          WHERE p.company_id=? ORDER BY p.id DESC LIMIT 6""", (cid,)).fetchall()

    projects_count = _count(c, 'projects', cid)
    apus_count = _count(c, 'apus', cid)
    clients_count = _count(c, 'clients', cid)
    budgets_count = _count(c, 'budgets', cid)
    quotes_count = _count(c, 'quotations', cid)

    active_projects = c.execute("""SELECT COUNT(*) n FROM projects WHERE company_id=?
                                  AND LOWER(COALESCE(status,'')) NOT IN ('finalizada','finalizado','terminada','terminado','cerrada','cerrado')""", (cid,)).fetchone()['n']
    contracted_total = float(c.execute('SELECT COALESCE(SUM(value),0) v FROM projects WHERE company_id=?', (cid,)).fetchone()['v'] or 0)

    costs = c.execute('SELECT amount,payment_status,due_date FROM project_costs WHERE company_id=?', (cid,)).fetchall()
    committed_total = sum(float(x['amount'] or 0) for x in costs)
    pending_total = sum(float(x['amount'] or 0) for x in costs if x['payment_status'] == 'Pendiente')
    today = date.today().isoformat()
    overdue_total = sum(float(x['amount'] or 0) for x in costs if x['payment_status'] == 'Pendiente' and x['due_date'] and x['due_date'] < today)
    current_profit = contracted_total - committed_total

    quote_rows = c.execute('SELECT budget_id FROM quotations WHERE company_id=?', (cid,)).fetchall()
    quoted_total = 0
    for q in quote_rows:
        rows = c.execute('SELECT quantity,unit_price FROM budget_items WHERE budget_id=?', (q['budget_id'],)).fetchall()
        quoted_total += sum(float(x['quantity'] or 0) * float(x['unit_price'] or 0) for x in rows)
    c.close()

    return render_template(
        'dashboard.html', company=co, projects=projects,
        apus_count=apus_count, clients_count=clients_count,
        budgets_count=budgets_count, quotes_count=quotes_count,
        quoted_total=quoted_total, projects_count=projects_count,
        active_projects=active_projects, contracted_total=contracted_total,
        committed_total=committed_total, pending_total=pending_total,
        overdue_total=overdue_total, current_profit=current_profit, demo=False
    )


# Replace only the dashboard view; keep every existing route from app/control_obra.
app.view_functions['dashboard'] = dashboard_live
