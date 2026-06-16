## SIG - Sistema Informatico de Gestion

Aplicacion web para administrar la estructura CACES, ciclos de evaluacion, control documental, evidencias, evaluacion, mejora continua, seguridad e integraciones del sistema.

El proyecto usa una arquitectura Django modular sobre SQL Server y consume Microsoft Graph para crear carpetas y administrar documentos protegidos sin almacenar estructura documental local en el servidor.

## Objetivo funcional

- Administrar criterios, subcriterios, indicadores y elementos fundamentales.
- Crear ciclos de evaluacion con documento de autorizacion obligatorio.
- Versionar documentos con `version_documento`.
- Registrar accesos documentales en `documento_acceso_log`.
- Restringir el acceso a documentos protegidos mediante vistas del sistema, sin URL publica directa.
- Integrar Microsoft Graph para carpetas y archivos documentales.

## Herramientas utilizadas

### Backend

- Python 3.12
- Django 6.0.3
- mssql-django
- pyodbc
- python-dotenv
- argon2-cffi
- cryptography

### Base de datos

- SQL Server
- ODBC Driver 18 for SQL Server

### Frontend

- Node.js
- npm
- Gulp
- Sass
- PostCSS
- Autoprefixer
- cssnano

### Integraciones

- Microsoft Graph API
- SharePoint / OneDrive corporativo

## Arquitectura

El proyecto sigue estas reglas:

- Proyecto Django modular.
- Sin logica compleja en views.
- `services` para negocio.
- `selectors` para lectura.
- Templates por modulo.
- Todos los templates internos extienden `dashboard_base.html`.
- La estructura documental se construye por `criterio/subcriterio/indicador/elemento`.
- No se crea ni activa `ciclo_evaluacion` sin documento de autorizacion previo.
- Cada nueva version documental se registra en `version_documento`.
- Cada acceso documental se registra en `documento_acceso_log`.
- Las carpetas documentales se aprovisionan directamente por Microsoft Graph.

## Estructura general del proyecto

```text
SISTEMA INFORMATICO DE GESTION/
|-- backend/
|   |-- SIG/                  # Configuracion principal de Django
|   |-- application/          # Servicios transversales
|   |-- apps/                 # Modulos funcionales
|   |-- requirements/         # Dependencias Python
|   |-- manage.py
|   `-- .env
|-- frontend/
|   |-- src/                  # SCSS, JS, imagenes, fuentes
|   |-- static/               # Assets compilados
|   |-- templates/            # Templates HTML
|   |-- gulpfile.js
|   `-- package.json
|-- AGENTS.md
`-- README.md
```

## Modulos principales

- `apps.core`: catalogos base del sistema.
- `apps.usuarios`: usuarios, roles y relacion usuario-rol.
- `apps.seguridad`: login, sesiones, OTP, recuperacion de contrasena, credenciales.
- `apps.permisos`: permisos por rol y alcance operativo.
- `apps.acreditacion`: estructura CACES, ciclos y acceso por estructura.
- `apps.documentos`: carga, versionado, autorizaciones y acceso protegido a documentos.
- `apps.evidencias`: documentos, versiones, registro de evidencia y log de acceso documental.
- `apps.evaluacion`: evaluaciones y observaciones.
- `apps.informes`: informes de autoevaluacion.
- `apps.mejora`: planes y acciones de mejora.
- `apps.integraciones`: servicios, credenciales, tokens y consumo de APIs.
- `apps.auditoria`: trazabilidad de eventos del sistema.

## Consideraciones de base de datos

- Los modelos de dominio principales estan definidos con `managed = False`.
- La estructura principal de negocio debe existir previamente en SQL Server.
- Debes ejecutar el script SQL del proyecto para crear la base `SIG` y sus tablas.
- Luego puedes ejecutar migraciones Django para tablas internas del framework como:
  - `django_session`
  - `django_admin_log`
  - `django_content_type`
  - `auth_permission`

## Variables de entorno

Archivo: `backend/.env`

Variables minimas:

```env
DJANGO_SECRET_KEY=change_me
DJANGO_DEBUG=true
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

DB_NAME=SIG_2_VERSION
DB_USER=
DB_PASSWORD=
DB_HOST= 
DB_PORT=
DB_DRIVER=
DB_TRUST_CERT=

DOC_PATH_DRIVE=
GRAPH_DRIVE_ID=
GRAPH_DRIVE_USER=
GRAPH_CICLO_AUTH_FOLDER=
GRAPH_CICLO_AUTH_FOLDER_URL=

MS_TENANT_ID=
MS_CLIENT_ID=
MS_CLIENT_SECRET=
```

Notas:

- `GRAPH_DRIVE_ID` es obligatorio para el flujo documental con Graph.
- El sistema intenta usar primero una credencial activa en `api_credencial`.
- Si no existe esa credencial, usa las variables `MS_TENANT_ID`, `MS_CLIENT_ID` y `MS_CLIENT_SECRET`.
- `GRAPH_DRIVE_USER` puede quedar vacio si el flujo usa `GRAPH_DRIVE_ID`.

## Levantamiento del proyecto

### 1. Crear y activar entorno virtual

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. Instalar dependencias Python

```powershell
pip install -r backend\requirements\dev.txt
```

Si no necesitas herramientas de desarrollo:

```powershell
pip install -r backend\requirements\base.txt
```

### 3. Instalar dependencias del frontend

```powershell
cd frontend
npm install
cd ..
```

### 4. Configurar `backend/.env`

- Copia `backend/.env.example` como base.
- Ajusta la conexion a SQL Server.
- Configura Microsoft Graph.

### 5. Preparar la base de datos

1. Crea la base `SIG` en SQL Server.
2. Ejecuta el script SQL funcional del proyecto para crear tablas, indices y relaciones.
3. Ejecuta migraciones de Django para tablas internas:

```powershell
.\.venv\Scripts\python.exe backend\manage.py migrate
```

### 6. Compilar assets

```powershell
cd frontend
npm run build
cd ..
```

Para desarrollo continuo de assets:

```powershell
cd frontend
npm run dev
```

### 7. Verificar configuracion

```powershell
.\.venv\Scripts\python.exe backend\manage.py check
```

### 8. Levantar el servidor

```powershell
.\.venv\Scripts\python.exe backend\manage.py runserver
```

Aplicacion local:

```text
http://127.0.0.1:8000/
```

## Flujo documental

- La estructura documental se genera por jerarquia:
  - criterio
  - subcriterio
  - indicador
  - elemento
  - ciclo
- El documento de autorizacion del ciclo es obligatorio para habilitar el ciclo.
- La carga documental estructurada se habilita cuando el ciclo esta aprobado y ya tiene documento de autorizacion.
- Los documentos se versionan en `version_documento`.
- Los accesos quedan registrados en `documento_acceso_log`.
- Las carpetas y archivos se gestionan por Microsoft Graph, no por almacenamiento local del servidor.

## Comandos utiles

Validar proyecto:

```powershell
.\.venv\Scripts\python.exe backend\manage.py check
```

Levantar servidor:

```powershell
.\.venv\Scripts\python.exe backend\manage.py runserver
```

Compilar frontend:

```powershell
cd frontend
npm run build
```

Modo watch frontend:

```powershell
cd frontend
npm run dev
```

## Observaciones operativas

- Si SQL Server no responde, los formularios de alta no podran persistir registros.
- Si Microsoft Graph no esta configurado correctamente, el sistema bloqueara la creacion de carpetas y cargas documentales.
- Los documentos protegidos no deben exponerse mediante URL publica.
- La capa de negocio debe mantenerse en `services` y la lectura en `selectors`.
