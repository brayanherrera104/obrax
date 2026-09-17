from flask import render_template,request,session,redirect,flash
from app import app,db,company
from plans import plan_limit
from plan_capacity import sync_project_capacity,project_plan_enabled,set_project_plan_enabled


def _project_perm(c,user_id,action):
 if not user_id:return True
 col={'view':'can_view','create':'can_create','edit':'can_edit','delete':'can_delete'}.get(action,'can_view')
 p=c.execute(f'SELECT {col} ok FROM user_permissions WHERE user_id=? AND module=?',(user_id,'projects')).fetchone();return bool(p and p['ok'])


def _can_view_financials(c,user_id):
 if not user_id:return True
 for module in ('cashflow','receivables'):
  try:
   p=c.execute('SELECT can_view ok FROM user_permissions WHERE user_id=? AND module=?',(user_id,module)).fetchone()
   if p and p['ok']:return True
  except Exception:pass
 return False


def _project_metrics(c,cid,p,show_financials):
 pid=p['id'];contract=float(p['value'] or 0) if 'value' in p.keys() else 0
 try:budget=float(c.execute('''SELECT COALESCE(SUM(bi.quantity*bi.unit_price),0) total FROM budget_items bi JOIN budgets b ON b.id=bi.budget_id WHERE b.project_id=? AND b.company_id=?''',(pid,cid)).fetchone()['total'] or 0)
 except Exception:budget=0
 try:actual=float(c.execute('SELECT COALESCE(SUM(amount),0) total FROM project_costs WHERE project_id=? AND company_id=?',(pid,cid)).fetchone()['total'] or 0)
 except Exception:actual=0
 try:
  m=c.execute('SELECT progress FROM project_control_meta WHERE project_id=? AND company_id=?',(pid,cid)).fetchone();manual=float(m['progress'] or 0) if m else 0
 except Exception:manual=0
 progress=manual
 try:
  items=c.execute('''SELECT bi.id,(bi.quantity*bi.unit_price) total FROM budget_items bi JOIN budgets b ON b.id=bi.budget_id WHERE b.project_id=? AND b.company_id=?''',(pid,cid)).fetchall();total=sum(float(x['total'] or 0) for x in items);weighted=0;has_activity=False
  for x in items:
   r=c.execute('SELECT progress FROM project_activity_progress WHERE project_id=? AND company_id=? AND budget_item_id=?',(pid,cid,x['id'])).fetchone();pct=float(r['progress'] or 0) if r else 0
   if pct>0:has_activity=True
   weighted+=float(x['total'] or 0)*pct/100
  if has_activity and total>0:progress=weighted/total*100
 except Exception:pass
 target=(budget*progress/100) if budget>0 and progress>0 else None
 if budget<=0:health='Sin presupuesto';health_code='neutral'
 elif progress<=0:health='Sin avance';health_code='neutral'
 elif actual>target*1.05:health='Sobrecosto';health_code='danger'
 elif actual>=target*.90:health='Atención';health_code='warning'
 else:health='Controlado';health_code='success'
 data={'budget':budget,'actual':actual,'progress':progress,'available':budget-actual if budget else None,'health':health,'health_code':health_code}
 if show_financials:
  billed=collected=receivable_pending=0
  try:
   rows=c.execute('SELECT * FROM project_receivables WHERE project_id=? AND company_id=?',(pid,cid)).fetchall()
   for x in rows:
    gross=float(x['amount'] or 0);rf=float(x['retefuente_pct'] or 0);ri=float(x['reteica_pct'] or 0);rv=float(x['reteiva_pct'] or 0);other=float(x['other_withholding'] or 0);net=max(0,gross-(gross*(rf+ri+rv)/100+other));paid=float(x['paid_amount'] or 0);billed+=gross;collected+=paid;receivable_pending+=max(0,net-paid)
  except Exception:pass
  # Solo proyectamos cuando existen presupuesto y avance. Evita presentar el presupuesto
  # como si fuera una proyeccion real antes de que la obra tenga ejecucion medible.
  projected_cost=(actual/progress*100) if budget>0 and progress>0 else None;projected_profit=(contract-projected_cost) if projected_cost is not None and contract>0 else None;projected_margin=(projected_profit/contract*100) if projected_profit is not None and contract else None
  data.update({'billed':billed,'collected':collected,'receivable_pending':receivable_pending,'projected_cost':projected_cost,'projected_profit':projected_profit,'projected_margin':projected_margin})
 return data


