from datetime import date
from flask import render_template, request, redirect, url_for, session, flash
from app import app, db, PG, login_required


def ensure_receivables_table():
    c = db()
    pk = 'SERIAL PRIMARY KEY' if PG else 'INTEGER PRIMARY KEY AUTOINCREMENT'
    real = 'DOUBLE PRECISION' if PG else 'REAL'
    c.execute(f'''CREATE TABLE IF NOT EXISTS project_receivables(
        id {pk}, company_id INTEGER NOT NULL, project_id INTEGER NOT NULL,
        concept TEXT NOT NULL, document_date TEXT NOT NULL, due_date TEXT,
        amount {real} DEFAULT 0, paid_amount {real} DEFAULT 0, notes TEXT
    )''')
    c.commit(); c.close()


def receivable_state(row, today):
    balance = max(0, float(row['amount'] or 0) - float(row['paid_amount'] or 0))
    if balance <= 0: return 'Cobrado'
    if row['due_date'] and row['due_date'] < today: return 'Vencido'
    return 'Pendiente'


@app.route('/receivables', methods=['GET','POST'])
@login_required
def receivables():
    ensure_receivables_table(); cid=session['company_id']; c=db()
    if request.method == 'POST':
        try:
            amount=float(request.form.get('amount',0) or 0); paid=float(request.form.get('paid_amount',0) or 0)
        except ValueError:
            amount=0; paid=0
        project_id=request.form.get('project_id',''); concept=request.form.get('concept','').strip()
        project=c.execute('SELECT id FROM projects WHERE id=? AND company_id=?',(project_id,cid)).fetchone() if project_id.isdigit() else None
        if not project or not concept or amount <= 0:
            c.close(); flash('Selecciona una obra, escribe el concepto e ingresa un valor mayor a cero.'); return redirect(url_for('receivables'))
        paid=max(0,min(paid,amount))
        c.execute('INSERT INTO project_receivables(company_id,project_id,concept,document_date,due_date,amount,paid_amount,notes) VALUES(?,?,?,?,?,?,?,?)',(cid,int(project_id),concept,request.form.get('document_date') or date.today().isoformat(),request.form.get('due_date') or None,amount,paid,request.form.get('notes','').strip()))
        c.commit(); c.close(); flash('Cuenta por cobrar registrada.'); return redirect(url_for('receivables'))
    status=request.args.get('status','Todos'); project_filter=request.args.get('project_id',''); today=date.today().isoformat()
    q='''SELECT r.*,p.name project_name,COALESCE(cl.name,p.client,'') client_name FROM project_receivables r JOIN projects p ON p.id=r.project_id LEFT JOIN clients cl ON cl.id=p.client_id WHERE r.company_id=?'''; params=[cid]
    if project_filter.isdigit(): q+=' AND r.project_id=?'; params.append(int(project_filter))
    q+=' ORDER BY r.document_date DESC,r.id DESC'; raw=c.execute(q,tuple(params)).fetchall(); rows=[]
    for x in raw:
        d=dict(x); d['balance']=max(0,float(x['amount'] or 0)-float(x['paid_amount'] or 0)); d['state']=receivable_state(x,today)
        if status=='Todos' or d['state']==status: rows.append(d)
    totals=c.execute('SELECT amount,paid_amount,due_date FROM project_receivables WHERE company_id=?',(cid,)).fetchall()
    billed=sum(float(x['amount'] or 0) for x in totals); collected=sum(float(x['paid_amount'] or 0) for x in totals)
    pending=sum(max(0,float(x['amount'] or 0)-float(x['paid_amount'] or 0)) for x in totals)
    overdue=sum(max(0,float(x['amount'] or 0)-float(x['paid_amount'] or 0)) for x in totals if float(x['amount'] or 0)>float(x['paid_amount'] or 0) and x['due_date'] and x['due_date']<today)
    projects=c.execute('SELECT id,name FROM projects WHERE company_id=? ORDER BY name',(cid,)).fetchall(); c.close()
    return render_template('receivables.html',rows=rows,projects=projects,billed=billed,collected=collected,pending=pending,overdue=overdue,today=today,status_filter=status,project_filter=project_filter)


@app.route('/receivables/<int:item_id>/payment', methods=['POST'])
@login_required
def receivable_payment(item_id):
    ensure_receivables_table(); cid=session['company_id']; c=db(); row=c.execute('SELECT amount,paid_amount FROM project_receivables WHERE id=? AND company_id=?',(item_id,cid)).fetchone()
    if not row: c.close(); return 'Cuenta no encontrada',404
    try: value=float(request.form.get('payment',0) or 0)
    except ValueError: value=0
    balance=max(0,float(row['amount'] or 0)-float(row['paid_amount'] or 0))
    if value<=0 or value>balance:
        c.close(); flash('El abono debe ser mayor a cero y no superar el saldo pendiente.'); return redirect(url_for('receivables'))
    c.execute('UPDATE project_receivables SET paid_amount=paid_amount+? WHERE id=? AND company_id=?',(value,item_id,cid)); c.commit(); c.close(); flash('Abono registrado correctamente.'); return redirect(url_for('receivables'))


@app.route('/receivables/<int:item_id>/delete', methods=['POST'])
@login_required
def receivable_delete(item_id):
    ensure_receivables_table(); c=db(); c.execute('DELETE FROM project_receivables WHERE id=? AND company_id=?',(item_id,session['company_id'])); c.commit(); c.close(); flash('Cuenta por cobrar eliminada.'); return redirect(url_for('receivables'))

ensure_receivables_table()
