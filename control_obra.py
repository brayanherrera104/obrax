from datetime import date
from flask import render_template,request,redirect,url_for,session,flash
from app import app,db,PG,login_required

def ensure_cost_table():
 c=db();pk='SERIAL PRIMARY KEY' if PG else 'INTEGER PRIMARY KEY AUTOINCREMENT';r='DOUBLE PRECISION' if PG else 'REAL'
 c.execute(f'''CREATE TABLE IF NOT EXISTS project_costs(id {pk},company_id INTEGER NOT NULL,project_id INTEGER NOT NULL,cost_date TEXT NOT NULL,category TEXT NOT NULL,description TEXT NOT NULL,supplier TEXT,amount {r} DEFAULT 0,payment_status TEXT DEFAULT 'Pagado')''')
 for sql in ['ALTER TABLE project_costs ADD COLUMN budget_item_id INTEGER','ALTER TABLE project_costs ADD COLUMN due_date TEXT']:
  try:c.execute(sql);c.commit()
  except Exception:c.rollback()
 c.execute(f'''CREATE TABLE IF NOT EXISTS project_control_meta(project_id INTEGER PRIMARY KEY,company_id INTEGER NOT NULL,progress {r} DEFAULT 0,updated_at TEXT)''')
 c.execute(f'''CREATE TABLE IF NOT EXISTS project_activity_progress(project_id INTEGER NOT NULL,company_id INTEGER NOT NULL,budget_item_id INTEGER NOT NULL,progress {r} DEFAULT 0,updated_at TEXT,PRIMARY KEY(project_id,budget_item_id))''');c.commit();c.close()

def project_budget_items(c,project_id,company_id):return c.execute('''SELECT bi.id,bi.description,bi.unit,bi.quantity,bi.unit_price,(bi.quantity*bi.unit_price) total FROM budget_items bi JOIN budgets b ON b.id=bi.budget_id WHERE b.project_id=? AND b.company_id=? ORDER BY bi.id''',(project_id,company_id)).fetchall()
def manual_progress(c,project_id,company_id):
 m=c.execute('SELECT progress FROM project_control_meta WHERE project_id=? AND company_id=?',(project_id,company_id)).fetchone();return float(m['progress'] or 0) if m else 0
def activity_data(c,project_id,company_id):
 items=project_budget_items(c,project_id,company_id);rows=[];weighted=0;total=sum((x['total'] or 0) for x in items)
 for x in items:
  r=c.execute('SELECT progress FROM project_activity_progress WHERE project_id=? AND company_id=? AND budget_item_id=?',(project_id,company_id,x['id'])).fetchone();pct=float(r['progress'] or 0) if r else 0;value=x['total'] or 0;weighted+=value*pct/100
  cr=c.execute('SELECT COALESCE(SUM(amount),0) real_cost FROM project_costs WHERE project_id=? AND company_id=? AND budget_item_id=?',(project_id,company_id,x['id'])).fetchone();real=float(cr['real_cost'] or 0);target=value*pct/100;dev=real-target;consumption=(real/target*100) if target>0 else (100 if real>0 else 0)
  if pct<=0 and real>0:traffic='red';status='Costo sin avance';alert='Hay costos registrados pero la actividad no tiene avance reportado.'
  elif target<=0:traffic='gray';status='Sin datos';alert='Registra avance para evaluar el desempeño.'
  elif consumption>105:traffic='red';status='Sobrecosto';alert='El costo real supera el costo esperado para el avance actual.'
  elif consumption>=90:traffic='yellow';status='Atención';alert='El costo está cerca del límite esperado para este avance.'
  else:traffic='green';status='Controlado';alert='El costo registrado está por debajo del esperado para este avance.'
  rows.append({'id':x['id'],'description':x['description'],'unit':x['unit'],'quantity':x['quantity'],'total':value,'progress':pct,'weight':(value/total*100 if total else 0),'real_cost':real,'target_cost':target,'deviation':dev,'consumption':consumption,'traffic':traffic,'cost_status':status,'alert':alert})
 return rows,(weighted/total*100 if total else 0)

@app.route('/project/<int:project_id>/progress',methods=['POST'])
@login_required
def project_progress(project_id):
 ensure_cost_table();cid=session['company_id'];progress=max(0,min(100,float(request.form.get('progress',0) or 0)));c=db();p=c.execute('SELECT id FROM projects WHERE id=? AND company_id=?',(project_id,cid)).fetchone()
 if not p:c.close();return 'Obra no encontrada',404
 old=c.execute('SELECT project_id FROM project_control_meta WHERE project_id=? AND company_id=?',(project_id,cid)).fetchone()
 if old:c.execute('UPDATE project_control_meta SET progress=?,updated_at=? WHERE project_id=? AND company_id=?',(progress,date.today().isoformat(),project_id,cid))
 else:c.execute('INSERT INTO project_control_meta(project_id,company_id,progress,updated_at) VALUES(?,?,?,?)',(project_id,cid,progress,date.today().isoformat()))
 c.commit();c.close();flash('Avance manual actualizado.');return redirect(url_for('project_control',project_id=project_id))
