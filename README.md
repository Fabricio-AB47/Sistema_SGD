# Sistema_SGD

Guía rápida del entorno y de los flujos implementados.

## Requisitos
- Python 3.12+ y virtualenv
- Node.js (npm)
- SQL Server con ODBC Driver 17

## Backend (Django)
Dependencias clave (instaladas en la venv):
- Django 5.2.10, mssql-django, pyodbc
- python-dotenv / django-environ
- pandas, openpyxl, SQLAlchemy, requests, gunicorn, python-docx
- django-rq, django-redis, redis (cliente)

### .env de ejemplo
```
DEBUG=1
SECRET_KEY=tu_clave_segura
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost

DB_ENGINE=mssql
DB_NAME=***
DB_USER=**
DB_PASSWORD=***
DB_HOST=****
DB_PORT=***
DB_ODBC_DRIVER=ODBC Driver 17 for SQL Server
DB_ODBC_EXTRA_PARAMS=TrustServerCertificate=yes;Encrypt=no
```

### Pasos backend
1) Activar venv: `.\.venv\Scripts\activate`
2) Instalar deps (si aplica): `pip install -r requirements.txt` (o manual según lista arriba)
3) Migraciones: solo se aplicaron las de Django core; las tablas de negocio ya existen (modelos con `managed=False`)
4) Ejecutar: `python manage.py runserver`

> Nota: se parcheó localmente mssql-django para permitir SQL Server 2025 (versión 17 en `mssql/base.py`). Si reinstalas el paquete, revisa compatibilidad o reaplica el cambio.

## Frontend (Gulp)
Rutas:
- Fuente SCSS/JS/img: `frontend/src`
- Salida: `frontend/static/dist` (`css`, `js`, `img`)
- Plantillas Django: `frontend/templates`

Scripts npm:
- `npm run build` (compila estilos/JS/img)
- `npm run dev` (watch)

Pasos:
```
cd frontend
npm install
npm run build   # o npm run dev
```

## Login y home
- `/login`: correo + contraseña; guarda `usuario_id` en sesión.
- `/`: muestra estado de conexión a BD y usuario logueado; redirige a login si no hay sesión.

## Apps y archivos clave
- `apps/seguridad/models.py`: modelos `Usuario`, `UsuarioCredencial`, `Rol`, `UsuarioRol`, etc. (`managed=False`), `EmailVerificationToken`.
- `apps/seguridad/auth_backend.py`: autenticación por correo (hash PBKDF2 en VARBINARY).
- `apps/seguridad/middleware.py`: renueva `user_session` y `last_seen_at` según `SESSION_IDLE_MINUTES` (15 min default).
- `apps/seguridad/views.py`: login/logout, verificación de correo (tokens 24h, reenvío limitado), sesiones/actividad, formularios básicos de usuario.
- `apps/seguridad/email_service.py`: SMTP (Gmail/Office365) configurable por env.
- `apps/seguridad/management/commands/cleanup_expired_tokens.py`: limpia tokens expirados.
- `apps/core/views.py`: formularios para criterio, subcriterio, indicador y tipo de indicador.
- `frontend/templates/admin/*.html`: vistas admin; `user_create.html` tiene modales para listar/editar usuarios y selector de roles.
- `frontend/src/pages/_catalogs.scss` y `_user_create.scss`: estilos para catálogos y usuarios/roles.

## Verificación de correo
- Tablas: `usuario` (`correo_verificado`) y `email_verification_token` (hash + prefijo, expira 24h).
- Rutas: `/seguridad/solicitar-verificacion/`, `/seguridad/reenviar-verificacion/`, `/seguridad/verificar-correo/<token>/`.
- Reenvío: máx. 3 por hora por usuario; guarda IP y user-agent.

## Modal de usuarios (admin)
- Botón **Ver usuarios** abre un modal con la tabla y acciones **Editar/Eliminar**.
- Botón **Editar** abre otro modal con todos los campos y subpantalla de roles; los roles seleccionados viajan en `roles_edit_selected` (CSV de IDs). Ajusta tu endpoint `/admin/usuarios/<id>/editar` para procesarlo.

## Sesiones / actividad
- `SESSION_IDLE_MINUTES` en `settings.py` controla inactividad (default 15 min).
- Zona horaria: `America/Guayaquil`, `USE_TZ=True`.

## Ejecución rápida
```
.\.venv\Scripts\activate
python manage.py runserver

cd frontend
npm install
npm run dev   # o build
```

## Notas para futuros cambios
- Mantén `managed=False` en modelos de tablas existentes; evita migraciones sobre ellas.
- Si reinstalas `mssql-django`, revisa compatibilidad con SQL Server 2025 (parche versión 17).
- Ajusta rutas de editar/eliminar usuario según tu backend real.
- Implementa en backend la lectura de `roles_edit_selected` al guardar ediciones.
