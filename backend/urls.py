"""
URL configuration for backend project.

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
from django.contrib import admin
from django.urls import path, include
from apps.core.views import (
    home,
    create_user_view,
    user_role_view,
    criterio_view,
    subcriterio_view,
    tipo_indicador_view,
    indicador_view,
    update_credential_view,
)
from apps.seguridad.views import (
    login_view,
    logout_view,
    register_view,
    request_reset_view,
    confirm_reset_view,
)

urlpatterns = [
    path("", home, name="home"),
    path("admin/crear-usuario/", create_user_view, name="admin_create_user"),
    path("admin/asignacion-usuario-rol/", user_role_view, name="admin_user_role"),
    path(
        "admin/usuarios/<int:user_id>/credencial",
        update_credential_view,
        name="admin_user_credential",
    ),
    path("admin/criterios/", criterio_view, name="admin_criterio"),
    path("admin/subcriterios/", subcriterio_view, name="admin_subcriterio"),
    path("admin/tipos-indicador/", tipo_indicador_view, name="admin_tipo_indicador"),
    path("admin/indicadores/", indicador_view, name="admin_indicador"),
    path("admin/", admin.site.urls),
    path("", include("apps.seguridad.urls")),
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),
    path("register/", register_view, name="register"),
    path("reset-password/", request_reset_view, name="request_reset"),
    path("reset-password/confirm/", confirm_reset_view, name="confirm_reset"),
]
