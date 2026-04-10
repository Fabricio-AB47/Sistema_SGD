from apps.usuarios.services.session_service import (  # noqa: F401
    close_session,
    create_session,
    ensure_request_session_active,
    expire_sessions,
    get_request_user_session,
    get_token_hash,
    is_session_expired,
    is_session_idle,
    revoke_other_sessions_for_user,
    revoke_session,
    touch_session,
    validate_session,
)


def invalidate_session(token_plain: str) -> int:
    result = close_session(token_plain=token_plain, reason="manual")
    return 1 if result.get("updated") else 0
