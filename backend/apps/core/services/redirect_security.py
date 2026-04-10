from __future__ import annotations

from urllib.parse import urlencode

from django.conf import settings
from django.utils.http import url_has_allowed_host_and_scheme


def get_safe_redirect_target(
    request,
    *,
    fallback: str,
    candidate: str | None = None,
    param_name: str = "next",
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
        return target
    return fallback


def build_login_redirect_url(request, login_url: str | None = None) -> str:
    base_url = login_url or settings.LOGIN_URL or "/login/"
    next_target = request.get_full_path() or "/"
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}{urlencode({'next': next_target})}"
