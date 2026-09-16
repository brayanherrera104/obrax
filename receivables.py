from datetime import date
from flask import render_template, request, redirect, url_for, session, flash
from app import app, db, PG, login_required


def ensure_receivables_table():
    c=db(); pk='SERIAL PRIMARY KEY' if PG else 'INTEGER PRIMARY KEY AUTOINCREMENT'; real='DOUBLE PRECISION' if PG else 'REAL'
    c.execute(f'''CREATE TABLE IF NOT EXISTS project_receivables(id {pk},company_id INTEGER NOT NULL,project_id INTEGER NOT NULL,concept TEXT NOT NULL,document_date TEXT NOT NULL,due_date TEXT,amount {real} DEFAULT 0,paid_amount {real} DEFAULT 0,notes TEXT)''')
    c.execute(f'''CREATE TABLE IF NOT EXISTS receivable_payments(id {pk},company_id INTEGER NOT NULL,receivable_id INTEGER NOT NULL,payment_date TEXT NOT NULL,amount {real} DEFAULT 0,payment_method TEXT,reference TEXT,notes TEXT)''');c.commit();c.close()
    for col in ['retefuente_pct','reteica_pct','reteiva_pct','other_withholding']:
        c=db()
        try:c.execute(f'ALTER TABLE project_receivables ADD COLUMN {col} {real} DEFAULT 0');c.commit()
        except Exception:c.rollback()
        c.close()


def calc(row):
    gross=float(row['amount'] or 0); retention=max(0,gross*(float(row['retefuente_pct'] or 0)+float(row['reteica_pct'] or 0)+float(row['reteiva_pct'] or 0))/100+float(row['other_withholding'] or 0)); net=max(0,gross-retention); paid=float(row['paid_amount'] or 0); return retention,net,max(0,net-paid)

def receivable_state(row,today):
    balance=calc(row)[2]
    if balance<=0:return 'Cobrado'
    if row['due_date'] and row['due_date']<today:return 'Vencido'
    return 'Pendiente'

def assigned_project_ids(c):
    if not session.get('user_id'):return None
    return [x['project_id'] for x in c.execute('SELECT project_id FROM user_projects WHERE user_id=?',(session['user_id'],)).fetchall()]

def allowed_project(project_id,allowed):return allowed is None or int(project_id) in allowed