@app.route('/project/<int:project_id>/activity-progress',methods=['POST'])
@login_required
def activity_progress(project_id):
 ensure_cost_table();cid=session['company_id'];c=db();valid={x['id'] for x in project_budget_items(c,project_id,cid)}
 for key,value in request.form.items():
  if not key.startswith('activity_'):continue
  try:item_id=int(key.split('_',1)[1]);pct=max(0,min(100,float(value or 0)))
  except:continue
  if item_id not in valid:continue
  old=c.execute('SELECT budget_item_id FROM project_activity_progress WHERE project_id=? AND company_id=? AND budget_item_id=?',(project_id,cid,item_id)).fetchone()
  if old:c.execute('UPDATE project_activity_progress SET progress=?,updated_at=? WHERE project_id=? AND company_id=? AND budget_item_id=?',(pct,date.today().isoformat(),project_id,cid,item_id))
  else:c.execute('INSERT INTO project_activity_progress(project_id,company_id,budget_item_id,progress,updated_at) VALUES(?,?,?,?,?)',(project_id,cid,item_id,pct,date.today().isoformat()))
 c.commit();c.close();flash('Avance por actividades actualizado.');return redirect(url_for('project_control',project_id=project_id))

@app.route('/project/<int:project_id>/control',methods=['GET','POST'])
@login_required
def project_control(project_id):
 ensure_cost_table();cid=session['company_id'];c=db();p=c.execute("SELECT p.*,COALESCE(cl.name,p.client,'') client_name FROM projects p LEFT JOIN clients cl ON cl.id=p.client_id WHERE p.id=? AND p.company_id=?",(project_id,cid)).fetchone()
 if not p:c.close();return 'Obra no encontrada',404
 budget_items=project_budget_items(c,project_id,cid);valid_ids={x['id'] for x in budget_items}
 if request.method=='POST':
  amount=float(request.form.get('amount',0) or 0)
  if amount<=0:c.close();flash('Ingresa un valor de costo mayor a cero.');return redirect(url_for('project_control',project_id=project_id))
  raw=request.form.get('budget_item_id','').strip();item_id=int(raw) if raw.isdigit() and int(raw) in valid_ids else None;status=request.form.get('payment_status','Pagado');due=request.form.get('due_date') or None
  if status=='Pagado':due=None
  c.execute('INSERT INTO project_costs(company_id,project_id,cost_date,category,description,supplier,amount,payment_status,budget_item_id,due_date) VALUES(?,?,?,?,?,?,?,?,?,?)',(cid,project_id,request.form.get('cost_date') or date.today().isoformat(),request.form.get('category','Otros'),request.form['description'].strip(),request.form.get('supplier','').strip(),amount,status,item_id,due));c.commit();c.close();flash('Costo registrado y asignado a la actividad.');return redirect(url_for('project_control',project_id=project_id))
 costs=c.execute('''SELECT pc.*,bi.description activity_name FROM project_costs pc LEFT JOIN budget_items bi ON bi.id=pc.budget_item_id WHERE pc.project_id=? AND pc.company_id=? ORDER BY pc.cost_date DESC,pc.id DESC''',(project_id,cid)).fetchall();actual=sum(x['amount'] or 0 for x in costs);paid=sum((x['amount'] or 0) for x in costs if x['payment_status']=='Pagado');pending=sum((x['amount'] or 0) for x in costs if x['payment_status']=='Pendiente');activities,weighted_progress=activity_data(c,project_id,cid);budget=sum(x['total'] for x in activities);has_budget=budget>0;manual=manual_progress(c,project_id,cid);has_activity_progress=any(x['progress']>0 for x in activities);progress=weighted_progress if has_activity_progress else manual;progress_source='Actividades' if has_activity_progress else 'Manual';target_cost=(budget*progress/100) if has_budget else None;progress_deviation=(actual-target_cost) if has_budget else None
 if not has_budget:health='Sin presupuesto'
 elif progress<=0:health='Sin avance reportado'
 elif progress_deviation > target_cost*0.05:health='Sobre presupuesto'
 elif progress_deviation < -target_cost*0.05:health='Por debajo del presupuesto'
 else:health='Dentro del presupuesto'
 contract=p['value'] or 0;expected_profit=(contract-budget) if has_budget else None;real_profit=contract-actual;real_margin=(real_profit/contract*100) if contract else None;c.close();return render_template('project_control.html',project=p,costs=costs,budget=budget,has_budget=has_budget,actual=actual,paid=paid,pending=pending,expected_profit=expected_profit,real_profit=real_profit,real_margin=real_margin,progress=progress,manual_progress=manual,progress_source=progress_source,target_cost=target_cost,progress_deviation=progress_deviation,health=health,activities=activities,today=date.today().isoformat())

