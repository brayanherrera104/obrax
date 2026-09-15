from flask import request,redirect,url_for,session,flash
from app import app,db,login_required

@app.route('/budget/<int:budget_id>/assign-project',methods=['POST'])
@login_required
def budget_assign_project(budget_id):
    cid=session['company_id'];project_id=request.form.get('project_id') or None;c=db()
    b=c.execute('SELECT id FROM budgets WHERE id=? AND company_id=?',(budget_id,cid)).fetchone()
    if not b:c.close();return 'Presupuesto no encontrado',404
    if project_id:
        p=c.execute('SELECT id,client_id FROM projects WHERE id=? AND company_id=?',(project_id,cid)).fetchone()
        if not p:c.close();flash('La obra seleccionada no pertenece a tu empresa.');return redirect(url_for('budget_detail',i=budget_id))
        c.execute('UPDATE budgets SET project_id=?,client_id=COALESCE(client_id,?) WHERE id=? AND company_id=?',(project_id,p['client_id'],budget_id,cid));flash('Presupuesto vinculado a la obra.')
    else:
        c.execute('UPDATE budgets SET project_id=NULL WHERE id=? AND company_id=?',(budget_id,cid));flash('Presupuesto desvinculado de la obra.')
    c.commit();c.close();return redirect(url_for('budget_detail',i=budget_id))
