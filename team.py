from flask import render_template,request,redirect,session,flash
from functools import wraps
from werkzeug.security import generate_password_hash,check_password_hash
from app import app,db,PG
from plan_capacity import sync_user_capacity,user_plan_enabled
from plans import plan_limit

MODULES=[('dashboard','Dashboard'),('apus','APUs'),('clients','Clientes'),('projects','Obras'),('budgets','Presupuestos'),('quotations','Cotizaciones'),('control','Control de obra'),('payables','Por pagar'),('receivables','Por cobrar'),('cashflow','Flujo de caja')]
ACTIONS=('view','create','edit','delete')
ROLE_DEFAULTS={'Gerente':{k:['view','create','edit'] for k,_ in MODULES},'Administrativo':{k:['view','create','edit'] for k in ['dashboard','clients','projects','budgets','quotations','payables','receivables','cashflow']},'Residente':{'dashboard':['view'],'projects':['view'],'control':['view','create','edit'],'apus':['view']},'Consulta':{'dashboard':['view'],'projects':['view'],'control':['view']}}
PATH_MODULES=[('/cashflow','cashflow'),('/receivables','receivables'),('/payables','payables'),('/quotations','quotations'),('/quotation/','quotations'),('/budgets','budgets'),('/budget/','budgets'),('/clients','clients'),('/apus','apus'),('/apu/','apus'),('/projects','projects'),('/project/','control'),('/dashboard','dashboard')]

def ensure_team_tables():
 c=db();pk='SERIAL PRIMARY KEY' if PG else 'INTEGER PRIMARY KEY AUTOINCREMENT';c.execute(f'''CREATE TABLE IF NOT EXISTS company_users(id {pk},company_id INTEGER NOT NULL,name TEXT NOT NULL,email TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,role TEXT DEFAULT 'Consulta',is_active INTEGER DEFAULT 1)''');c.execute('''CREATE TABLE IF NOT EXISTS user_permissions(user_id INTEGER NOT NULL,module TEXT NOT NULL,can_view INTEGER DEFAULT 0,can_create INTEGER DEFAULT 0,can_edit INTEGER DEFAULT 0,can_delete INTEGER DEFAULT 0,PRIMARY KEY(user_id,module))''');c.execute('''CREATE TABLE IF NOT EXISTS user_projects(user_id INTEGER NOT NULL,project_id INTEGER NOT NULL,PRIMARY KEY(user_id,project_id))''');c.commit();c.close()
def employee_permission(module,action='view'):
 if not session.get('user_id'):return True
 c=db();u=c.execute('SELECT is_active FROM company_users WHERE id=? AND company_id=?',(session['user_id'],session['company_id'])).fetchone()
 if not u or not u['is_active']:c.close();return False
 col={'view':'can_view','create':'can_create','edit':'can_edit','delete':'can_delete'}.get(action,'can_view');p=c.execute(f'SELECT {col} ok FROM user_permissions WHERE user_id=? AND module=?',(session['user_id'],module)).fetchone();c.close();return bool(p and p['ok'])
def employee_project_allowed(project_id):
 if not session.get('user_id'):return True
 c=db();x=c.execute('SELECT 1 ok FROM user_projects WHERE user_id=? AND project_id=?',(session['user_id'],project_id)).fetchone();c.close();return bool(x)
def company_admin_required(f):
 @wraps(f)
 def w(*a,**k):
  if not session.get('company_id'):return redirect('/login')
  if session.get('user_id'):flash('Solo el administrador de la empresa puede gestionar el equipo.');return redirect('/dashboard')
  return f(*a,**k)
 return w
def posted_permissions(form):
 result={}
 for key,_ in MODULES:
  acts=[action for action in ACTIONS if form.get(f'perm_{key}_{action}')=='1']
  if any(a in acts for a in ('create','edit','delete')) and 'view' not in acts:acts.insert(0,'view')
  result[key]=acts
 return result
