from flask import request,session,redirect,flash
from app import app,db
from plans import plan_limit


def ensure_plan_capacity_tables():
 c=db()
 c.execute('''CREATE TABLE IF NOT EXISTS plan_project_access(company_id INTEGER NOT NULL,project_id INTEGER NOT NULL,is_enabled INTEGER DEFAULT 1,PRIMARY KEY(company_id,project_id))''')
 c.execute('''CREATE TABLE IF NOT EXISTS plan_user_access(company_id INTEGER NOT NULL,user_id INTEGER NOT NULL,is_enabled INTEGER DEFAULT 1,PRIMARY KEY(company_id,user_id))''')
 c.execute('''CREATE TABLE IF NOT EXISTS plan_apu_access(company_id INTEGER NOT NULL,apu_id INTEGER NOT NULL,is_enabled INTEGER DEFAULT 1,PRIMARY KEY(company_id,apu_id))''')
 c.commit();c.close()


def _sync_capacity(company_id,plan,resource,table,id_col,source_table):
 ensure_plan_capacity_tables();c=db();rows=c.execute(f'SELECT id FROM {source_table} WHERE company_id=? ORDER BY id DESC',(company_id,)).fetchall();ids=[x['id'] for x in rows];limit=plan_limit(plan,resource)
 if limit is None:
  for rid in ids:c.execute(f'INSERT INTO {table}(company_id,{id_col},is_enabled) VALUES(?,?,1) ON CONFLICT(company_id,{id_col}) DO UPDATE SET is_enabled=1',(company_id,rid))
 else:
  existing={x[id_col]:int(x['is_enabled'] or 0) for x in c.execute(f'SELECT {id_col},is_enabled FROM {table} WHERE company_id=?',(company_id,)).fetchall()}
  enabled=[rid for rid in ids if existing.get(rid)==1]
  if not existing:enabled=ids[:limit]
  elif len(enabled)>limit:enabled=enabled[:limit]
  elif len(enabled)<limit:
   for rid in ids:
    if rid not in enabled and rid not in existing:
     enabled.append(rid)
     if len(enabled)>=limit:break
  enabled_set=set(enabled)
  for rid in ids:
   val=1 if rid in enabled_set else 0;c.execute(f'INSERT INTO {table}(company_id,{id_col},is_enabled) VALUES(?,?,?) ON CONFLICT(company_id,{id_col}) DO UPDATE SET is_enabled=?',(company_id,rid,val,val))
 c.commit();c.close()

def sync_project_capacity(company_id,plan):_sync_capacity(company_id,plan,'projects','plan_project_access','project_id','projects')
def sync_user_capacity(company_id,plan):_sync_capacity(company_id,plan,'users','plan_user_access','user_id','company_users')
def sync_apu_capacity(company_id,plan):_sync_capacity(company_id,plan,'apus','plan_apu_access','apu_id','apus')

def _enabled(company_id,rid,table,id_col):
 c=db();x=c.execute(f'SELECT is_enabled FROM {table} WHERE company_id=? AND {id_col}=?',(company_id,rid)).fetchone();c.close();return True if not x else bool(x['is_enabled'])
def project_plan_enabled(company_id,project_id):return _enabled(company_id,project_id,'plan_project_access','project_id')
def user_plan_enabled(company_id,user_id):return _enabled(company_id,user_id,'plan_user_access','user_id')
def apu_plan_enabled(company_id,apu_id):return _enabled(company_id,apu_id,'plan_apu_access','apu_id')

def _set_enabled(company_id,rid,enabled,plan,resource,table,id_col,source_table,label):
 _sync_capacity(company_id,plan,resource,table,id_col,source_table);limit=plan_limit(plan,resource);c=db();row=c.execute(f'SELECT id FROM {source_table} WHERE id=? AND company_id=?',(rid,company_id)).fetchone()
 if not row:c.close();return False,f'{label} no encontrado.'
 if enabled and limit is not None:
  used=c.execute(f'SELECT COUNT(*) n FROM {table} WHERE company_id=? AND is_enabled=1',(company_id,)).fetchone()['n']
  if used>=limit:c.close();return False,f'Tu plan {plan} permite {limit} {label.lower()}s operativos. Libera un cupo antes de activar otro.'
 c.execute(f'INSERT INTO {table}(company_id,{id_col},is_enabled) VALUES(?,?,?) ON CONFLICT(company_id,{id_col}) DO UPDATE SET is_enabled=?',(company_id,rid,int(enabled),int(enabled)));c.commit();c.close();return True,f'{label} activado.' if enabled else f'{label} pasó a modo solo consulta.'

def set_project_plan_enabled(company_id,project_id,enabled,plan):return _set_enabled(company_id,project_id,enabled,plan,'projects','plan_project_access','project_id','projects','Obra')
def set_user_plan_enabled(company_id,user_id,enabled,plan):return _set_enabled(company_id,user_id,enabled,plan,'users','plan_user_access','user_id','company_users','Usuario')
def set_apu_plan_enabled(company_id,apu_id,enabled,plan):return _set_enabled(company_id,apu_id,enabled,plan,'apus','plan_apu_access','apu_id','apus','APU')

@app.route('/team/<int:user_id>/plan-access/<action>',methods=['POST'])
def user_plan_access(user_id,action):
 if not session.get('company_id') or session.get('user_id'):return redirect('/dashboard')
 plan=session.get('company_plan','Prueba');ok,msg=set_user_plan_enabled(session['company_id'],user_id,action=='activate',plan);flash(msg);return redirect('/team')

@app.route('/apu/<int:apu_id>/plan-access/<action>',methods=['POST'])
def apu_plan_access(apu_id,action):
 if not session.get('company_id'):return redirect('/login')
 plan=session.get('company_plan','Prueba');ok,msg=set_apu_plan_enabled(session['company_id'],apu_id,action=='activate',plan);flash(msg);return redirect('/apus')

@app.before_request
def plan_capacity_guard():
 cid=session.get('company_id');plan=session.get('company_plan')
 if not cid or not plan:return None
 sync_project_capacity(cid,plan);sync_user_capacity(cid,plan);sync_apu_capacity(cid,plan)
 if session.get('user_id') and not user_plan_enabled(cid,session['user_id']):
  session.clear();flash('Tu usuario está fuera de los cupos activos del plan de la empresa. Contacta al administrador.');return redirect('/login')
 path=request.path
 if path.startswith('/project/'):
  try:rid=int(path.split('/')[2])
  except:return None
  if not project_plan_enabled(cid,rid) and request.method not in ('GET','HEAD','OPTIONS'):
   flash('Esta obra está en modo solo consulta porque excede el límite de obras de tu plan.');return redirect('/projects')
 if path.startswith('/apu/') and '/plan-access/' not in path:
  try:rid=int(path.split('/')[2])
  except:return None
  if not apu_plan_enabled(cid,rid) and request.method not in ('GET','HEAD','OPTIONS'):
   flash('Este APU está en modo solo consulta porque excede el límite de APUs de tu plan.');return redirect('/apus')

ensure_plan_capacity_tables()
