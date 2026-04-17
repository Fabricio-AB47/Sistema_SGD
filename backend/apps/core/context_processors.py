from apps.core.services.navigation_service import get_user_profile_context


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
    return {
        "sig_profile": profile,
        "sig_navigation_groups": profile["navigation_groups"],
    }