@app.route('/project/<int:project_id>/cost/<int:cost_id>/edit',methods=['POST'])
@login_required
def project_cost_edit(project_id,cost_id):
 ensure_cost_table();cid=session['company_id'];c=db();cost=c.execute('SELECT id FROM project_costs WHERE id=? AND project_id=? AND company_id=?',(cost_id,project_id,cid)).fetchone()
 if not cost:c.close();return 'Movimiento no encontrado',404
 valid_ids={x['id'] for x in project_budget_items(c,project_id,cid)}
 try:amount=float(request.form.get('amount',0) or 0)
 except:amount=0
 if amount<=0:c.close();flash('El valor debe ser mayor a cero.');return redirect(url_for('project_control',project_id=project_id))
 raw=request.form.get('budget_item_id','').strip();item_id=int(raw) if raw.isdigit() and int(raw) in valid_ids else None;category=request.form.get('category','Otros');status=request.form.get('payment_status','Pagado');due=request.form.get('due_date') or None
 if category not in ['Materiales','Mano de obra','Equipos','Transporte','Subcontratos','Otros']:category='Otros'
 if status not in ['Pagado','Pendiente']:status='Pagado'
 if status=='Pagado':due=None
 description=request.form.get('description','').strip()
 if not description:c.close();flash('La descripción es obligatoria.');return redirect(url_for('project_control',project_id=project_id))
 c.execute('''UPDATE project_costs SET cost_date=?,budget_item_id=?,category=?,description=?,supplier=?,amount=?,payment_status=?,due_date=? WHERE id=? AND project_id=? AND company_id=?''',(request.form.get('cost_date') or date.today().isoformat(),item_id,category,description,request.form.get('supplier','').strip(),amount,status,due,cost_id,project_id,cid));c.commit();c.close();flash('Movimiento actualizado correctamente.');return redirect(url_for('project_control',project_id=project_id))
@app.route('/project/<int:project_id>/cost/<int:cost_id>/delete',methods=['POST'])
@login_required
def project_cost_delete(project_id,cost_id):
 ensure_cost_table();c=db();c.execute('DELETE FROM project_costs WHERE id=? AND project_id=? AND company_id=?',(cost_id,project_id,session['company_id']));c.commit();c.close();flash('Costo eliminado.');return redirect(url_for('project_control',project_id=project_id))

@app.route('/payables')
@login_required
def payables():
 ensure_cost_table();cid=session['company_id'];c=db();status=request.args.get('status','Todos');project=request.args.get('project_id','');supplier=request.args.get('supplier','').strip();q='''SELECT pc.*,p.name project_name,bi.description activity_name FROM project_costs pc JOIN projects p ON p.id=pc.project_id LEFT JOIN budget_items bi ON bi.id=pc.budget_item_id WHERE pc.company_id=?''';params=[cid]
 if status=='Pendiente':q+=' AND pc.payment_status=?';params.append('Pendiente')
 elif status=='Pagado':q+=' AND pc.payment_status=?';params.append('Pagado')
 elif status=='Vencido':q+=" AND pc.payment_status='Pendiente' AND pc.due_date IS NOT NULL AND pc.due_date<>'' AND pc.due_date<?";params.append(date.today().isoformat())
 if project.isdigit():q+=' AND pc.project_id=?';params.append(int(project))
 if supplier:q+=" AND LOWER(COALESCE(pc.supplier,'')) LIKE ?";params.append('%'+supplier.lower()+'%')
 q+=" ORDER BY CASE WHEN pc.payment_status='Pendiente' THEN 0 ELSE 1 END,pc.due_date,pc.cost_date DESC";rows=c.execute(q,tuple(params)).fetchall();allrows=c.execute('SELECT amount,payment_status,due_date FROM project_costs WHERE company_id=?',(cid,)).fetchall();projects=c.execute('SELECT id,name FROM projects WHERE company_id=? ORDER BY name',(cid,)).fetchall();today=date.today().isoformat();total=sum(x['amount'] or 0 for x in allrows);paid=sum((x['amount'] or 0) for x in allrows if x['payment_status']=='Pagado');pending=sum((x['amount'] or 0) for x in allrows if x['payment_status']=='Pendiente');overdue=sum((x['amount'] or 0) for x in allrows if x['payment_status']=='Pendiente' and x['due_date'] and x['due_date']<today);c.close();return render_template('payables.html',rows=rows,projects=projects,total=total,paid=paid,pending=pending,overdue=overdue,today=today,status_filter=status,project_filter=project,supplier_filter=supplier)
@app.route('/payables/<int:cost_id>/pay',methods=['POST'])
@login_required
def payable_pay(cost_id):
 ensure_cost_table();c=db();c.execute("UPDATE project_costs SET payment_status='Pagado',due_date=NULL WHERE id=? AND company_id=?",(cost_id,session['company_id']));c.commit();c.close();flash('Cuenta marcada como pagada.');return redirect(request.referrer or url_for('payables'))
ensure_cost_table()
