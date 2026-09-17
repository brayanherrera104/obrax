from flask import Flask,render_template,request,redirect,url_for,session,flash,send_file
import os,sqlite3,io,base64
from functools import wraps
from datetime import date
from html import escape
from werkzeug.security import generate_password_hash,check_password_hash
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,Image
app=Flask(__name__); app.secret_key=os.environ.get('OBRAX_SECRET','change-me'); app.config['MAX_CONTENT_LENGTH']=2*1024*1024
URL=os.environ.get('DATABASE_URL',''); PG=URL.startswith(('postgres://','postgresql://')); DB='obrax.db'
if PG:
 import psycopg2
 from psycopg2.extras import RealDictCursor
class Conn:
 def __init__(s):
  s.pg=PG
  if PG:s.c=psycopg2.connect(URL,cursor_factory=RealDictCursor)
  else:s.c=sqlite3.connect(DB);s.c.row_factory=sqlite3.Row
 def execute(s,q,p=()):
  if s.pg:
   x=s.c.cursor();x.execute(q.replace('?','%s'),p);return x
  return s.c.execute(q,p)
 def commit(s):s.c.commit()
 def rollback(s):s.c.rollback()
 def close(s):s.c.close()
def db():return Conn()
def ins(c,q,p):
 if c.pg:return c.execute(q+' RETURNING id',p).fetchone()['id']
 return c.execute(q,p).lastrowid
def init_db():
 c=db();pk='SERIAL PRIMARY KEY' if PG else 'INTEGER PRIMARY KEY AUTOINCREMENT';r='DOUBLE PRECISION' if PG else 'REAL'
 ss=[f'''CREATE TABLE IF NOT EXISTS companies(id {pk},name TEXT NOT NULL,nit TEXT,admin_name TEXT NOT NULL,email TEXT UNIQUE NOT NULL,phone TEXT,password_hash TEXT NOT NULL,logo_data TEXT)''',f'''CREATE TABLE IF NOT EXISTS clients(id {pk},company_id INTEGER NOT NULL,name TEXT NOT NULL,nit TEXT,contact TEXT,phone TEXT,email TEXT)''',f'''CREATE TABLE IF NOT EXISTS projects(id {pk},company_id INTEGER NOT NULL,client_id INTEGER,name TEXT NOT NULL,client TEXT,value {r} DEFAULT 0,status TEXT DEFAULT 'En preparación')''',f'''CREATE TABLE IF NOT EXISTS apus(id {pk},company_id INTEGER NOT NULL,name TEXT NOT NULL,unit TEXT NOT NULL,admin_pct {r} DEFAULT 8,conting_pct {r} DEFAULT 2,util_pct {r} DEFAULT 10)''',f'''CREATE TABLE IF NOT EXISTS apu_items(id {pk},apu_id INTEGER NOT NULL,resource_type TEXT,name TEXT NOT NULL,unit TEXT,qty {r} DEFAULT 0,waste_pct {r} DEFAULT 0,price {r} DEFAULT 0)''',f'''CREATE TABLE IF NOT EXISTS budgets(id {pk},company_id INTEGER NOT NULL,project_id INTEGER,client_id INTEGER,name TEXT NOT NULL,created_at TEXT NOT NULL,validity_days INTEGER DEFAULT 15,status TEXT DEFAULT 'Borrador')''',f'''CREATE TABLE IF NOT EXISTS budget_items(id {pk},budget_id INTEGER NOT NULL,chapter TEXT,apu_id INTEGER,description TEXT NOT NULL,unit TEXT,quantity {r} DEFAULT 1,unit_price {r} DEFAULT 0)''',f'''CREATE TABLE IF NOT EXISTS quotations(id {pk},company_id INTEGER NOT NULL,budget_id INTEGER NOT NULL,quote_number TEXT NOT NULL,created_at TEXT NOT NULL,validity_days INTEGER DEFAULT 15,status TEXT DEFAULT 'Borrador',terms TEXT,observations TEXT)''']
 for x in ss:c.execute(x)
 c.commit();c.close()
@app.before_request
def ready():init_db()
def login_required(f):
 @wraps(f)
 def w(*a,**k):return f(*a,**k) if session.get('company_id') else redirect(url_for('login'))
 return w
def company():
 c=db();x=c.execute('SELECT * FROM companies WHERE id=?',(session.get('company_id'),)).fetchone() if session.get('company_id') else None;c.close();return x
