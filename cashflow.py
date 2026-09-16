from datetime import date, timedelta
from flask import render_template, session
from app import app, db, login_required
import control_obra
import receivables


def assigned_project_ids(company_id):
    if not session.get('user_id'):return None
    c=db();ids=[x['project_id'] for x in c.execute('SELECT project_id FROM user_projects WHERE user_id=?',(session['user_id'],)).fetchall()];c.close();return ids

def cashflow_data(company_id,project_id=None,allowed_ids=None):
    control_obra.ensure_cost_table();receivables.ensure_receivables_table();c=db();params=[company_id];clauses=[]
    if project_id:clauses.append('p.id=?');params.append(project_id)
    if allowed_ids is not None:
        if not allowed_ids:clauses.append('1=0')
        else:clauses.append('p.id IN ('+','.join('?' for _ in allowed_ids)+')');params.extend(allowed_ids)
    project_sql=(' AND '+' AND '.join(clauses)) if clauses else ''
    projects=c.execute("SELECT p.id,p.name,p.value,COALESCE(cl.name,p.client,'') client_name FROM projects p LEFT JOIN clients cl ON cl.id=p.client_id WHERE p.company_id=?"+project_sql+" ORDER BY p.name",tuple(params)).fetchall();result=[];today=date.today().isoformat()
    for p in projects:
        costs=c.execute('SELECT amount,payment_status,due_date FROM project_costs WHERE company_id=? AND project_id=?',(company_id,p['id'])).fetchall();recs=c.execute('SELECT * FROM project_receivables WHERE company_id=? AND project_id=?',(company_id,p['id'])).fetchall();income=sum(float(x['paid_amount'] or 0) for x in recs);billed=sum(float(x['amount'] or 0) for x in recs);retentions=sum(receivables.calc(x)[0] for x in recs);net_billed=sum(receivables.calc(x)[1] for x in recs);outflow=sum(float(x['amount'] or 0) for x in costs if x['payment_status']=='Pagado');payable=sum(float(x['amount'] or 0) for x in costs if x['payment_status']=='Pendiente');receivable=sum(receivables.calc(x)[2] for x in recs);overdue_payable=sum(float(x['amount'] or 0) for x in costs if x['payment_status']=='Pendiente' and x['due_date'] and x['due_date']<today);overdue_receivable=sum(receivables.calc(x)[2] for x in recs if receivables.calc(x)[2]>0 and x['due_date'] and x['due_date']<today)
        result.append({'id':p['id'],'name':p['name'],'client_name':p['client_name'],'contract':float(p['value'] or 0),'billed':billed,'retentions':retentions,'net_billed':net_billed,'income':income,'outflow':outflow,'cash_balance':income-outflow,'receivable':receivable,'payable':payable,'projected_balance':income+receivable-outflow-payable,'overdue_payable':overdue_payable,'overdue_receivable':overdue_receivable})
    c.close();return result


def treasury_forecast(company_id,opening_balance,allowed_ids=None):
    control_obra.ensure_cost_table();receivables.ensure_receivables_table();c=db();today=date.today();events=[];scope='';params=[company_id]
    if allowed_ids is not None:
        if not allowed_ids:scope=' AND 1=0'
        else:scope=' AND r.project_id IN ('+','.join('?' for _ in allowed_ids)+')';params.extend(allowed_ids)
    recs=c.execute("SELECT r.*,p.name project_name FROM project_receivables r JOIN projects p ON p.id=r.project_id WHERE r.company_id=?"+scope,tuple(params)).fetchall()
    for r in recs:
        balance=receivables.calc(r)[2]
        if balance<=0:continue
        try:d=date.fromisoformat(r['due_date']) if r['due_date'] else today
        except Exception:d=today
        events.append({'date':d,'type':'Cobro','project':r['project_name'],'concept':r['concept'],'amount':balance})
    scope='';params=[company_id]
    if allowed_ids is not None:
        if not allowed_ids:scope=' AND 1=0'
        else:scope=' AND pc.project_id IN ('+','.join('?' for _ in allowed_ids)+')';params.extend(allowed_ids)
    costs=c.execute("SELECT pc.*,p.name project_name FROM project_costs pc JOIN projects p ON p.id=pc.project_id WHERE pc.company_id=? AND pc.payment_status='Pendiente'"+scope,tuple(params)).fetchall()
    for x in costs:
        try:d=date.fromisoformat(x['due_date']) if x['due_date'] else today
        except Exception:d=today
        events.append({'date':d,'type':'Pago','project':x['project_name'],'concept':x['description'] or 'Costo pendiente','amount':float(x['amount'] or 0)})
    c.close();events.sort(key=lambda x:(x['date'],0 if x['type']=='Pago' else 1));running=opening_balance;minimum=opening_balance;minimum_date=today
    for e in events:
        running+=e['amount'] if e['type']=='Cobro' else -e['amount'];e['balance']=running;e['date_label']=e['date'].strftime('%d/%m/%Y')
        if running<minimum:minimum=running;minimum_date=e['date']
    windows=[]
    for days in (7,15,30,60):
        limit=today+timedelta(days=days);ins=sum(e['amount'] for e in events if e['type']=='Cobro' and e['date']<=limit);outs=sum(e['amount'] for e in events if e['type']=='Pago' and e['date']<=limit);windows.append({'days':days,'income':ins,'outflow':outs,'balance':opening_balance+ins-outs})
    return events[:20],windows,minimum,minimum_date.strftime('%d/%m/%Y')