def set_permissions(c,user_id,permissions):
 c.execute('DELETE FROM user_permissions WHERE user_id=?',(user_id,))
 for key,_ in MODULES:
  acts=set(permissions.get(key,[]));c.execute('INSERT INTO user_permissions(user_id,module,can_view,can_create,can_edit,can_delete) VALUES(?,?,?,?,?,?)',(user_id,key,int('view' in acts),int('create' in acts),int('edit' in acts),int('delete' in acts)))
def set_projects(c,user_id,projects):
 c.execute('DELETE FROM user_projects WHERE user_id=?',(user_id,))
 for x in projects:
  if str(x).isdigit():c.execute('INSERT INTO user_projects(user_id,project_id) VALUES(?,?)',(user_id,int(x)))
@app.before_request
def team_access_guard():
 ensure_team_tables()
 if not session.get('user_id'):return None
 path=request.path
 if path in ['/logout','/login','/account/password'] or path.startswith('/static/'):return None
 module=next((m for prefix,m in PATH_MODULES if path==prefix or path.startswith(prefix)),None)
 if module:
  action='view'
  if request.method=='POST':
   if '/delete' in path:action='delete'
   elif '/edit' in path or '/progress' in path or '/payment' in path or '/pay' in path:action='edit'
   else:action='create'
  if not employee_permission(module,action):flash('No tienes permiso para realizar esta acción.');return redirect('/dashboard')
  if path.startswith('/project/'):
   try:pid=int(path.split('/')[2])
   except:pid=None
   if pid and not employee_project_allowed(pid):flash('Esta obra no está asignada a tu usuario.');return redirect('/projects')
 return None
@app.route('/team',methods=['GET','POST'])
@company_admin_required
def team():
 ensure_team_tables();cid=session['company_id'];c=db()
 if request.method=='POST':
  name=request.form.get('name','').strip();email=request.form.get('email','').strip().lower();password=request.form.get('password','');role=request.form.get('role','Consulta')
  if not name or not email or len(password)<6:c.close();flash('Nombre, correo y contraseña de mínimo 6 caracteres son obligatorios.');return redirect('/team')
  try:
   if PG:u=c.execute('INSERT INTO company_users(company_id,name,email,password_hash,role,is_active) VALUES(?,?,?,?,?,1) RETURNING id',(cid,name,email,generate_password_hash(password),role)).fetchone()['id']
   else:u=c.execute('INSERT INTO company_users(company_id,name,email,password_hash,role,is_active) VALUES(?,?,?,?,?,1)',(cid,name,email,generate_password_hash(password),role)).lastrowid
   set_permissions(c,u,posted_permissions(request.form));set_projects(c,u,request.form.getlist('projects'));c.commit();flash('Usuario creado con sus permisos y obras asignadas.')
  except Exception:c.rollback();flash('No se pudo crear el usuario. Verifica que el correo no esté registrado.')
  c.close();return redirect('/team')
 users=c.execute('SELECT * FROM company_users WHERE company_id=? ORDER BY name',(cid,)).fetchall();projects=c.execute('SELECT id,name FROM projects WHERE company_id=? ORDER BY name',(cid,)).fetchall();data=[];c.close();plan=session.get('company_plan','Prueba');sync_user_capacity(cid,plan);c=db()
 for u in users:
  d=dict(u);d['plan_enabled']=user_plan_enabled(cid,u['id']);d['permissions']={}
  for x in c.execute('SELECT * FROM user_permissions WHERE user_id=?',(u['id'],)).fetchall():d['permissions'][x['module']]={'view':bool(x['can_view']),'create':bool(x['can_create']),'edit':bool(x['can_edit']),'delete':bool(x['can_delete'])}
  d['projects']=[x['project_id'] for x in c.execute('SELECT project_id FROM user_projects WHERE user_id=?',(u['id'],)).fetchall()];data.append(d)
 c.close();total_users=len(data);operational_users=sum(1 for u in data if u['plan_enabled']);out_of_plan=total_users-operational_users;limit=plan_limit(plan,'users')
 user_summary={'plan':plan,'total':total_users,'operational':operational_users,'out_of_plan':out_of_plan,'limit':limit,'limit_text':'Ilimitados' if limit is None else str(limit)}
 return render_template('team.html',users=data,projects=projects,modules=MODULES,role_defaults=ROLE_DEFAULTS,user_summary=user_summary)
