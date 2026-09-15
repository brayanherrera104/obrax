from flask import render_template,request,session,redirect,flash
from app import app,db,company

# Reemplaza la vista de Obras para empleados: solo obras asignadas y sin datos financieros.
def projects_secure():
 co=company()
 if not co:return redirect('/login')
 c=db()
 employee=bool(session.get('user_id'))
 perms=set(session.get('permissions',[]))
 if request.method=='POST':
  # Por ahora los empleados no crean obras. El administrador conserva esta facultad.
  if employee:
   c.close();flash('Solo el administrador de la empresa puede crear obras.');return redirect('/projects')
  ci=request.form.get('client_id') or None;cn='';z=c.execute('SELECT name FROM clients WHERE id=? AND company_id=?',(ci,co['id'])).fetchone() if ci else None;cn=z['name'] if z else '';c.execute('INSERT INTO projects(company_id,client_id,name,client,value,status) VALUES(?,?,?,?,?,?)',(co['id'],ci,request.form['name'],cn,float(request.form.get('value',0) or 0),request.form.get('status','En preparación')));c.commit();c.close();return redirect('/projects')
 if employee:
  rows=c.execute("""SELECT p.id,p.name,p.status,COALESCE(cl.name,p.client,'') client_name
   FROM projects p JOIN user_projects up ON up.project_id=p.id AND up.user_id=?
   LEFT JOIN clients cl ON cl.id=p.client_id
   WHERE p.company_id=? ORDER BY p.id DESC""",(session['user_id'],co['id'])).fetchall();c.close();return render_template('projects_employee.html',projects=rows,can_control='control' in perms)
 cls=c.execute('SELECT * FROM clients WHERE company_id=? ORDER BY name',(co['id'],)).fetchall();rows=c.execute("SELECT p.*,COALESCE(cl.name,p.client,'') client_name FROM projects p LEFT JOIN clients cl ON cl.id=p.client_id WHERE p.company_id=? ORDER BY p.id DESC",(co['id'],)).fetchall();c.close();return render_template('projects.html',projects=rows,clients=cls)

app.view_functions['projects']=projects_secure