def apu_cost(c,i):
 a=c.execute('SELECT * FROM apus WHERE id=?',(i,)).fetchone();xs=c.execute('SELECT * FROM apu_items WHERE apu_id=?',(i,)).fetchall() if a else [];d=sum((x['qty'] or 0)*(1+(x['waste_pct'] or 0)/100)*(x['price'] or 0) for x in xs);return (d,d*(1+(a['admin_pct'] or 0)/100+(a['conting_pct'] or 0)/100)*(1+(a['util_pct'] or 0)/100)) if a else (0,0)
def btotal(c,i):return sum((x['quantity'] or 0)*(x['unit_price'] or 0) for x in c.execute('SELECT quantity,unit_price FROM budget_items WHERE budget_id=?',(i,)).fetchall())
def items(c,aid):
 n=request.form.getlist('item_name[]');t=request.form.getlist('item_type[]');u=request.form.getlist('item_unit[]');q=request.form.getlist('item_qty[]');w=request.form.getlist('item_waste[]');p=request.form.getlist('item_price[]')
 for i,x in enumerate(n):
  if x.strip():c.execute('INSERT INTO apu_items(apu_id,resource_type,name,unit,qty,waste_pct,price) VALUES(?,?,?,?,?,?,?)',(aid,t[i],x,u[i],float(q[i] or 0),float(w[i] or 0),float(p[i] or 0)))
@app.route('/')
def landing():
 host=request.host.split(':')[0].lower()
 if host=='app.obrax.com.co':
  if session.get('company_id') or session.get('demo'):return redirect(url_for('dashboard'))
  return render_template('app_home.html')
 return render_template('landing.html')
@app.route('/demo')
def demo():session.clear();session['demo']=1;return redirect(url_for('dashboard'))
@app.route('/register',methods=['GET','POST'])
def register():
 if request.method=='POST':
  if len(request.form['password'])<6:flash('La contraseña debe tener mínimo 6 caracteres.');return render_template('register.html')
  c=db()
  try:i=ins(c,'INSERT INTO companies(name,nit,admin_name,email,phone,password_hash) VALUES(?,?,?,?,?,?)',(request.form['company_name'],request.form.get('nit',''),request.form['admin_name'],request.form['email'].lower(),request.form.get('phone',''),generate_password_hash(request.form['password'])));c.commit();session.clear();session['company_id']=i;c.close();return redirect(url_for('dashboard'))
  except Exception:c.rollback();c.close();flash('Ese correo ya está registrado o no se pudo crear la cuenta.')
 return render_template('register.html')
@app.route('/login',methods=['GET','POST'])
def login():
 if request.method=='POST':
  c=db();x=c.execute('SELECT * FROM companies WHERE email=?',(request.form['email'].lower(),)).fetchone();c.close()
  if x and check_password_hash(x['password_hash'],request.form['password']):session.clear();session['company_id']=x['id'];return redirect(url_for('dashboard'))
  flash('Correo o contraseña incorrectos.')
 return render_template('login.html')
@app.route('/logout')
def logout():session.clear();return redirect('/')
@app.route('/dashboard')
def dashboard():
 if not session.get('company_id') and not session.get('demo'):return redirect('/login')
 if session.get('demo'):return render_template('dashboard.html',company={'name':'Constructora Demo S.A.S.'},projects=[{'name':'Cerramiento estación TM','client':'Cliente Demo','value':185000000,'status':'En ejecución'}],apus_count=12,clients_count=8,budgets_count=5,quotes_count=3,quoted_total=505000000,demo=True)
 co=company();c=db();ps=c.execute("SELECT p.*,COALESCE(cl.name,p.client,'') client_name FROM projects p LEFT JOIN clients cl ON cl.id=p.client_id WHERE p.company_id=? ORDER BY p.id DESC LIMIT 8",(co['id'],)).fetchall();cnt=lambda t:c.execute(f'SELECT COUNT(*) n FROM {t} WHERE company_id=?',(co['id'],)).fetchone()['n'];qs=c.execute('SELECT budget_id FROM quotations WHERE company_id=?',(co['id'],)).fetchall();tot=sum(btotal(c,x['budget_id']) for x in qs);a,cl,b,q=cnt('apus'),cnt('clients'),cnt('budgets'),cnt('quotations');c.close();return render_template('dashboard.html',company=co,projects=ps,apus_count=a,clients_count=cl,budgets_count=b,quotes_count=q,quoted_total=tot,demo=False)