def _decorate_projects(rows,cid,c=None,show_financials=False):
 out=[]
 for p in rows:
  item={**dict(p),'plan_enabled':project_plan_enabled(cid,p['id'])}
  if c is not None:item.update(_project_metrics(c,cid,p,show_financials))
  out.append(item)
 return out


def projects_secure():
 co=company()
 if not co:return redirect('/login')
 c=db();uid=session.get('user_id');employee=bool(uid);perms=set(session.get('permissions',[]));plan=session.get('company_plan','Prueba');sync_project_capacity(co['id'],plan)
 if request.method=='POST':
  if employee and not _project_perm(c,uid,'create'):
   c.close();flash('No tienes permiso para crear obras.');return redirect('/projects')
  ci=request.form.get('client_id') or None;cn='';z=c.execute('SELECT name FROM clients WHERE id=? AND company_id=?',(ci,co['id'])).fetchone() if ci else None;cn=z['name'] if z else ''
  if employee:
   c.execute('INSERT INTO projects(company_id,client_id,name,client,value,status) VALUES(?,?,?,?,?,?)',(co['id'],ci,request.form['name'],cn,0,request.form.get('status','En preparación')))
   try:
    pid=c.execute('SELECT id FROM projects WHERE company_id=? AND name=? ORDER BY id DESC LIMIT 1',(co['id'],request.form['name'])).fetchone()['id'];c.execute('INSERT INTO user_projects(user_id,project_id) VALUES(?,?)',(uid,pid))
   except Exception:pass
  else:c.execute('INSERT INTO projects(company_id,client_id,name,client,value,status) VALUES(?,?,?,?,?,?)',(co['id'],ci,request.form['name'],cn,float(request.form.get('value',0) or 0),request.form.get('status','En preparación')))
  c.commit();c.close();sync_project_capacity(co['id'],plan);flash('Obra creada correctamente.');return redirect('/projects')
 show_financials=_can_view_financials(c,uid)
 if employee:
  rows=c.execute("""SELECT p.*,COALESCE(cl.name,p.client,'') client_name FROM projects p JOIN user_projects up ON up.project_id=p.id AND up.user_id=? LEFT JOIN clients cl ON cl.id=p.client_id WHERE p.company_id=? ORDER BY p.id DESC""",(uid,co['id'])).fetchall();can_create=_project_perm(c,uid,'create');cls=c.execute('SELECT * FROM clients WHERE company_id=? ORDER BY name',(co['id'],)).fetchall() if can_create else [];projects=_decorate_projects(rows,co['id'],c,show_financials);c.close();return render_template('projects_employee.html',projects=projects,can_control='control' in perms,can_create=can_create,clients=cls,can_view_financials=show_financials)
 cls=c.execute('SELECT * FROM clients WHERE company_id=? ORDER BY name',(co['id'],)).fetchall();rows=c.execute("SELECT p.*,COALESCE(cl.name,p.client,'') client_name FROM projects p LEFT JOIN clients cl ON cl.id=p.client_id WHERE p.company_id=? ORDER BY p.id DESC",(co['id'],)).fetchall();projects=_decorate_projects(rows,co['id'],c,True);c.close();limit=plan_limit(plan,'projects');return render_template('projects.html',projects=projects,clients=cls,project_limit=limit,plan_name=plan,can_view_financials=True)


@app.route('/projects/<int:project_id>/plan-access',methods=['POST'])
def project_plan_access(project_id):
 co=company()
 if not co:return redirect('/login')
 if session.get('user_id'):flash('Solo el administrador puede cambiar las obras operativas del plan.');return redirect('/projects')
 enabled=request.form.get('enabled')=='1';ok,msg=set_project_plan_enabled(co['id'],project_id,enabled,session.get('company_plan','Prueba'));flash(msg);return redirect('/projects')


app.view_functions['projects']=projects_secure
