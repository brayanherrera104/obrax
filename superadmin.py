import os,hmac
from functools import wraps
from datetime import datetime
from flask import render_template,request,redirect,url_for,session,flash
from app import app,db

ADMIN_EMAIL=os.environ.get('OBRAX_SUPERADMIN_EMAIL','').strip().lower();ADMIN_PASSWORD=os.environ.get('OBRAX_SUPERADMIN_PASSWORD','')
PLANS={
 'Prueba':{'price':'Gratis · 14 días','description':'Para conocer OBRAX antes de contratar.','features':['1 empresa','Hasta 3 obras','Hasta 10 APUs','Presupuestos y cotizaciones PDF']},
 'Básico':{'price':'$49.900 COP / mes','description':'Para independientes y contratistas pequeños.','features':['Hasta 10 obras','Hasta 50 APUs','Clientes y presupuestos','Cotizaciones con logo']},
 'Pro':{'price':'$99.900 COP / mes','description':'Para constructoras y metalmecánicas en crecimiento.','features':['Obras y APUs ilimitados','Control de costos','Reportes avanzados','Soporte prioritario']},
 'Empresa':{'price':'$199.900 COP / mes','description':'Para equipos con mayor operación.','features':['Todo Pro','Múltiples usuarios (próximamente)','Roles y permisos (próximamente)','Soporte empresarial']}}

def ensure_admin_tables():
 c=db();c.execute('''CREATE TABLE IF NOT EXISTS company_admin_meta(company_id INTEGER PRIMARY KEY,plan TEXT DEFAULT 'Prueba',is_active INTEGER DEFAULT 1,created_at TEXT,last_seen_at TEXT,last_admin_action TEXT)''')
 # migrations for subscription lifecycle
 for col,typ in [('subscription_status','TEXT'),('expires_at','TEXT')]:
  try:c.execute(f'ALTER TABLE company_admin_meta ADD COLUMN {col} {typ}')
  except Exception:c.rollback()
 c.commit();c.close()
def ensure_company_meta(company_id):
 c=db();m=c.execute('SELECT company_id FROM company_admin_meta WHERE company_id=?',(company_id,)).fetchone()
 if not m:
  now=datetime.utcnow().isoformat(timespec='seconds');c.execute('INSERT INTO company_admin_meta(company_id,plan,is_active,created_at,last_seen_at,subscription_status) VALUES(?,?,?,?,?,?)',(company_id,'Prueba',1,now,now,'Prueba'));c.commit()
 c.close()
def superadmin_required(f):
 @wraps(f)
 def w(*a,**k):return f(*a,**k) if session.get('superadmin') else redirect(url_for('superadmin_login'))
 return w
@app.before_request
def superadmin_company_guard():
 ensure_admin_tables();cid=session.get('company_id')
 if not cid:return None
 ensure_company_meta(cid);c=db();m=c.execute('SELECT is_active FROM company_admin_meta WHERE company_id=?',(cid,)).fetchone()
 if m and int(m['is_active'] or 0)==0:session.clear();c.close();flash('Esta cuenta está temporalmente bloqueada. Contacta al soporte de OBRAX.');return redirect(url_for('login'))
 c.execute('UPDATE company_admin_meta SET last_seen_at=? WHERE company_id=?',(datetime.utcnow().isoformat(timespec='seconds'),cid));c.commit();c.close()
@app.route('/billing')
def billing():
 cid=session.get('company_id')
 if not cid:return redirect(url_for('login'))
 ensure_company_meta(cid);c=db();m=c.execute('SELECT * FROM company_admin_meta WHERE company_id=?',(cid,)).fetchone();c.close();return render_template('billing.html',plans=PLANS,current_plan=m['plan'] or 'Prueba',subscription_status=m['subscription_status'] or 'Prueba',expires_at=m['expires_at'])
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
 ensure_company_meta(company_id);plan=request.form.get('plan','Prueba');plan=plan if plan in PLANS else 'Prueba';active=1 if request.form.get('is_active')=='1' else 0;c=db();c.execute('UPDATE company_admin_meta SET plan=?,is_active=?,subscription_status=?,last_admin_action=? WHERE company_id=?',(plan,active,'Activa' if plan!='Prueba' else 'Prueba',datetime.utcnow().isoformat(timespec='seconds'),company_id));c.commit();c.close();flash('Empresa actualizada.');return redirect(url_for('superadmin_dashboard'))
ensure_admin_tables()
