from flask import request,session,redirect,flash
from app import app,db,PG
from plans import plan_limit


def ensure_plan_capacity_tables():
 c=db()
 c.execute('''CREATE TABLE IF NOT EXISTS plan_project_access(company_id INTEGER NOT NULL,project_id INTEGER NOT NULL,is_enabled INTEGER DEFAULT 1,PRIMARY KEY(company_id,project_id))''')
 c.commit();c.close()


def sync_project_capacity(company_id,plan):
 """Never deletes projects. Keeps only the plan allowance operational when over limit."""
 ensure_plan_capacity_tables();c=db();projects=c.execute('SELECT id FROM projects WHERE company_id=? ORDER BY id DESC',(company_id,)).fetchall();ids=[x['id'] for x in projects];limit=plan_limit(plan,'projects')
 if limit is None:
  for pid in ids:c.execute('INSERT INTO plan_project_access(company_id,project_id,is_enabled) VALUES(?,?,1) ON CONFLICT(company_id,project_id) DO UPDATE SET is_enabled=1',(company_id,pid))
 else:
  existing={x['project_id']:int(x['is_enabled'] or 0) for x in c.execute('SELECT project_id,is_enabled FROM plan_project_access WHERE company_id=?',(company_id,)).fetchall()}
  enabled=[pid for pid in ids if existing.get(pid)==1]
  # First sync after a downgrade: preserve up to the limit, prioritizing the newest projects.
  if not existing:
   enabled=ids[:limit]
  elif len(enabled)>limit:
   enabled=enabled[:limit]
  elif len(enabled)<limit:
   for pid in ids:
    if pid not in enabled and pid not in existing:
     enabled.append(pid)
     if len(enabled)>=limit:break
  enabled_set=set(enabled)
  for pid in ids:
   val=1 if pid in enabled_set else 0
   c.execute('INSERT INTO plan_project_access(company_id,project_id,is_enabled) VALUES(?,?,?) ON CONFLICT(company_id,project_id) DO UPDATE SET is_enabled=?',(company_id,pid,val,val))
 c.commit();c.close()


def project_plan_enabled(company_id,project_id):
 c=db();x=c.execute('SELECT is_enabled FROM plan_project_access WHERE company_id=? AND project_id=?',(company_id,project_id)).fetchone();c.close();return True if not x else bool(x['is_enabled'])


def set_project_plan_enabled(company_id,project_id,enabled,plan):
 sync_project_capacity(company_id,plan);limit=plan_limit(plan,'projects');c=db();p=c.execute('SELECT id FROM projects WHERE id=? AND company_id=?',(project_id,company_id)).fetchone()
 if not p:c.close();return False,'Obra no encontrada.'
 if enabled and limit is not None:
  used=c.execute('SELECT COUNT(*) n FROM plan_project_access WHERE company_id=? AND is_enabled=1',(company_id,)).fetchone()['n']
  if used>=limit:c.close();return False,f'Tu plan {plan} permite {limit} obras operativas. Desactiva una obra antes de activar otra.'
 c.execute('INSERT INTO plan_project_access(company_id,project_id,is_enabled) VALUES(?,?,?) ON CONFLICT(company_id,project_id) DO UPDATE SET is_enabled=?',(company_id,project_id,int(enabled),int(enabled)));c.commit();c.close();return True,'Obra activada para operar.' if enabled else 'Obra pasó a modo solo consulta.'

@app.before_request
def plan_project_capacity_guard():
 cid=session.get('company_id');plan=session.get('company_plan')
 if not cid or not plan:return None
 sync_project_capacity(cid,plan)
 path=request.path
 if not path.startswith('/project/'):return None
 try:pid=int(path.split('/')[2])
 except:return None
 if project_plan_enabled(cid,pid):return None
 # Excess projects remain visible/readable, but cannot be operated on.
 if request.method not in ('GET','HEAD','OPTIONS'):
  flash('Esta obra está en modo solo consulta porque excede el límite de obras de tu plan. Activa otra obra o mejora tu plan para operarla.');return redirect('/projects')

ensure_plan_capacity_tables()