@app.route('/settings',methods=['GET','POST'])
@login_required
def settings():
 co=company()
 if request.method=='POST':
  logo=co['logo_data'];f=request.files.get('logo')
  if f and f.filename:
   raw=f.read();mime=f.mimetype
   if len(raw)>2*1024*1024 or mime not in ('image/png','image/jpeg','image/webp'):flash('Logo inválido. Usa PNG, JPG o WEBP de máximo 2 MB.');return redirect('/settings')
   logo=f'data:{mime};base64,'+base64.b64encode(raw).decode()
  c=db();c.execute('UPDATE companies SET name=?,nit=?,admin_name=?,phone=?,logo_data=? WHERE id=?',(request.form['name'],request.form.get('nit',''),request.form['admin_name'],request.form.get('phone',''),logo,co['id']));c.commit();c.close();flash('Datos de empresa actualizados.');return redirect('/settings')
 return render_template('settings.html',company=co)
@app.route('/clients',methods=['GET','POST'])
@login_required
def clients():
 co=company();c=db()
 if request.method=='POST':c.execute('INSERT INTO clients(company_id,name,nit,contact,phone,email) VALUES(?,?,?,?,?,?)',(co['id'],request.form['name'],request.form.get('nit',''),request.form.get('contact',''),request.form.get('phone',''),request.form.get('email','')));c.commit();c.close();return redirect('/clients')
 x=c.execute('SELECT * FROM clients WHERE company_id=? ORDER BY id DESC',(co['id'],)).fetchall();c.close();return render_template('clients.html',clients=x)
@app.route('/projects',methods=['GET','POST'])
@login_required
def projects():
 co=company();c=db();cls=c.execute('SELECT * FROM clients WHERE company_id=? ORDER BY name',(co['id'],)).fetchall()
 if request.method=='POST':
  ci=request.form.get('client_id') or None;cn='';z=c.execute('SELECT name FROM clients WHERE id=? AND company_id=?',(ci,co['id'])).fetchone() if ci else None;cn=z['name'] if z else '';c.execute('INSERT INTO projects(company_id,client_id,name,client,value,status) VALUES(?,?,?,?,?,?)',(co['id'],ci,request.form['name'],cn,float(request.form.get('value',0) or 0),request.form.get('status','En preparación')));c.commit();c.close();return redirect('/projects')
 x=c.execute("SELECT p.*,COALESCE(cl.name,p.client,'') client_name FROM projects p LEFT JOIN clients cl ON cl.id=p.client_id WHERE p.company_id=? ORDER BY p.id DESC",(co['id'],)).fetchall();c.close();return render_template('projects.html',projects=x,clients=cls)
@app.route('/apus',methods=['GET','POST'])
def apus():
 co=company()
 if session.get('demo'):return render_template('apus.html',apus=[{'name':'Fabricación y montaje de estructura metálica','unit':'kg','direct':4200,'price':5082}],demo=True)
 if not co:return redirect('/login')
 if request.method=='POST':
  c=db();aid=ins(c,'INSERT INTO apus(company_id,name,unit,admin_pct,conting_pct,util_pct) VALUES(?,?,?,?,?,?)',(co['id'],request.form['name'],request.form['unit'],float(request.form.get('admin_pct',8) or 0),float(request.form.get('conting_pct',2) or 0),float(request.form.get('util_pct',10) or 0)));items(c,aid);c.commit();c.close();return redirect('/apus')
 c=db();x=[]
 for a in c.execute('SELECT * FROM apus WHERE company_id=? ORDER BY id DESC',(co['id'],)).fetchall():d,p=apu_cost(c,a['id']);x.append({**dict(a),'direct':d,'price':p})
 c.close();return render_template('apus.html',apus=x,demo=False)
@app.route('/apu/new')
@login_required
def new_apu():return render_template('apu_form.html',apu=None,items=[])
@app.route('/apu/<int:i>/edit',methods=['GET','POST'])
@login_required
def edit_apu(i):
 co=company();c=db();a=c.execute('SELECT * FROM apus WHERE id=? AND company_id=?',(i,co['id'])).fetchone()
 if not a:c.close();return 'APU no encontrado',404
 if request.method=='POST':c.execute('UPDATE apus SET name=?,unit=?,admin_pct=?,conting_pct=?,util_pct=? WHERE id=?',(request.form['name'],request.form['unit'],float(request.form.get('admin_pct',0) or 0),float(request.form.get('conting_pct',0) or 0),float(request.form.get('util_pct',0) or 0),i));c.execute('DELETE FROM apu_items WHERE apu_id=?',(i,));items(c,i);c.commit();c.close();flash('APU actualizado.');return redirect('/apus')
 xs=c.execute('SELECT * FROM apu_items WHERE apu_id=? ORDER BY id',(i,)).fetchall();c.close();return render_template('apu_form.html',apu=a,items=xs)
