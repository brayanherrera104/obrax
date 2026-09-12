
from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3, os
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import date, timedelta

app = Flask(__name__)
app.secret_key = os.environ.get("OBRAX_SECRET", "change-this-secret")
DB = os.path.join(os.path.dirname(__file__), "obrax.db")

def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    c = db()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS companies(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        nit TEXT,
        admin_name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        phone TEXT,
        password_hash TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS clients(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        nit TEXT,
        contact TEXT,
        phone TEXT,
        email TEXT
    );

    CREATE TABLE IF NOT EXISTS projects(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL,
        client_id INTEGER,
        name TEXT NOT NULL,
        client TEXT,
        value REAL DEFAULT 0,
        status TEXT DEFAULT 'En preparación'
    );

    CREATE TABLE IF NOT EXISTS apus(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        unit TEXT NOT NULL,
        admin_pct REAL DEFAULT 8,
        conting_pct REAL DEFAULT 2,
        util_pct REAL DEFAULT 10
    );

    CREATE TABLE IF NOT EXISTS apu_items(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        apu_id INTEGER NOT NULL,
        resource_type TEXT,
        name TEXT NOT NULL,
        unit TEXT,
        qty REAL DEFAULT 0,
        waste_pct REAL DEFAULT 0,
        price REAL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS budgets(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL,
        project_id INTEGER,
        client_id INTEGER,
        name TEXT NOT NULL,
        created_at TEXT NOT NULL,
        validity_days INTEGER DEFAULT 15,
        status TEXT DEFAULT 'Borrador'
    );

    CREATE TABLE IF NOT EXISTS budget_items(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        budget_id INTEGER NOT NULL,
        chapter TEXT,
        apu_id INTEGER,
        description TEXT NOT NULL,
        unit TEXT,
        quantity REAL DEFAULT 1,
        unit_price REAL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS quotations(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL,
        budget_id INTEGER NOT NULL,
        quote_number TEXT NOT NULL,
        created_at TEXT NOT NULL,
        validity_days INTEGER DEFAULT 15,
        status TEXT DEFAULT 'Borrador',
        terms TEXT,
        observations TEXT
    );
    """)
    c.commit()
    c.close()

@app.before_request
def ensure_db():
    init_db()

def login_required(f):
    @wraps(f)
    def w(*a, **k):
        if session.get("company_id"):
            return f(*a, **k)
        return redirect(url_for("login"))
    return w

def company():
    if not session.get("company_id"):
        return None
    c=db()
    r=c.execute("SELECT * FROM companies WHERE id=?", (session["company_id"],)).fetchone()
    c.close()
    return r

def apu_cost(c, apu_id):
    a=c.execute("SELECT * FROM apus WHERE id=?", (apu_id,)).fetchone()
    if not a: return 0,0
    items=c.execute("SELECT * FROM apu_items WHERE apu_id=?", (apu_id,)).fetchall()
    direct=sum((x["qty"] or 0)*(1+(x["waste_pct"] or 0)/100)*(x["price"] or 0) for x in items)
    price=direct*(1+(a["admin_pct"] or 0)/100+(a["conting_pct"] or 0)/100)*(1+(a["util_pct"] or 0)/100)
    return direct, price

def budget_total(c, budget_id):
    rows=c.execute("SELECT quantity, unit_price FROM budget_items WHERE budget_id=?", (budget_id,)).fetchall()
    return sum((r["quantity"] or 0)*(r["unit_price"] or 0) for r in rows)

@app.route("/")
def landing():
    return render_template("landing.html")

@app.route("/demo")
def demo():
    session.clear()
    session["demo"]=True
    return redirect(url_for("dashboard"))

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method=="POST":
        p=request.form["password"]
        if len(p)<6:
            flash("La contraseña debe tener mínimo 6 caracteres.")
            return render_template("register.html")
        c=db()
        try:
            r=c.execute(
                "INSERT INTO companies(name,nit,admin_name,email,phone,password_hash) VALUES(?,?,?,?,?,?)",
                (request.form["company_name"], request.form.get("nit",""), request.form["admin_name"],
                 request.form["email"].lower(), request.form.get("phone",""), generate_password_hash(p))
            )
            c.commit()
            session.clear()
            session["company_id"]=r.lastrowid
            c.close()
            return redirect(url_for("dashboard"))
        except sqlite3.IntegrityError:
            c.close()
            flash("Ese correo ya está registrado.")
    return render_template("register.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        c=db()
        r=c.execute("SELECT * FROM companies WHERE email=?", (request.form["email"].lower(),)).fetchone()
        c.close()
        if r and check_password_hash(r["password_hash"], request.form["password"]):
            session.clear()
            session["company_id"]=r["id"]
            return redirect(url_for("dashboard"))
        flash("Correo o contraseña incorrectos.")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))

@app.route("/dashboard")
def dashboard():
    if not session.get("company_id") and not session.get("demo"):
        return redirect(url_for("login"))

    if session.get("demo"):
        projects=[
            {"name":"Cerramiento estación TM","client":"Cliente Demo","value":185000000,"status":"En ejecución"},
            {"name":"Estructura metálica bodega","client":"Cliente Industrial","value":320000000,"status":"Cotización"}
        ]
        return render_template("dashboard.html", company={"name":"Constructora Demo S.A.S."},
            projects=projects, apus_count=12, clients_count=8, budgets_count=5,
            quotes_count=3, quoted_total=505000000, demo=True)

    co=company()
    c=db()
    projects=c.execute("""
        SELECT p.*, COALESCE(cl.name,p.client,'') client_name
        FROM projects p LEFT JOIN clients cl ON cl.id=p.client_id
        WHERE p.company_id=? ORDER BY p.id DESC LIMIT 8
    """,(co["id"],)).fetchall()
    apus_count=c.execute("SELECT COUNT(*) n FROM apus WHERE company_id=?",(co["id"],)).fetchone()["n"]
    clients_count=c.execute("SELECT COUNT(*) n FROM clients WHERE company_id=?",(co["id"],)).fetchone()["n"]
    budgets_count=c.execute("SELECT COUNT(*) n FROM budgets WHERE company_id=?",(co["id"],)).fetchone()["n"]
    quotes_count=c.execute("SELECT COUNT(*) n FROM quotations WHERE company_id=?",(co["id"],)).fetchone()["n"]
    quote_rows=c.execute("SELECT budget_id FROM quotations WHERE company_id=?",(co["id"],)).fetchall()
    quoted_total=sum(budget_total(c,r["budget_id"]) for r in quote_rows)
    c.close()
    return render_template("dashboard.html", company=co, projects=projects, apus_count=apus_count,
        clients_count=clients_count, budgets_count=budgets_count, quotes_count=quotes_count,
        quoted_total=quoted_total, demo=False)

@app.route("/clients", methods=["GET","POST"])
@login_required
def clients():
    co=company(); c=db()
    if request.method=="POST":
        c.execute("""INSERT INTO clients(company_id,name,nit,contact,phone,email)
                     VALUES(?,?,?,?,?,?)""",
                  (co["id"], request.form["name"], request.form.get("nit",""),
                   request.form.get("contact",""), request.form.get("phone",""),
                   request.form.get("email","")))
        c.commit()
        flash("Cliente creado.")
        return redirect(url_for("clients"))
    rows=c.execute("SELECT * FROM clients WHERE company_id=? ORDER BY id DESC",(co["id"],)).fetchall()
    c.close()
    return render_template("clients.html", clients=rows)

@app.route("/projects", methods=["GET","POST"])
@login_required
def projects():
    co=company(); c=db()
    clients=c.execute("SELECT * FROM clients WHERE company_id=? ORDER BY name",(co["id"],)).fetchall()
    if request.method=="POST":
        client_id=request.form.get("client_id") or None
        client_name=""
        if client_id:
            rr=c.execute("SELECT name FROM clients WHERE id=? AND company_id=?",(client_id,co["id"])).fetchone()
            client_name=rr["name"] if rr else ""
        c.execute("""INSERT INTO projects(company_id,client_id,name,client,value,status)
                     VALUES(?,?,?,?,?,?)""",
                  (co["id"], client_id, request.form["name"], client_name,
                   float(request.form.get("value",0) or 0),
                   request.form.get("status","En preparación")))
        c.commit()
        flash("Obra creada.")
        return redirect(url_for("projects"))
    rows=c.execute("""
        SELECT p.*, COALESCE(cl.name,p.client,'') client_name
        FROM projects p LEFT JOIN clients cl ON cl.id=p.client_id
        WHERE p.company_id=? ORDER BY p.id DESC
    """,(co["id"],)).fetchall()
    c.close()
    return render_template("projects.html", projects=rows, clients=clients)

@app.route("/apus", methods=["GET","POST"])
def apus():
    demo=session.get("demo"); co=company()
    if not demo and not co:
        return redirect(url_for("login"))

    if request.method=="POST" and not demo:
        c=db()
        r=c.execute("""INSERT INTO apus(company_id,name,unit,admin_pct,conting_pct,util_pct)
                       VALUES(?,?,?,?,?,?)""",
          (co["id"], request.form["name"], request.form["unit"],
           float(request.form.get("admin_pct",8) or 0),
           float(request.form.get("conting_pct",2) or 0),
           float(request.form.get("util_pct",10) or 0)))
        aid=r.lastrowid
        names=request.form.getlist("item_name[]")
        types=request.form.getlist("item_type[]")
        units=request.form.getlist("item_unit[]")
        qty=request.form.getlist("item_qty[]")
        waste=request.form.getlist("item_waste[]")
        price=request.form.getlist("item_price[]")
        for i,n in enumerate(names):
            if n.strip():
                c.execute("""INSERT INTO apu_items(apu_id,resource_type,name,unit,qty,waste_pct,price)
                             VALUES(?,?,?,?,?,?,?)""",
                    (aid, types[i], n, units[i],
                     float(qty[i] or 0), float(waste[i] or 0), float(price[i] or 0)))
        c.commit(); c.close()
        flash("APU guardado correctamente.")
        return redirect(url_for("apus"))

    if demo:
        rows=[
            {"name":"Fabricación y montaje de estructura metálica","unit":"kg","direct":4200,"price":5082},
            {"name":"Pintura anticorrosiva","unit":"m²","direct":18500,"price":22385},
            {"name":"Cerramiento metálico","unit":"m²","direct":128000,"price":154880}
        ]
        return render_template("apus.html", apus=rows, demo=True)

    c=db(); data=[]
    for a in c.execute("SELECT * FROM apus WHERE company_id=? ORDER BY id DESC",(co["id"],)).fetchall():
        direct,price=apu_cost(c,a["id"])
        data.append({**dict(a),"direct":direct,"price":price})
    c.close()
    return render_template("apus.html", apus=data, demo=False)

@app.route("/apu/new")
@login_required
def new_apu():
    return render_template("apu_form.html")

@app.route("/budgets", methods=["GET","POST"])
@login_required
def budgets():
    co=company(); c=db()
    projects=c.execute("SELECT * FROM projects WHERE company_id=? ORDER BY name",(co["id"],)).fetchall()
    clients=c.execute("SELECT * FROM clients WHERE company_id=? ORDER BY name",(co["id"],)).fetchall()
    if request.method=="POST":
        r=c.execute("""INSERT INTO budgets(company_id,project_id,client_id,name,created_at,validity_days,status)
                       VALUES(?,?,?,?,?,?,?)""",
                    (co["id"], request.form.get("project_id") or None,
                     request.form.get("client_id") or None, request.form["name"],
                     date.today().isoformat(), int(request.form.get("validity_days",15) or 15), "Borrador"))
        c.commit()
        bid=r.lastrowid
        c.close()
        return redirect(url_for("budget_detail", budget_id=bid))
    rows=c.execute("""
        SELECT b.*, p.name project_name, cl.name client_name
        FROM budgets b
        LEFT JOIN projects p ON p.id=b.project_id
        LEFT JOIN clients cl ON cl.id=b.client_id
        WHERE b.company_id=? ORDER BY b.id DESC
    """,(co["id"],)).fetchall()
    data=[]
    for b in rows:
        data.append({**dict(b),"total":budget_total(c,b["id"])})
    c.close()
    return render_template("budgets.html", budgets=data, projects=projects, clients=clients)

@app.route("/budget/<int:budget_id>", methods=["GET","POST"])
@login_required
def budget_detail(budget_id):
    co=company(); c=db()
    b=c.execute("SELECT * FROM budgets WHERE id=? AND company_id=?",(budget_id,co["id"])).fetchone()
    if not b:
        c.close(); return "Presupuesto no encontrado",404

    if request.method=="POST":
        apu_id=request.form.get("apu_id") or None
        description=request.form.get("description","")
        unit=request.form.get("unit","")
        unit_price=float(request.form.get("unit_price",0) or 0)
        if apu_id:
            a=c.execute("SELECT * FROM apus WHERE id=? AND company_id=?",(apu_id,co["id"])).fetchone()
            if a:
                description=a["name"]; unit=a["unit"]; _,unit_price=apu_cost(c,a["id"])
        c.execute("""INSERT INTO budget_items(budget_id,chapter,apu_id,description,unit,quantity,unit_price)
                     VALUES(?,?,?,?,?,?,?)""",
                  (budget_id, request.form.get("chapter","General"), apu_id,
                   description, unit, float(request.form.get("quantity",1) or 1), unit_price))
        c.commit()
        return redirect(url_for("budget_detail",budget_id=budget_id))

    items=c.execute("SELECT * FROM budget_items WHERE budget_id=? ORDER BY id",(budget_id,)).fetchall()
    apus=c.execute("SELECT * FROM apus WHERE company_id=? ORDER BY name",(co["id"],)).fetchall()
    total=budget_total(c,budget_id)
    c.close()
    return render_template("budget_detail.html", budget=b, items=items, apus=apus, total=total)

@app.route("/budget/<int:budget_id>/quote", methods=["POST"])
@login_required
def create_quote(budget_id):
    co=company(); c=db()
    b=c.execute("SELECT * FROM budgets WHERE id=? AND company_id=?",(budget_id,co["id"])).fetchone()
    if not b:
        c.close(); return "Presupuesto no encontrado",404
    existing=c.execute("SELECT * FROM quotations WHERE budget_id=? AND company_id=?",(budget_id,co["id"])).fetchone()
    if existing:
        c.close()
        return redirect(url_for("quotation_detail", quote_id=existing["id"]))
    count=c.execute("SELECT COUNT(*) n FROM quotations WHERE company_id=?",(co["id"],)).fetchone()["n"]+1
    qnum=f"COT-{date.today().year}-{count:04d}"
    r=c.execute("""INSERT INTO quotations(company_id,budget_id,quote_number,created_at,validity_days,status,terms,observations)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (co["id"],budget_id,qnum,date.today().isoformat(),b["validity_days"],"Borrador",
                 "50% anticipo, saldo contra avance o entrega.",""))
    c.commit(); qid=r.lastrowid; c.close()
    flash("Cotización generada desde el presupuesto.")
    return redirect(url_for("quotation_detail",quote_id=qid))

@app.route("/quotations")
@login_required
def quotations():
    co=company(); c=db()
    rows=c.execute("""
        SELECT q.*, b.name budget_name
        FROM quotations q JOIN budgets b ON b.id=q.budget_id
        WHERE q.company_id=? ORDER BY q.id DESC
    """,(co["id"],)).fetchall()
    data=[]
    for q in rows:
        data.append({**dict(q),"total":budget_total(c,q["budget_id"])})
    c.close()
    return render_template("quotations.html", quotations=data)

@app.route("/quotation/<int:quote_id>", methods=["GET","POST"])
@login_required
def quotation_detail(quote_id):
    co=company(); c=db()
    q=c.execute("""
        SELECT q.*, b.name budget_name, b.client_id, b.project_id,
               cl.name client_name, cl.nit client_nit, cl.contact client_contact,
               cl.phone client_phone, cl.email client_email,
               p.name project_name
        FROM quotations q
        JOIN budgets b ON b.id=q.budget_id
        LEFT JOIN clients cl ON cl.id=b.client_id
        LEFT JOIN projects p ON p.id=b.project_id
        WHERE q.id=? AND q.company_id=?
    """,(quote_id,co["id"])).fetchone()
    if not q:
        c.close(); return "Cotización no encontrada",404
    if request.method=="POST":
        c.execute("""UPDATE quotations SET status=?, terms=?, observations=? WHERE id=? AND company_id=?""",
                  (request.form["status"],request.form.get("terms",""),
                   request.form.get("observations",""),quote_id,co["id"]))
        c.commit()
        flash("Cotización actualizada.")
        return redirect(url_for("quotation_detail",quote_id=quote_id))
    items=c.execute("SELECT * FROM budget_items WHERE budget_id=?",(q["budget_id"],)).fetchall()
    total=budget_total(c,q["budget_id"])
    c.close()
    return render_template("quotation_detail.html", q=q, items=items, total=total, company=co)

if __name__=="__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",5000)), debug=os.environ.get("FLASK_DEBUG")=="1")
