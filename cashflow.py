from datetime import date
from flask import render_template, session
from app import app, db, login_required
import control_obra
import receivables


def cashflow_data(company_id,project_id=None):
    control_obra.ensure_cost_table();receivables.ensure_receivables_table();c=db();params=[company_id];project_sql=' AND p.id=?' if project_id else ''
    if project_id:params.append(project_id)
    projects=c.execute("SELECT p.id,p.name,p.value,COALESCE(cl.name,p.client,'') client_name FROM projects p LEFT JOIN clients cl ON cl.id=p.client_id WHERE p.company_id=?"+project_sql+" ORDER BY p.name",tuple(params)).fetchall();result=[];today=date.today().isoformat()
    for p in projects:
        costs=c.execute('SELECT amount,payment_status,due_date FROM project_costs WHERE company_id=? AND project_id=?',(company_id,p['id'])).fetchall();recs=c.execute('SELECT * FROM project_receivables WHERE company_id=? AND project_id=?',(company_id,p['id'])).fetchall();income=sum(float(x['paid_amount'] or 0) for x in recs);billed=sum(float(x['amount'] or 0) for x in recs);retentions=sum(receivables.calc(x)[0] for x in recs);net_billed=sum(receivables.calc(x)[1] for x in recs);outflow=sum(float(x['amount'] or 0) for x in costs if x['payment_status']=='Pagado');payable=sum(float(x['amount'] or 0) for x in costs if x['payment_status']=='Pendiente');receivable=sum(receivables.calc(x)[2] for x in recs);overdue_payable=sum(float(x['amount'] or 0) for x in costs if x['payment_status']=='Pendiente' and x['due_date'] and x['due_date']<today);overdue_receivable=sum(receivables.calc(x)[2] for x in recs if receivables.calc(x)[2]>0 and x['due_date'] and x['due_date']<today)
        result.append({'id':p['id'],'name':p['name'],'client_name':p['client_name'],'contract':float(p['value'] or 0),'billed':billed,'retentions':retentions,'net_billed':net_billed,'income':income,'outflow':outflow,'cash_balance':income-outflow,'receivable':receivable,'payable':payable,'projected_balance':income+receivable-outflow-payable,'overdue_payable':overdue_payable,'overdue_receivable':overdue_receivable})
    c.close();return result

@app.route('/cashflow')
@login_required
def cashflow():
    cid=session['company_id'];rows=cashflow_data(cid);totals={k:sum(x[k] for x in rows) for k in ['contract','billed','retentions','net_billed','income','outflow','cash_balance','receivable','payable','projected_balance','overdue_payable','overdue_receivable']};return render_template('cashflow.html',rows=rows,totals=totals)