@app.route('/apu/<int:i>/duplicate',methods=['POST'])
@login_required
def duplicate_apu(i):
 co=company();c=db();a=c.execute('SELECT * FROM apus WHERE id=? AND company_id=?',(i,co['id'])).fetchone()
 if a:
  n=ins(c,'INSERT INTO apus(company_id,name,unit,admin_pct,conting_pct,util_pct) VALUES(?,?,?,?,?,?)',(co['id'],a['name']+' (copia)',a['unit'],a['admin_pct'],a['conting_pct'],a['util_pct']))
  for x in c.execute('SELECT * FROM apu_items WHERE apu_id=?',(i,)).fetchall():c.execute('INSERT INTO apu_items(apu_id,resource_type,name,unit,qty,waste_pct,price) VALUES(?,?,?,?,?,?,?)',(n,x['resource_type'],x['name'],x['unit'],x['qty'],x['waste_pct'],x['price']))
  c.commit()
 c.close();return redirect('/apus')
@app.route('/apu/<int:i>/delete',methods=['POST'])
@login_required
def delete_apu(i):
 co=company();c=db();a=c.execute('SELECT id FROM apus WHERE id=? AND company_id=?',(i,co['id'])).fetchone()
 if a:c.execute('DELETE FROM apu_items WHERE apu_id=?',(i,));c.execute('DELETE FROM apus WHERE id=?',(i,));c.commit()
 c.close();return redirect('/apus')
@app.route('/budgets',methods=['GET','POST'])
@login_required
def budgets():
 co=company();c=db();ps=c.execute('SELECT * FROM projects WHERE company_id=? ORDER BY name',(co['id'],)).fetchall();cls=c.execute('SELECT * FROM clients WHERE company_id=? ORDER BY name',(co['id'],)).fetchall()
 if request.method=='POST':i=ins(c,'INSERT INTO budgets(company_id,project_id,client_id,name,created_at,validity_days,status) VALUES(?,?,?,?,?,?,?)',(co['id'],request.form.get('project_id') or None,request.form.get('client_id') or None,request.form['name'],date.today().isoformat(),int(request.form.get('validity_days',15) or 15),'Borrador'));c.commit();c.close();return redirect(url_for('budget_detail',i=i))
 x=c.execute('SELECT b.*,p.name project_name,cl.name client_name FROM budgets b LEFT JOIN projects p ON p.id=b.project_id LEFT JOIN clients cl ON cl.id=b.client_id WHERE b.company_id=? ORDER BY b.id DESC',(co['id'],)).fetchall();data=[{**dict(z),'total':btotal(c,z['id'])} for z in x];c.close();return render_template('budgets.html',budgets=data,projects=ps,clients=cls)
@app.route('/budget/<int:i>',methods=['GET','POST'])
@login_required
def budget_detail(i):
 co=company();c=db();b=c.execute('SELECT * FROM budgets WHERE id=? AND company_id=?',(i,co['id'])).fetchone()
 if not b:c.close();return 'Presupuesto no encontrado',404
 if request.method=='POST':
  aid=request.form.get('apu_id') or None;des=request.form.get('description','');un=request.form.get('unit','');pr=float(request.form.get('unit_price',0) or 0)
  if aid:
   a=c.execute('SELECT * FROM apus WHERE id=? AND company_id=?',(aid,co['id'])).fetchone()
   if a:des=a['name'];un=a['unit'];_,pr=apu_cost(c,a['id'])
  c.execute('INSERT INTO budget_items(budget_id,chapter,apu_id,description,unit,quantity,unit_price) VALUES(?,?,?,?,?,?,?)',(i,request.form.get('chapter','General'),aid,des,un,float(request.form.get('quantity',1) or 1),pr));c.commit();return redirect(url_for('budget_detail',i=i))
 xs=c.execute('SELECT * FROM budget_items WHERE budget_id=? ORDER BY id',(i,)).fetchall();aps=c.execute('SELECT * FROM apus WHERE company_id=? ORDER BY name',(co['id'],)).fetchall();tot=btotal(c,i);c.close();return render_template('budget_detail.html',budget=b,items=xs,apus=aps,total=tot)
@app.route('/budget/<int:i>/quote',methods=['POST'])
@login_required
def create_quote(i):
 co=company();c=db();b=c.execute('SELECT * FROM budgets WHERE id=? AND company_id=?',(i,co['id'])).fetchone();old=c.execute('SELECT * FROM quotations WHERE budget_id=? AND company_id=?',(i,co['id'])).fetchone()
 if old:c.close();return redirect(url_for('quotation_detail',i=old['id']))
 n=c.execute('SELECT COUNT(*) n FROM quotations WHERE company_id=?',(co['id'],)).fetchone()['n']+1;q=ins(c,'INSERT INTO quotations(company_id,budget_id,quote_number,created_at,validity_days,status,terms,observations) VALUES(?,?,?,?,?,?,?,?)',(co['id'],i,f'COT-{date.today().year}-{n:04d}',date.today().isoformat(),b['validity_days'],'Borrador','50% anticipo, saldo contra avance o entrega.',''));c.commit();c.close();return redirect(url_for('quotation_detail',i=q))
