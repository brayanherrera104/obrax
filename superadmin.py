import os,hmac
from functools import wraps
from datetime import datetime,timedelta
from flask import render_template,request,redirect,url_for,session,flash
from app import app,db,PG
from plans import PLANS,normalize_plan,plan_limit,plan_has_module

ADMIN_EMAIL=os.environ.get('OBRAX_SUPERADMIN_EMAIL','').strip().lower();ADMIN_PASSWORD=os.environ.get('OBRAX_SUPERADMIN_PASSWORD','')

def ensure_admin_tables():
 c=db();c.execute('''CREATE TABLE IF NOT EXISTS company_admin_meta(company_id INTEGER PRIMARY KEY,plan TEXT DEFAULT 'Prueba',is_active INTEGER DEFAULT 1,created_at TEXT,last_seen_at TEXT,last_admin_action TEXT)''');c.commit()
 try:
  if PG:cols={r['column_name'] for r in c.execute("SELECT column_name FROM information_schema.columns WHERE table_name='company_admin_meta'").fetchall()}
  else:cols={r['name'] for r in c.execute('PRAGMA table_info(company_admin_meta)').fetchall()}
  if 'subscription_status' not in cols:c.execute('ALTER TABLE company_admin_meta ADD COLUMN subscription_status TEXT');c.commit()
  if 'expires_at' not in cols:c.execute('ALTER TABLE company_admin_meta ADD COLUMN expires_at TEXT');c.commit()
 except Exception:c.rollback()
 c.close()
def ensure_company_meta(company_id):
 c=db();m=c.execute('SELECT company_id FROM company_admin_meta WHERE company_id=?',(company_id,)).fetchone()
 if not m:
  now=datetime.utcnow();exp=(now+timedelta(days=14)).isoformat(timespec='seconds');c.execute('INSERT INTO company_admin_meta(company_id,plan,is_active,created_at,last_seen_at,subscription_status,expires_at) VALUES(?,?,?,?,?,?,?)',(company_id,'Prueba',1,now.isoformat(timespec='seconds'),now.isoformat(timespec='seconds'),'Prueba',exp));c.commit()
 c.close()
def company_plan(company_id):
 c=db();m=c.execute('SELECT plan FROM company_admin_meta WHERE company_id=?',(company_id,)).fetchone();c.close();return normalize_plan(m['plan'] if m else 'Prueba')
def company_has_module(company_id,module):return plan_has_module(company_plan(company_id),module)
def superadmin_required(f):
 @wraps(f)
 def w(*a,**k):return f(*a,**k) if session.get('superadmin') else redirect(url_for('superadmin_login'))
 return w
def refresh_subscription(company_id):
 c=db();m=c.execute('SELECT subscription_status,expires_at FROM company_admin_meta WHERE company_id=?',(company_id,)).fetchone()
 if m and m['expires_at']:
  try:
   if datetime.fromisoformat(m['expires_at']) < datetime.utcnow() and m['subscription_status']!='Vencida':c.execute('UPDATE company_admin_meta SET subscription_status=? WHERE company_id=?',('Vencida',company_id));c.commit()
  except Exception:pass
 c.close()
def check_plan_limit(company_id,resource):
 plan=company_plan(company_id);limit=plan_limit(plan,resource)
 if limit is None:return None
 c=db()
 if resource=='users':table='company_users'
 elif resource=='projects':table='projects'
 else:table='apus'
 count=c.execute(f'SELECT COUNT(*) n FROM {table} WHERE company_id=?',(company_id,)).fetchone()['n'];c.close()
 if count>=limit:
  label={'users':'usuarios','projects':'obras','apus':'APUs'}[resource];return f'Has alcanzado el límite de {limit} {label} de tu plan {plan}. Mejora tu plan para continuar.'
 return None
@app.before_request
def superadmin_company_guard():
 ensure_admin_tables();cid=session.get('company_id')
 if not cid:return None
 ensure_company_meta(cid);refresh_subscription(cid);c=db();m=c.execute('SELECT is_active FROM company_admin_meta WHERE company_id=?',(cid,)).fetchone()
 if m and int(m['is_active'] or 0)==0:session.clear();c.close();flash('Esta cuenta está temporalmente bloqueada. Contacta al soporte de OBRAX.');return redirect(url_for('login'))
 c.execute('UPDATE company_admin_meta SET last_seen_at=? WHERE company_id=?',(datetime.utcnow().isoformat(timespec='seconds'),cid));c.commit();c.close()
 resource=None
 if request.method=='POST' and request.path=='/projects':resource='projects'
 elif request.method=='POST' and request.path=='/apus':resource='apus'
 elif request.method=='POST' and request.path.startswith('/apu/') and request.path.endswith('/duplicate'):resource='apus'
 elif request.method=='POST' and request.path=='/team':resource='users'
 if resource:
  msg=check_plan_limit(cid,resource)
  if msg:flash(msg);return redirect({'projects':'/projects','apus':'/apus','users':'/team'}[resource])
 # Bloqueo de módulos financieros por plan. Se valida en servidor, no solo en el menú.
 path=request.path
 module=None
 if path.startswith('/receivables'):module='receivables'
 elif path.startswith('/cashflow'):module='cashflow'
 elif path.startswith('/treasury'):module='treasury'
 if module and not company_has_module(cid,module):
  flash(f'Esta función no está incluida en tu plan {company_plan(cid)}. Está disponible desde OBRAX Pro.');return redirect('/billing')
