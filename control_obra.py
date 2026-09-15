from datetime import date
from flask import render_template,request,redirect,url_for,session,flash
from app import app,db,PG,login_required

def ensure_cost_table():
 c=db();pk='SERIAL PRIMARY KEY' if PG else 'INTEGER PRIMARY KEY AUTOINCREMENT';r='DOUBLE PRECISION' if PG else 'REAL'
 c.execute(f'''CREATE TABLE IF NOT EXISTS project_costs(id {pk},company_id INTEGER NOT NULL,project_id INTEGER NOT NULL,cost_date TEXT NOT NULL,category TEXT NOT NULL,description TEXT NOT NULL,supplier TEXT,amount {r} DEFAULT 0,payment_status TEXT DEFAULT 'Pagado')''');c.commit();c.close()

def project_budget_total(c,project_id,company_id):
 rows=c.execute('SELECT id FROM budgets WHERE project_id=? AND company_id=?',(project_id,company_id)).fetchall();total=0
 for b in rows:
  xs=c.execute('SELECT quantity,unit_price FROM budget_items WHERE budget_id=?',(b['id'],)).fetchall();total+=sum((x['quantity'] or 0)*(x['unit_price'] or 0) for x in xs)
 return total

@app.route('/project/<int:project_id>/control',methods=['GET','POST'])
@login_required
def project_control(project_id):
 ensure_cost_table();cid=session['company_id'];c=db();p=c.execute("SELECT p.*,COALESCE(cl.name,p.client,'') client_name FROM projects p LEFT JOIN clients cl ON cl.id=p.client_id WHERE p.id=? AND p.company_id=?",(project_id,cid)).fetchone()
 if not p:c.close();return 'Obra no encontrada',404
 if request.method=='POST':
  amount=float(request.form.get('amount',0) or 0)
  if amount<=0:c.close();flash('Ingresa un valor de costo mayor a cero.');return redirect(url_for('project_control',project_id=project_id))
  c.execute('INSERT INTO project_costs(company_id,project_id,cost_date,category,description,supplier,amount,payment_status) VALUES(?,?,?,?,?,?,?,?)',(cid,project_id,request.form.get('cost_date') or date.today().isoformat(),request.form.get('category','Otros'),request.form['description'].strip(),request.form.get('supplier','').strip(),amount,request.form.get('payment_status','Pagado')));c.commit();c.close();flash('Costo registrado.');return redirect(url_for('project_control',project_id=project_id))
 costs=c.execute('SELECT * FROM project_costs WHERE project_id=? AND company_id=? ORDER BY cost_date DESC,id DESC',(project_id,cid)).fetchall();actual=sum(x['amount'] or 0 for x in costs);paid=sum((x['amount'] or 0) for x in costs if x['payment_status']=='Pagado');pending=sum((x['amount'] or 0) for x in costs if x['payment_status']=='Pendiente');budget=project_budget_total(c,project_id,cid);has_budget=budget>0;contract=p['value'] or 0;expected_profit=(contract-budget) if has_budget else None;real_profit=contract-actual;deviation=(actual-budget) if has_budget else None;real_margin=(real_profit/contract*100) if contract else None;c.close()
 return render_template('project_control.html',project=p,costs=costs,budget=budget,has_budget=has_budget,actual=actual,paid=paid,pending=pending,expected_profit=expected_profit,real_profit=real_profit,deviation=deviation,real_margin=real_margin,today=date.today().isoformat())

@app.route('/project/<int:project_id>/cost/<int:cost_id>/delete',methods=['POST'])
@login_required
def project_cost_delete(project_id,cost_id):
 ensure_cost_table();c=db();c.execute('DELETE FROM project_costs WHERE id=? AND project_id=? AND company_id=?',(cost_id,project_id,session['company_id']));c.commit();c.close();flash('Costo eliminado.');return redirect(url_for('project_control',project_id=project_id))

ensure_cost_table()