@app.route('/quotations')
@login_required
def quotations():
 co=company();c=db();x=c.execute('SELECT q.*,b.name budget_name FROM quotations q JOIN budgets b ON b.id=q.budget_id WHERE q.company_id=? ORDER BY q.id DESC',(co['id'],)).fetchall();data=[{**dict(z),'total':btotal(c,z['budget_id'])} for z in x];c.close();return render_template('quotations.html',quotations=data)
def qdata(c,i,co):return c.execute('SELECT q.*,b.name budget_name,b.client_id,b.project_id,cl.name client_name,cl.nit client_nit,cl.contact client_contact,p.name project_name FROM quotations q JOIN budgets b ON b.id=q.budget_id LEFT JOIN clients cl ON cl.id=b.client_id LEFT JOIN projects p ON p.id=b.project_id WHERE q.id=? AND q.company_id=?',(i,co)).fetchone()
@app.route('/quotation/<int:i>',methods=['GET','POST'])
@login_required
def quotation_detail(i):
 co=company();c=db();q=qdata(c,i,co['id'])
 if not q:c.close();return 'Cotización no encontrada',404
 if request.method=='POST':c.execute('UPDATE quotations SET status=?,terms=?,observations=? WHERE id=? AND company_id=?',(request.form['status'],request.form.get('terms',''),request.form.get('observations',''),i,co['id']));c.commit();return redirect(url_for('quotation_detail',i=i))
 xs=c.execute('SELECT * FROM budget_items WHERE budget_id=?',(q['budget_id'],)).fetchall();tot=btotal(c,q['budget_id']);c.close();return render_template('quotation_detail.html',q=q,items=xs,total=tot,company=co)
@app.route('/quotation/<int:i>/pdf')
@login_required
def quotation_pdf(i):
 co=company();c=db();q=qdata(c,i,co['id']);xs=c.execute('SELECT * FROM budget_items WHERE budget_id=? ORDER BY id',(q['budget_id'],)).fetchall() if q else [];tot=btotal(c,q['budget_id']) if q else 0;c.close()
 if not q:return 'Cotización no encontrada',404
 buf=io.BytesIO();doc=SimpleDocTemplate(buf,pagesize=A4,rightMargin=15*mm,leftMargin=15*mm,topMargin=15*mm,bottomMargin=15*mm);st=getSampleStyleSheet();story=[]
 if co['logo_data']:
  try:story.append(Image(io.BytesIO(base64.b64decode(co['logo_data'].split(',',1)[1])),width=35*mm,height=18*mm,kind='proportional'))
  except:pass
 story+=[Paragraph(f"<b>{escape(co['name'])}</b><br/>NIT {escape(co['nit'] or '-')}<br/>{escape(co['email'])}",st['Normal']),Spacer(1,5*mm),Paragraph(f"<b>COTIZACIÓN {escape(q['quote_number'])}</b><br/>Cliente: {escape(q['client_name'] or 'Sin asignar')}<br/>Obra: {escape(q['project_name'] or '-')}",st['Heading2']),Spacer(1,4*mm)]
 data=[['Descripción','Und','Cant.','Precio','Total']]+[[x['description'],x['unit'] or '',f"{x['quantity']:,.2f}",f"${x['unit_price']:,.0f}",f"${x['quantity']*x['unit_price']:,.0f}"] for x in xs];t=Table(data,colWidths=[75*mm,15*mm,18*mm,27*mm,30*mm],repeatRows=1);t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#14213D')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('GRID',(0,0),(-1,-1),.3,colors.grey),('FONTSIZE',(0,0),(-1,-1),8),('ALIGN',(2,1),(-1,-1),'RIGHT')]));story+=[t,Spacer(1,5*mm),Paragraph(f'<b>TOTAL: ${tot:,.0f}</b>',st['Heading2']),Spacer(1,4*mm),Paragraph('<b>Condiciones de pago</b><br/>'+escape(q['terms'] or ''),st['Normal'])];doc.build(story);buf.seek(0);return send_file(buf,mimetype='application/pdf',as_attachment=True,download_name=q['quote_number']+'.pdf')
if __name__=='__main__':init_db();app.run(host='0.0.0.0',port=int(os.environ.get('PORT',5000)))