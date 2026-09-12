# OBRAX 3.0 MVP

Incluye:
- Registro e inicio de sesión por empresa
- Dashboard
- Clientes
- Obras
- APUs
- Presupuestos
- Conversión Presupuesto → Cotización
- Estados de cotización
- Vista imprimible / guardar como PDF desde el navegador

## Probar localmente
pip install -r requirements.txt
python app.py

Abrir:
http://127.0.0.1:5000

## Despliegue web
Build command:
pip install -r requirements.txt

Start command:
gunicorn app:app

Variable recomendada:
OBRAX_SECRET = una clave larga y aleatoria

## Próxima etapa recomendada
- PostgreSQL para producción
- Base de precios
- Costos reales de obra
- Compras y proveedores
- Control presupuesto vs real
- Roles de usuario
- Recuperación de contraseña
- CSRF y endurecimiento de seguridad
- IA para creación asistida de APUs
