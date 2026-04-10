from pathlib import Path
import os

from django.core.exceptions import ImproperlyConfigured

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent
# Directorio del frontend (templates y estáticos viven allí)
FRONTEND_DIR = BASE_DIR.parent / "frontend"


def _env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _env_csv(name: str, default: str = "") -> tuple[str, ...]:
    value = os.getenv(name, default)
    return tuple(item.strip() for item in value.split(",") if item.strip())


# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
    "change-me-in-env",
)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = _env_bool("DJANGO_DEBUG", False)

ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "").split(",") if not DEBUG else ["*"]

# Rutas de autenticación
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/dashboard/"
LOGOUT_REDIRECT_URL = "/login/"

# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Apps del SIG
    "apps.core",
    "apps.usuarios",
    "apps.seguridad",
    "apps.permisos",
    "apps.acreditacion",
    "apps.documentos",
    "apps.evidencias",
    "apps.evaluacion",
    "apps.informes",
    "apps.mejora",
    "apps.integraciones",
    "apps.auditoria",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.seguridad.middleware.TokenSessionMiddleware",
]

ROOT_URLCONF = "SIG.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [
            FRONTEND_DIR / "templates",
        ],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "SIG.wsgi.application"


# Database
# Ajusta las variables de entorno para apuntar a tu instancia SQL Server.
DATABASES = {
    "default": {
        "ENGINE": "mssql",
        "NAME": os.getenv("DB_NAME", "SIG"),
        "USER": os.getenv("DB_USER", "sa"),
        "PASSWORD": os.getenv("DB_PASSWORD", "change_me"),
        "HOST": os.getenv("DB_HOST", "localhost"),
        "PORT": os.getenv("DB_PORT", "1433"),
        "OPTIONS": {
            "driver": os.getenv("DB_DRIVER", "ODBC Driver 18 for SQL Server"),
            "extra_params": "Encrypt=yes;TrustServerCertificate=yes;Connection Timeout=30;",
        },
    }
}


def _validate_runtime_security_settings():
    if DEBUG:
        return

    if not SECRET_KEY or SECRET_KEY == "change-me-in-env":
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY debe configurarse con un valor seguro fuera del codigo."
        )

    allowed_hosts = [host.strip() for host in ALLOWED_HOSTS if host.strip()]
    if not allowed_hosts:
        raise ImproperlyConfigured(
            "DJANGO_ALLOWED_HOSTS debe definir al menos un host en entornos no DEBUG."
        )

    db_password = DATABASES["default"].get("PASSWORD")
    if not db_password or db_password == "change_me":
        raise ImproperlyConfigured(
            "DB_PASSWORD debe configurarse con un valor valido fuera del codigo."
        )


_validate_runtime_security_settings()


# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Algoritmos de hash de contraseñas (se prioriza Argon2 por seguridad)
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",  # Hash fuerte y recomendado.
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]


# Internationalization
LANGUAGE_CODE = "es-ec"

TIME_ZONE = "America/Guayaquil"

USE_I18N = True
USE_TZ = True


# Static files (CSS, JavaScript, Images)
STATIC_URL = "/static/"
# Se sirven desde frontend/static (compilados por Gulp)
STATICFILES_DIRS = [FRONTEND_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Baseline de endurecimiento para reducir riesgo de misconfiguracion y fuga de sesion.
SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", not DEBUG)
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = os.getenv("CSRF_COOKIE_SAMESITE", "Lax")
CSRF_COOKIE_SECURE = _env_bool("CSRF_COOKIE_SECURE", not DEBUG)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SECURE_SSL_REDIRECT = _env_bool("SECURE_SSL_REDIRECT", False)
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "0") or "0")
SECURE_HSTS_INCLUDE_SUBDOMAINS = _env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", False)
SECURE_HSTS_PRELOAD = _env_bool("SECURE_HSTS_PRELOAD", False)

