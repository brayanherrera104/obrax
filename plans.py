# OBRAX 5.2 - catálogo único de planes, límites y funcionalidades.
# Toda la aplicación debe consultar este archivo para evitar diferencias entre precios y bloqueos.
# El límite 'users' corresponde a usuarios adicionales del equipo; el administrador principal va incluido aparte.

PLAN_MODULES = {
    'core': {'dashboard','apus','clients','projects','budgets','quotations','control','payables'},
    'financial': {'receivables','retentions','cashflow','treasury','treasury_alerts','financial_sheet'},
}

PLANS = {
    'Prueba': {
        'monthly': 0, 'annual': 0, 'trial_days': 14,
        'users': 1, 'projects': 3, 'apus': 10,
        'description': 'Prueba OBRAX Pro durante 14 días.',
        'features': ['1 usuario adicional + administrador','Hasta 3 obras','Hasta 10 APUs','Funciones Pro durante 14 días'],
        'modules': PLAN_MODULES['core'] | PLAN_MODULES['financial'],
    },
    'Básico': {
        'monthly': 49900, 'annual': 499000,
        'users': 2, 'projects': 5, 'apus': 50,
        'description': 'Para independientes y equipos pequeños que necesitan controlar sus obras.',
        'features': ['2 usuarios adicionales + administrador','Hasta 5 obras','Hasta 50 APUs','Presupuestos y cotizaciones PDF','Control de obra y cuentas por pagar'],
        'modules': PLAN_MODULES['core'],
    },
    'Pro': {
        'monthly': 99900, 'annual': 999000,
        'users': 8, 'projects': 20, 'apus': None,
        'description': 'Control operativo y financiero completo para empresas en crecimiento.',
        'features': ['8 usuarios adicionales + administrador','Hasta 20 obras','APUs ilimitados','Cartera y retenciones','Flujo de caja y tesorería','Alertas y ficha financiera','Reportes avanzados'],
        'modules': PLAN_MODULES['core'] | PLAN_MODULES['financial'],
    },
    'Empresa': {
        'monthly': 149900, 'annual': 1499000,
        'users': None, 'projects': None, 'apus': None,
        'description': 'Para empresas con múltiples equipos y operación sin límites.',
        'features': ['Usuarios adicionales ilimitados + administrador','Obras ilimitadas','APUs ilimitados','Todo OBRAX Pro','Roles y permisos avanzados','Auditoría completa','Soporte prioritario'],
        'modules': PLAN_MODULES['core'] | PLAN_MODULES['financial'] | {'audit'},
    },
}

PLAN_ORDER = ('Prueba','Básico','Pro','Empresa')

def normalize_plan(name):
    return name if name in PLANS else 'Prueba'

def plan_limit(name, resource):
    return PLANS[normalize_plan(name)].get(resource)

def plan_has_module(name, module):
    return module in PLANS[normalize_plan(name)]['modules']
