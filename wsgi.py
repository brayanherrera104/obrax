# OBRAX WSGI entrypoint: carga la app principal y registra módulos de plataforma.
from app import app
import superadmin  # noqa: F401,E402
import control_obra  # noqa: F401,E402
import budget_link  # noqa: F401,E402
import budget_coverage  # noqa: F401,E402
import dashboard_patch  # noqa: F401,E402
import receivables  # noqa: F401,E402
import cashflow  # noqa: F401,E402
import team  # noqa: F401,E402
import employee_auth  # noqa: F401,E402
import projects_access  # noqa: F401,E402
