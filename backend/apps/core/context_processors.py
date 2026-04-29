from apps.core.services.navigation_service import get_user_profile_context
from apps.core.services.notification_service import obtener_resumen_notificaciones


def sig_navigation(request):
    role_names = tuple(request.session.get("sig_roles", []) or [])
    permission_codes = tuple(request.session.get("sig_permissions", []) or [])
    operational_roles = tuple(request.session.get("sig_operational_roles", []) or [])
    assignment_options = tuple(request.session.get("sig_assignment_options", []) or [])
    profile = get_user_profile_context(
        user_id=request.session.get("sig_user_id"),
        role_names=role_names,
        permission_codes=permission_codes,
        operational_roles=operational_roles,
        active_assignment_id=request.session.get("sig_active_assignment_id"),
        assignment_options=assignment_options,
    )
    notification_summary = obtener_resumen_notificaciones(
        user_id=request.session.get("sig_user_id"),
    )
    return {
        "sig_profile": profile,
        "sig_navigation_groups": profile["navigation_groups"],
        "sig_notifications": notification_summary,
    }
