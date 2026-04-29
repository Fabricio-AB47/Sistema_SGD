"""
URL configuration for SIG project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.core.urls")),       # inicio y dashboard
    path("", include("apps.seguridad.urls")),  # login y auth
    path("", include("apps.usuarios.urls")),   # usuarios
    path("permisos/", include("apps.permisos.urls")),  # permisos
    path("acreditacion/", include("apps.acreditacion.urls")),  # acreditacion
    path("documentos/", include("apps.documentos.urls")),  # documentos
    path("evaluacion/", include("apps.evaluacion.urls")),  # evaluacion
    path("informes/", include("apps.informes.urls")),  # informes
    path("mejora/", include("apps.mejora.urls")),  # mejora
    path("", include("apps.integraciones.urls")),  # integraciones API
    path("", include("apps.auditoria.urls")),  # auditoria
]

if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