@app.route('/team/<int:user_id>/update',methods=['POST'])
@company_admin_required
def team_update(user_id):
 ensure_team_tables();cid=session['company_id'];c=db();u=c.execute('SELECT id FROM company_users WHERE id=? AND company_id=?',(user_id,cid)).fetchone()
 if not u:c.close();return 'Usuario no encontrado',404
 role=request.form.get('role','Consulta');active=1 if request.form.get('is_active')=='1' else 0;c.execute('UPDATE company_users SET name=?,role=?,is_active=? WHERE id=? AND company_id=?',(request.form.get('name','').strip(),role,active,user_id,cid));set_permissions(c,user_id,posted_permissions(request.form));set_projects(c,user_id,request.form.getlist('projects'));c.commit();c.close();flash('Permisos del usuario actualizados.');return redirect('/team')

@app.route('/team/<int:user_id>/password',methods=['POST'])
@company_admin_required
def team_password(user_id):
 cid=session['company_id'];password=request.form.get('new_password','')
 if len(password)<6:flash('La nueva contraseña debe tener mínimo 6 caracteres.');return redirect('/team')
 c=db();u=c.execute('SELECT id FROM company_users WHERE id=? AND company_id=?',(user_id,cid)).fetchone()
 if not u:c.close();flash('Usuario no encontrado.');return redirect('/team')
 c.execute('UPDATE company_users SET password_hash=? WHERE id=? AND company_id=?',(generate_password_hash(password),user_id,cid));c.commit();c.close();flash('Contraseña temporal actualizada. El usuario ya puede ingresar con la nueva contraseña.');return redirect('/team')

@app.route('/team/<int:user_id>/delete',methods=['POST'])
@company_admin_required
def team_delete(user_id):
 cid=session['company_id'];c=db();u=c.execute('SELECT id,name FROM company_users WHERE id=? AND company_id=?',(user_id,cid)).fetchone()
 if not u:c.close();flash('Usuario no encontrado.');return redirect('/team')
 c.execute('DELETE FROM user_permissions WHERE user_id=?',(user_id,));c.execute('DELETE FROM user_projects WHERE user_id=?',(user_id,));c.execute('DELETE FROM company_users WHERE id=? AND company_id=?',(user_id,cid));c.commit();c.close();sync_user_capacity(cid,session.get('company_plan','Prueba'));flash(f'Usuario {u["name"]} eliminado. El cupo quedó disponible.');return redirect('/team')

@app.route('/account/password',methods=['GET','POST'])
def account_password():
 if not session.get('company_id'):return redirect('/login')
 if request.method=='GET':return render_template('change_password.html')
 current=request.form.get('current_password','');new=request.form.get('new_password','');confirm=request.form.get('confirm_password','')
 if len(new)<6:flash('La nueva contraseña debe tener mínimo 6 caracteres.');return redirect('/account/password')
 if new!=confirm:flash('Las contraseñas nuevas no coinciden.');return redirect('/account/password')
 c=db()
 if session.get('user_id'):
  row=c.execute('SELECT password_hash FROM company_users WHERE id=? AND company_id=?',(session['user_id'],session['company_id'])).fetchone();table='company_users';where_id=session['user_id']
 else:
  row=c.execute('SELECT password_hash FROM companies WHERE id=?',(session['company_id'],)).fetchone();table='companies';where_id=session['company_id']
 if not row or not check_password_hash(row['password_hash'],current):c.close();flash('La contraseña actual no es correcta.');return redirect('/account/password')
 c.execute(f'UPDATE {table} SET password_hash=? WHERE id=?',(generate_password_hash(new),where_id));c.commit();c.close();flash('Contraseña actualizada correctamente.');return redirect('/dashboard')
ensure_team_tables()