# Limites de carga para reducir abuso y proteger el servidor.
SIG_MAX_UPLOAD_FILE_MB = int(os.getenv("SIG_MAX_UPLOAD_FILE_MB", "25") or "25")
SIG_MAX_UPLOAD_FILE_BYTES = SIG_MAX_UPLOAD_FILE_MB * 1024 * 1024
SIG_ALLOWED_UPLOAD_EXTENSIONS = _env_csv(
    "SIG_ALLOWED_UPLOAD_EXTENSIONS",
    ".pdf,.doc,.docx,.xls,.xlsx,.csv",
)
SIG_ALLOWED_UPLOAD_CONTENT_TYPES = _env_csv(
    "SIG_ALLOWED_UPLOAD_CONTENT_TYPES",
    (
        "application/pdf,"
        "application/msword,"
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document,"
        "application/vnd.ms-excel,"
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,"
        "text/csv"
    ),
)
DATA_UPLOAD_MAX_MEMORY_SIZE = SIG_MAX_UPLOAD_FILE_BYTES + (2 * 1024 * 1024)
FILE_UPLOAD_MAX_MEMORY_SIZE = min(SIG_MAX_UPLOAD_FILE_BYTES, 10 * 1024 * 1024)
DATA_UPLOAD_MAX_NUMBER_FILES = int(os.getenv("DATA_UPLOAD_MAX_NUMBER_FILES", "5") or "5")

# Configuracion documental / Graph / SharePoint
DOC_PATH_DRIVE = (
    os.getenv("DOC_PATH_DRIVE")
    or os.getenv("doc_path_drive")
    or "SISTEMA INFORMATICO DE GESTION"
).strip()
GRAPH_DRIVE_ID = os.getenv("GRAPH_DRIVE_ID", "").strip()
GRAPH_DRIVE_USER = os.getenv("GRAPH_DRIVE_USER", "").strip()
GRAPH_CICLO_AUTH_FOLDER = os.getenv("GRAPH_CICLO_AUTH_FOLDER", "DOCUMENTOS CICLOS AUTH").strip()
GRAPH_CICLO_AUTH_FOLDER_URL = os.getenv("GRAPH_CICLO_AUTH_FOLDER_URL", "").strip()
GRAPH_REQUEST_TIMEOUT_SECONDS = int(os.getenv("GRAPH_REQUEST_TIMEOUT_SECONDS", "10") or "10")
GRAPH_UPLOAD_TIMEOUT_SECONDS = int(os.getenv("GRAPH_UPLOAD_TIMEOUT_SECONDS", "30") or "30")

# Seguridad de acceso: exigir correo verificado antes de permitir login.
SIG_REQUIRE_EMAIL_VERIFICATION = _env_bool("SIG_REQUIRE_EMAIL_VERIFICATION", False)
SIG_REQUIRE_OTP_EVERY_LOGIN = _env_bool("SIG_REQUIRE_OTP_EVERY_LOGIN", True)
SIG_OTP_CODE_LENGTH = int(os.getenv("SIG_OTP_CODE_LENGTH", "6") or "6")
SIG_OTP_EXPIRATION_MINUTES = int(os.getenv("SIG_OTP_EXPIRATION_MINUTES", "10") or "10")
SIG_OTP_MAX_ATTEMPTS = int(os.getenv("SIG_OTP_MAX_ATTEMPTS", "5") or "5")
SIG_EXPOSE_DEBUG_OTP = _env_bool("SIG_EXPOSE_DEBUG_OTP", False)
SIG_USE_GRAPH_EMAIL = _env_bool("SIG_USE_GRAPH_EMAIL", True)

# Correo transaccional para OTP, verificacion y recuperacion.
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = os.getenv("EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "25") or "25")
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "").strip()
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = _env_bool("EMAIL_USE_TLS", False)
EMAIL_USE_SSL = _env_bool("EMAIL_USE_SSL", False)
EMAIL_TIMEOUT = int(os.getenv("EMAIL_TIMEOUT", "10") or "10")
DEFAULT_FROM_EMAIL = (
    os.getenv("DEFAULT_FROM_EMAIL", "").strip()
    or EMAIL_HOST_USER
    or "no-reply@sig.local"
)
SIG_SITE_NAME = os.getenv("SIG_SITE_NAME", "SIG").strip() or "SIG"
SIG_MAIL_SENDER = os.getenv("SIG_MAIL_SENDER", "").strip() or GRAPH_DRIVE_USER
OTP_URL = "/otp/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
