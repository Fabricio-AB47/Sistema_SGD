from __future__ import annotations

from urllib.parse import urlencode, urlsplit

from django.conf import settings
from django.utils.http import url_has_allowed_host_and_scheme


def _normalize_local_path(value: str | None) -> str | None:
    path = urlsplit(str(value or "")).path
    if not path or not path.startswith("/"):
        return None
    return path.rstrip("/") or "/"


def _is_disallowed_redirect(target: str, disallowed_paths: tuple[str, ...]) -> bool:
    target_path = _normalize_local_path(target)
    if not target_path:
        return False

    for path in disallowed_paths:
        blocked_path = _normalize_local_path(path)
        if not blocked_path:
            continue
        if target_path == blocked_path:
            return True
        if blocked_path != "/" and target_path.startswith(f"{blocked_path}/"):
            return True
    return False


def get_auth_flow_redirect_blocklist() -> tuple[str, ...]:
    return tuple(
        path
        for path in (
            getattr(settings, "LOGIN_URL", None),
            getattr(settings, "OTP_URL", None),
            "/logout/",
            "/otp/reenviar/",
            "/recuperar-password/",
            "/cambiar-password/",
        )
        if path
    )


def get_safe_redirect_target(
    request,
    *,
    fallback: str,
    candidate: str | None = None,
    param_name: str = "next",
    disallowed_paths: tuple[str, ...] = (),
) -> str:
    target = (candidate or "").strip()
    if not target:
        target = (
            request.POST.get(param_name)
            or request.GET.get(param_name)
            or ""
        ).strip()

    if target and url_has_allowed_host_and_scheme(
        url=target,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        if _is_disallowed_redirect(target, disallowed_paths):
            return fallback
        return target
    return fallback


def build_login_redirect_url(request, login_url: str | None = None) -> str:
    base_url = login_url or settings.LOGIN_URL or "/login/"
    next_target = request.get_full_path() or "/"
    if _is_disallowed_redirect(next_target, get_auth_flow_redirect_blocklist()):
        next_target = getattr(settings, "LOGIN_REDIRECT_URL", "/dashboard/") or "/dashboard/"
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}{urlencode({'next': next_target})}"
