from flask import request,session,flash,redirect
from app import app,db
import superadmin

# OBRAX 5.2. Precios comerciales antes de IVA.
PLANS={
 'Prueba':{'monthly':0,'annual':None,'price':'Gratis · 14 días','description':'Prueba OBRAX Pro durante 14 días.','features':['1 usuario','Hasta 3 obras','Hasta 10 APUs','Funciones Pro durante 14 días'],'projects':3,'apus':10,'users':1,'modules':{'dashboard','apus','clients','projects','budgets','quotations','control','payables','receivables','cashflow'}},
 'Básico':{'monthly':49900,'annual':499000,'price':'$49.900 + IVA / mes','description':'Para independientes y equipos pequeños que quieren controlar sus obras.','features':['2 usuarios','Hasta 5 obras','Hasta 50 APUs','Presupuestos, cotizaciones y control de obra','Cuentas por pagar'],'projects':5,'apus':50,'users':2,'modules':{'dashboard','apus','clients','projects','budgets','quotations','control','payables'}},
 'Pro':{'monthly':99900,'annual':999000,'price':'$99.900 + IVA / mes','description':'Control financiero completo para constructoras y metalmecánicas en crecimiento.','features':['8 usuarios','Hasta 20 obras','APUs ilimitados','Cartera, retenciones y flujo de caja','Tesorería, alertas y reportes avanzados'],'projects':20,'apus':None,'users':8,'modules':{'dashboard','apus','clients','projects','budgets','quotations','control','payables','receivables','cashflow'}},
 'Empresa':{'monthly':149900,'annual':1499000,'price':'$149.900 + IVA / mes','description':'Para empresas con múltiples equipos y una operación sin límites.','features':['Usuarios ilimitados','Obras y APUs ilimitados','Todo OBRAX Pro','Permisos avanzados y auditoría empresarial','Soporte prioritario Empresa'],'projects':None,'apus':None,'users':None,'modules':{'dashboard','apus','clients','projects','budgets','quotations','control','payables','receivables','cashflow'}}
}
# El guard existente de Superadmin usa este mismo diccionario para límites de obras/APUs.
superadmin.PLANS.clear();superadmin.PLANS.update(PLANS)

def current_plan(cid):
 c=db();m=c.execute('SELECT plan FROM company_admin_meta WHERE company_id=?',(cid,)).fetchone();c.close();return m['plan'] if m and m['plan'] in PLANS else 'Prueba'

def has_module(cid,module):return module in PLANS[current_plan(cid)]['modules']

@app.before_request
def plan_entitlement_guard():
 cid=session.get('company_id')
 if not cid:return None
 path=request.path
 route_modules=[('/cashflow','cashflow'),('/receivables','receivables'),('/payables','payables'),('/quotations','quotations'),('/quotation/','quotations'),('/budgets','budgets'),('/budget/','budgets'),('/clients','clients'),('/apus','apus'),('/apu/','apus'),('/projects','projects'),('/project/','control')]
 module=next((m for prefix,m in route_modules if path==prefix or path.startswith(prefix)),None)
 if module and not has_module(cid,module):
  flash(f'Esta función no está incluida en tu plan {current_plan(cid)}. Mejora tu plan para desbloquearla.')
  return redirect('/billing')
 # Usuarios incluye al administrador propietario. Prueba=1, Básico=2, Pro=8, Empresa=ilimitados.
 if request.method=='POST' and path=='/team':
  plan=current_plan(cid);limit=PLANS[plan]['users']
  if limit is not None:
   c=db();employees=c.execute('SELECT COUNT(*) n FROM company_users WHERE company_id=?',(cid,)).fetchone()['n'];c.close()
   if 1+employees>=limit:
    flash(f'Has alcanzado el límite de {limit} usuarios de tu plan {plan}. Mejora tu plan para agregar más personas.')
    return redirect('/team')