@app.route('/receivables',methods=['GET','POST'])
@login_required
def receivables():
    ensure_receivables_table();cid=session['company_id'];c=db();allowed=assigned_project_ids(c)
    if request.method=='POST':
        try:amount=float(request.form.get('amount',0) or 0);paid=float(request.form.get('paid_amount',0) or 0);rf=float(request.form.get('retefuente_pct',0) or 0);ri=float(request.form.get('reteica_pct',0) or 0);rv=float(request.form.get('reteiva_pct',0) or 0);other=float(request.form.get('other_withholding',0) or 0)
        except ValueError:amount=paid=rf=ri=rv=other=0
        project_id=request.form.get('project_id','');concept=request.form.get('concept','').strip();project=c.execute('SELECT id FROM projects WHERE id=? AND company_id=?',(project_id,cid)).fetchone() if project_id.isdigit() else None
        if project and not allowed_project(project_id,allowed):c.close();flash('Esta obra no está asignada a tu usuario.');return redirect(url_for('receivables'))
        if not project or not concept or amount<=0:c.close();flash('Selecciona una obra, escribe el concepto e ingresa un valor mayor a cero.');return redirect(url_for('receivables'))
        rf=max(0,rf);ri=max(0,ri);rv=max(0,rv);other=max(0,other);net=max(0,amount-amount*(rf+ri+rv)/100-other);paid=max(0,min(paid,net));doc_date=request.form.get('document_date') or date.today().isoformat()
        if PG:rid=c.execute('INSERT INTO project_receivables(company_id,project_id,concept,document_date,due_date,amount,paid_amount,notes,retefuente_pct,reteica_pct,reteiva_pct,other_withholding) VALUES(?,?,?,?,?,?,?,?,?,?,?,?) RETURNING id',(cid,int(project_id),concept,doc_date,request.form.get('due_date') or None,amount,paid,request.form.get('notes','').strip(),rf,ri,rv,other)).fetchone()['id']
        else:rid=c.execute('INSERT INTO project_receivables(company_id,project_id,concept,document_date,due_date,amount,paid_amount,notes,retefuente_pct,reteica_pct,reteiva_pct,other_withholding) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(cid,int(project_id),concept,doc_date,request.form.get('due_date') or None,amount,paid,request.form.get('notes','').strip(),rf,ri,rv,other)).lastrowid
        if paid>0:c.execute('INSERT INTO receivable_payments(company_id,receivable_id,payment_date,amount,payment_method,reference,notes) VALUES(?,?,?,?,?,?,?)',(cid,rid,doc_date,paid,'Abono inicial','','Registrado al crear la cuenta'))
        c.commit();c.close();flash('Cuenta por cobrar registrada con retenciones.');return redirect(url_for('receivables'))
    status=request.args.get('status','Todos');project_filter=request.args.get('project_id','');today=date.today().isoformat();q='''SELECT r.*,p.name project_name,COALESCE(cl.name,p.client,'') client_name FROM project_receivables r JOIN projects p ON p.id=r.project_id LEFT JOIN clients cl ON cl.id=p.client_id WHERE r.company_id=?''';params=[cid]
    if allowed is not None:
        if not allowed:q+=' AND 1=0'
        else:q+=' AND r.project_id IN ('+','.join('?' for _ in allowed)+')';params.extend(allowed)
    if project_filter.isdigit() and allowed_project(project_filter,allowed):q+=' AND r.project_id=?';params.append(int(project_filter))
    q+=' ORDER BY r.document_date DESC,r.id DESC';raw=c.execute(q,tuple(params)).fetchall();rows=[]
    for x in raw:
        d=dict(x);d['retention_total'],d['net_expected'],d['balance']=calc(x);d['state']=receivable_state(x,today);d['payments']=[dict(p) for p in c.execute('SELECT * FROM receivable_payments WHERE company_id=? AND receivable_id=? ORDER BY payment_date DESC,id DESC',(cid,x['id'])).fetchall()]
        if status=='Todos' or d['state']==status:rows.append(d)
    billed=sum(float(x['amount'] or 0) for x in raw);retained=sum(calc(x)[0] for x in raw);net_total=sum(calc(x)[1] for x in raw);collected=sum(float(x['paid_amount'] or 0) for x in raw);pending=sum(calc(x)[2] for x in raw);overdue=sum(calc(x)[2] for x in raw if calc(x)[2]>0 and x['due_date'] and x['due_date']<today)
    if allowed is None:projects=c.execute('SELECT id,name FROM projects WHERE company_id=? ORDER BY name',(cid,)).fetchall()
    elif not allowed:projects=[]
    else:projects=c.execute('SELECT id,name FROM projects WHERE company_id=? AND id IN ('+','.join('?' for _ in allowed)+') ORDER BY name',tuple([cid]+allowed)).fetchall()
    c.close();return render_template('receivables.html',rows=rows,projects=projects,billed=billed,retained=retained,net_total=net_total,collected=collected,pending=pending,overdue=overdue,today=today,status_filter=status,project_filter=project_filter)

@app.route('/receivables/<int:item_id>/payment',methods=['POST'])
@login_required
def receivable_payment(item_id):
    ensure_receivables_table();cid=session['company_id'];c=db();row=c.execute('SELECT * FROM project_receivables WHERE id=? AND company_id=?',(item_id,cid)).fetchone()
    if not row:c.close();return 'Cuenta no encontrada',404
    allowed=assigned_project_ids(c)
    if not allowed_project(row['project_id'],allowed):c.close();flash('Esta obra no está asignada a tu usuario.');return redirect(url_for('receivables'))
    try:value=float(request.form.get('payment',0) or 0)
    except ValueError:value=0
    balance=calc(row)[2]
    if value<=0 or value>balance:c.close();flash('El abono debe ser mayor a cero y no superar el neto pendiente.');return redirect(url_for('receivables'))
    payment_date=request.form.get('payment_date') or date.today().isoformat();method=request.form.get('payment_method','').strip();reference=request.form.get('reference','').strip();notes=request.form.get('payment_notes','').strip()
    c.execute('INSERT INTO receivable_payments(company_id,receivable_id,payment_date,amount,payment_method,reference,notes) VALUES(?,?,?,?,?,?,?)',(cid,item_id,payment_date,value,method,reference,notes));c.execute('UPDATE project_receivables SET paid_amount=paid_amount+? WHERE id=? AND company_id=?',(value,item_id,cid));c.commit();c.close();flash('Abono registrado en el historial.');return redirect(url_for('receivables'))

@app.route('/receivables/<int:item_id>/delete',methods=['POST'])
@login_required
def receivable_delete(item_id):
    ensure_receivables_table();cid=session['company_id'];c=db();row=c.execute('SELECT project_id FROM project_receivables WHERE id=? AND company_id=?',(item_id,cid)).fetchone()
    if not row:c.close();return 'Cuenta no encontrada',404
    allowed=assigned_project_ids(c)
    if not allowed_project(row['project_id'],allowed):c.close();flash('Esta obra no está asignada a tu usuario.');return redirect(url_for('receivables'))
    c.execute('DELETE FROM receivable_payments WHERE company_id=? AND receivable_id=?',(cid,item_id));c.execute('DELETE FROM project_receivables WHERE id=? AND company_id=?',(item_id,cid));c.commit();c.close();flash('Cuenta por cobrar y su historial eliminados.');return redirect(url_for('receivables'))

ensure_receivables_table()