def treasury_alerts(rows,events,windows,minimum,minimum_date):
    alerts=[];today=date.today();overdue_payable=sum(x['overdue_payable'] for x in rows);overdue_receivable=sum(x['overdue_receivable'] for x in rows)
    if minimum<0:alerts.append({'level':'danger','title':'Riesgo de caja negativa','text':f'La caja podría bajar hasta ${minimum:,.0f} alrededor del {minimum_date}. Prioriza cobros o reprograma pagos.','url':'/payables?status=Pendiente','action':'Revisar pagos'})
    if overdue_payable>0:alerts.append({'level':'danger','title':'Pagos vencidos','text':f'Tienes ${overdue_payable:,.0f} en compromisos vencidos que requieren atención.','url':'/payables?status=Vencido','action':'Ver pagos vencidos'})
    if overdue_receivable>0:alerts.append({'level':'warning','title':'Cartera vencida','text':f'Tienes ${overdue_receivable:,.0f} netos vencidos por cobrar. Gestionar esta cartera puede mejorar la liquidez.','url':'/receivables?status=Vencido','action':'Gestionar cartera'})
    next_payment=next((e for e in events if e['type']=='Pago' and e['date']>=today),None);next_collection=next((e for e in events if e['type']=='Cobro' and e['date']>=today),None)
    if next_payment and (not next_collection or next_payment['date']<next_collection['date']):
        when=next_payment['date'].strftime('%d/%m/%Y');alerts.append({'level':'warning','title':'Pago antes del próximo cobro','text':f'Hay un pago de ${next_payment["amount"]:,.0f} el {when} antes del siguiente ingreso previsto.','url':'/payables?status=Pendiente','action':'Revisar compromisos'})
    w7=next((w for w in windows if w['days']==7),None)
    if w7 and w7['outflow']>w7['income'] and w7['outflow']>0:alerts.append({'level':'warning','title':'Presión de caja esta semana','text':f'En 7 días se proyectan salidas por ${w7["outflow"]:,.0f} e ingresos por ${w7["income"]:,.0f}.','url':'/payables?status=Pendiente','action':'Revisar próximos pagos'})
    if not alerts:alerts.append({'level':'good','title':'Tesorería sin alertas críticas','text':'Con las fechas y movimientos registrados no se detectan riesgos inmediatos de liquidez.','url':'/cashflow','action':'Ver proyección'})
    return alerts[:5]

@app.route('/cashflow')
@login_required
def cashflow():
    cid=session['company_id'];allowed=assigned_project_ids(cid);rows=cashflow_data(cid,allowed_ids=allowed);totals={k:sum(x[k] for x in rows) for k in ['contract','billed','retentions','net_billed','income','outflow','cash_balance','receivable','payable','projected_balance','overdue_payable','overdue_receivable']};events,windows,min_balance,min_date=treasury_forecast(cid,totals['cash_balance'],allowed);alerts=treasury_alerts(rows,events,windows,min_balance,min_date);return render_template('cashflow.html',rows=rows,totals=totals,forecast_events=events,forecast_windows=windows,min_balance=min_balance,min_date=min_date,treasury_alerts=alerts)
