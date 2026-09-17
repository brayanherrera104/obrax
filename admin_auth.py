from flask import request,session,redirect,flash
from werkzeug.security import check_password_hash
from app import app,db


@app.before_request
def administrator_login_bridge():
    """Authenticate company administrators with normalized email input.

    Older/new registrations may contain accidental surrounding spaces in the
    stored email. The base login compares the value literally, so a valid
    administrator can be rejected even though the company exists. This bridge
    normalizes both sides without changing or deleting company data.
    """
    if request.path != '/login' or request.method != 'POST':
        return None

    email = request.form.get('email','').strip().lower()
    password = request.form.get('password','')
    if not email or not password:
        return None

    c = db()
    try:
        row = c.execute(
            'SELECT * FROM companies WHERE LOWER(TRIM(email))=?',
            (email,)
        ).fetchone()
    except Exception:
        row = None
    c.close()

    # If it is not a company administrator, let employee_auth handle it.
    if not row:
        return None

    if not check_password_hash(row['password_hash'],password):
        flash('Correo o contraseña incorrectos.')
        return redirect('/login')

    session.clear()
    session['company_id'] = row['id']
    return redirect('/dashboard')