@app.route('/billing')
def billing():
 cid=session.get('company_id')
 if not cid:return redirect(url_for('login'))
 ensure_company_meta(cid);refresh_subscription(cid);c=db();m=c.execute('SELECT * FROM company_admin_meta WHERE company_id=?',(cid,)).fetchone();c.close();return render_template('billing.html',plans=PLANS,current_plan=normalize_plan(m['plan'] or 'Prueba'),subscription_status=m['subscription_status'] or 'Prueba',expires_at=m['expires_at'])
@app.route('/superadmin/login',methods=['GET','POST'])
def superadmin_login():
 if request.method=='POST':
  email=request.form.get('email','').strip().lower();password=request.form.get('password','')
  if not ADMIN_EMAIL or not ADMIN_PASSWORD:flash('El acceso Superadmin todavía no está configurado en Render.')
  elif hmac.compare_digest(email,ADMIN_EMAIL) and hmac.compare_digest(password,ADMIN_PASSWORD):session.clear();session['superadmin']=True;return redirect(url_for('superadmin_dashboard'))
  else:flash('Credenciales incorrectas.')
 return render_template('superadmin_login.html')
@app.route('/superadmin/logout')
def superadmin_logout():session.clear();return redirect(url_for('superadmin_login'))
@app.route('/superadmin')
@superadmin_required
def superadmin_dashboard():
 q=request.args.get('q','').strip();c=db();base='''SELECT co.id,co.name,co.nit,co.admin_name,co.email,co.phone,COALESCE(m.plan,'Prueba') plan,COALESCE(m.is_active,1) is_active,m.created_at,m.last_seen_at,m.subscription_status,m.expires_at,(SELECT COUNT(*) FROM projects p WHERE p.company_id=co.id) projects_count,(SELECT COUNT(*) FROM apus a WHERE a.company_id=co.id) apus_count,(SELECT COUNT(*) FROM budgets b WHERE b.company_id=co.id) budgets_count,(SELECT COUNT(*) FROM quotations qt WHERE qt.company_id=co.id) quotes_count,(SELECT COUNT(*) FROM clients cl WHERE cl.company_id=co.id) clients_count FROM companies co LEFT JOIN company_admin_meta m ON m.company_id=co.id'''
 if q:rows=c.execute(base+" WHERE LOWER(co.name) LIKE ? OR LOWER(co.email) LIKE ? OR LOWER(COALESCE(co.nit,'')) LIKE ? ORDER BY co.id DESC",('%'+q.lower()+'%','%'+q.lower()+'%','%'+q.lower()+'%')).fetchall()
 else:rows=c.execute(base+' ORDER BY co.id DESC').fetchall()
 total=c.execute('SELECT COUNT(*) n FROM companies').fetchone()['n'];active=c.execute('SELECT COUNT(*) n FROM company_admin_meta WHERE is_active=1').fetchone()['n'];apus=c.execute('SELECT COUNT(*) n FROM apus').fetchone()['n'];quotes=c.execute('SELECT COUNT(*) n FROM quotations').fetchone()['n'];c.close();return render_template('superadmin_dashboard.html',companies=rows,total=total,active=active,apus=apus,quotes=quotes,q=q)
@app.route('/superadmin/company/<int:company_id>/update',methods=['POST'])
@superadmin_required
def superadmin_company_update(company_id):
 ensure_company_meta(company_id);plan=normalize_plan(request.form.get('plan','Prueba'));active=1 if request.form.get('is_active')=='1' else 0;c=db();old=c.execute('SELECT plan,expires_at FROM company_admin_meta WHERE company_id=?',(company_id,)).fetchone();now=datetime.utcnow();exp_raw=request.form.get('expires_at','').strip();exp=None
 if exp_raw:
  try:exp=datetime.fromisoformat(exp_raw).replace(hour=23,minute=59,second=59).isoformat(timespec='seconds')
  except Exception:exp=None
 if not exp:exp=old['expires_at'] if old else None
 if not old or old['plan']!=plan or not exp:exp=(now+timedelta(days=14 if plan=='Prueba' else 30)).isoformat(timespec='seconds')
 status='Vencida' if datetime.fromisoformat(exp)<now else ('Prueba' if plan=='Prueba' else 'Activa');c.execute('UPDATE company_admin_meta SET plan=?,is_active=?,subscription_status=?,expires_at=?,last_admin_action=? WHERE company_id=?',(plan,active,status,exp,now.isoformat(timespec='seconds'),company_id));c.commit();c.close();flash('Empresa actualizada.');return redirect(url_for('superadmin_dashboard'))
@app.route('/superadmin/company/<int:company_id>/renew',methods=['POST'])
@superadmin_required
def superadmin_company_renew(company_id):
 ensure_company_meta(company_id);c=db();m=c.execute('SELECT plan,expires_at FROM company_admin_meta WHERE company_id=?',(company_id,)).fetchone();now=datetime.utcnow();base=now
 if m and m['expires_at']:
  try:
   current=datetime.fromisoformat(m['expires_at']);base=current if current>now else now
  except Exception:pass
 new_exp=(base+timedelta(days=30)).isoformat(timespec='seconds');status='Prueba' if (m and m['plan']=='Prueba') else 'Activa';c.execute('UPDATE company_admin_meta SET expires_at=?,subscription_status=?,is_active=1,last_admin_action=? WHERE company_id=?',(new_exp,status,now.isoformat(timespec='seconds'),company_id));c.commit();c.close();flash('Suscripción renovada por 30 días.');return redirect(url_for('superadmin_dashboard'))
ensure_admin_tables()
