from flask import render_template,request,redirect,url_for,session,flash
from functools import wraps
from werkzeug.security import generate_password_hash
from app import app,db,PG,login_required

MODULES=[('dashboard','Dashboard'),('apus','APUs'),('clients','Clientes'),('projects','Obras'),('budgets','Presupuestos'),('quotations','Cotizaciones'),('control','Control de obra'),('payables','Por pagar'),('receivables','Por cobrar'),('cashflow','Flujo de caja')]
ROLE_DEFAULTS={
 'Gerente':[x[0] for x in MODULES],
 'Administrativo':['dashboard','clients','projects','budgets','quotations','payables','receivables','cashflow'],
 'Residente':['dashboard','projects','control','apus'],
 'Consulta':['dashboard','projects','control']
}

def ensure_team_tables():
 c=db();pk='SERIAL PRIMARY KEY' if PG else 'INTEGER PRIMARY KEY AUTOINCREMENT'
 c.execute(f'''CREATE TABLE IF NOT EXISTS company_users(id {pk},company_id INTEGER NOT NULL,name TEXT NOT NULL,email TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,role TEXT DEFAULT 'Consulta',is_active INTEGER DEFAULT 1)''')
 c.execute('''CREATE TABLE IF NOT EXISTS user_permissions(user_id INTEGER NOT NULL,module TEXT NOT NULL,can_view INTEGER DEFAULT 0,can_create INTEGER DEFAULT 0,can_edit INTEGER DEFAULT 0,can_delete INTEGER DEFAULT 0,PRIMARY KEY(user_id,module))''')
 c.execute('''CREATE TABLE IF NOT EXISTS user_projects(user_id INTEGER NOT NULL,project_id INTEGER NOT NULL,PRIMARY KEY(user_id,project_id))''');c.commit();c.close()

def company_admin_required(f):
 @wraps(f)
 def w(*a,**k):
  if not session.get('company_id'):return redirect(url_for('login'))
  if session.get('user_id'):flash('Solo el administrador de la empresa puede gestionar el equipo.');return redirect(url_for('dashboard'))
  return f(*a,**k)
 return w

def set_permissions(c,user_id,modules,role):
 c.execute('DELETE FROM user_permissions WHERE user_id=?',(user_id,))
 allowed=set(modules or ROLE_DEFAULTS.get(role,[]))
 for key,_ in MODULES:
  v=1 if key in allowed else 0;c.execute('INSERT INTO user_permissions(user_id,module,can_view,can_create,can_edit,can_delete) VALUES(?,?,?,?,?,?)',(user_id,key,v,v,v,0))

def set_projects(c,user_id,projects):
 c.execute('DELETE FROM user_projects WHERE user_id=?',(user_id,))
 for x in projects:
  if str(x).isdigit():c.execute('INSERT INTO user_projects(user_id,project_id) VALUES(?,?)',(user_id,int(x)))

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
   set_permissions(c,u,request.form.getlist('modules'),role);set_projects(c,u,request.form.getlist('projects'));c.commit();flash('Usuario creado con sus permisos y obras asignadas.')
  except Exception:c.rollback();flash('No se pudo crear el usuario. Verifica que el correo no esté registrado.')
  c.close();return redirect('/team')
 users=c.execute('SELECT * FROM company_users WHERE company_id=? ORDER BY name',(cid,)).fetchall();projects=c.execute('SELECT id,name FROM projects WHERE company_id=? ORDER BY name',(cid,)).fetchall();data=[]
 for u in users:
  d=dict(u);d['modules']=[x['module'] for x in c.execute('SELECT module FROM user_permissions WHERE user_id=? AND can_view=1',(u['id'],)).fetchall()];d['projects']=[x['project_id'] for x in c.execute('SELECT project_id FROM user_projects WHERE user_id=?',(u['id'],)).fetchall()];data.append(d)
 c.close();return render_template('team.html',users=data,projects=projects,modules=MODULES,role_defaults=ROLE_DEFAULTS)

@app.route('/team/<int:user_id>/update',methods=['POST'])
@company_admin_required
def team_update(user_id):
 ensure_team_tables();cid=session['company_id'];c=db();u=c.execute('SELECT id FROM company_users WHERE id=? AND company_id=?',(user_id,cid)).fetchone()
 if not u:c.close();return 'Usuario no encontrado',404
 role=request.form.get('role','Consulta');active=1 if request.form.get('is_active')=='1' else 0;c.execute('UPDATE company_users SET name=?,role=?,is_active=? WHERE id=? AND company_id=?',(request.form.get('name','').strip(),role,active,user_id,cid));set_permissions(c,user_id,request.form.getlist('modules'),role);set_projects(c,user_id,request.form.getlist('projects'));c.commit();c.close();flash('Permisos del usuario actualizados.');return redirect('/team')

ensure_team_tables()
