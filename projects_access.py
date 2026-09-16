from flask import render_template,request,session,redirect,flash
from app import app,db,company
from plans import plan_limit
from plan_capacity import sync_project_capacity,project_plan_enabled,set_project_plan_enabled

def _project_perm(c,user_id,action):
 if not user_id:return True
 col={'view':'can_view','create':'can_create','edit':'can_edit','delete':'can_delete'}.get(action,'can_view')
 p=c.execute(f'SELECT {col} ok FROM user_permissions WHERE user_id=? AND module=?',(user_id,'projects')).fetchone();return bool(p and p['ok'])

def _decorate_projects(rows,cid):
 return [{**dict(p),'plan_enabled':project_plan_enabled(cid,p['id'])} for p in rows]

# Vista de Obras: empleados solo ven asignadas; crear depende del permiso granular.
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
 if employee:
  rows=c.execute("""SELECT p.id,p.name,p.status,COALESCE(cl.name,p.client,'') client_name FROM projects p JOIN user_projects up ON up.project_id=p.id AND up.user_id=? LEFT JOIN clients cl ON cl.id=p.client_id WHERE p.company_id=? ORDER BY p.id DESC""",(uid,co['id'])).fetchall();can_create=_project_perm(c,uid,'create');cls=c.execute('SELECT * FROM clients WHERE company_id=? ORDER BY name',(co['id'],)).fetchall() if can_create else [];c.close();return render_template('projects_employee.html',projects=_decorate_projects(rows,co['id']),can_control='control' in perms,can_create=can_create,clients=cls)
 cls=c.execute('SELECT * FROM clients WHERE company_id=? ORDER BY name',(co['id'],)).fetchall();rows=c.execute("SELECT p.*,COALESCE(cl.name,p.client,'') client_name FROM projects p LEFT JOIN clients cl ON cl.id=p.client_id WHERE p.company_id=? ORDER BY p.id DESC",(co['id'],)).fetchall();c.close();limit=plan_limit(plan,'projects');return render_template('projects.html',projects=_decorate_projects(rows,co['id']),clients=cls,project_limit=limit,plan_name=plan)

@app.route('/projects/<int:project_id>/plan-access',methods=['POST'])
def project_plan_access(project_id):
 co=company()
 if not co:return redirect('/login')
 if session.get('user_id'):flash('Solo el administrador puede cambiar las obras operativas del plan.');return redirect('/projects')
 enabled=request.form.get('enabled')=='1';ok,msg=set_project_plan_enabled(co['id'],project_id,enabled,session.get('company_plan','Prueba'));flash(msg);return redirect('/projects')

app.view_functions['projects']=projects_secure
