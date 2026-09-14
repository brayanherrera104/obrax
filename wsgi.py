# OBRAX WSGI entrypoint: carga la app principal y registra las rutas del Superadmin.
from app import app
import superadmin  # noqa: F401,E402
