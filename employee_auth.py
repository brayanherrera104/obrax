from flask import request,session,redirect,flash
from werkzeug.security import check_password_hash
from app import app,db
from plans import normalize_plan
from plan_capacity import sync_user_capacity,user_plan_enabled

@app.before_request
def employee_login_bridge():
 if request.path!='/login' or request.method!='POST':return None
 email=request.form.get('email','').strip().lower();password=request.form.get('password','')
 if not email:return None
 c=db()
 try:u=c.execute('SELECT * FROM company_users WHERE email=?',(email,)).fetchone()
 except Exception:u=None
 if not u:c.close();return None
 if not u['is_active']:
  c.close();flash('Tu acceso está desactivado. Contacta al administrador de tu empresa.');return redirect('/login')
 if not check_password_hash(u['password_hash'],password):
  c.close();flash('Correo o contraseña incorrectos.');return redirect('/login')
 try:co=c.execute('SELECT plan FROM companies WHERE id=?',(u['company_id'],)).fetchone();plan=normalize_plan(co['plan'] if co and 'plan' in co.keys() else 'Prueba')
 except Exception:plan='Prueba'
 c.close();sync_user_capacity(u['company_id'],plan)
 if not user_plan_enabled(u['company_id'],u['id']):flash('Tu usuario está fuera de los cupos activos del plan de la empresa. Contacta al administrador.');return redirect('/login')
 c=db();perms=[x['module'] for x in c.execute('SELECT module FROM user_permissions WHERE user_id=? AND can_view=1',(u['id'],)).fetchall()];c.close()
 session.clear();session['company_id']=u['company_id'];session['user_id']=u['id'];session['user_name']=u['name'];session['user_role']=u['role'];session['permissions']=perms
 return redirect('/dashboard')
