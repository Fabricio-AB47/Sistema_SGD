import json
import ipaddress
import socket
from urllib.parse import urlparse
from urllib import error, request as urllib_request

from django.conf import settings

from . import api_log_service, token_service


class BaseApiClient:
    def __init__(self, credencial, usuario=None, ip=None, timeout=30):
        self.credencial = credencial
        self.api_servicio = credencial.api_servicio
        self.usuario = usuario
        self.ip = ip
        self.timeout = timeout

    def _build_url(self, endpoint: str) -> str:
        base_url = (self.api_servicio.url_base or "").rstrip("/")
        endpoint = endpoint.lstrip("/")
        if not base_url:
            return endpoint
        return f"{base_url}/{endpoint}" if endpoint else base_url

    def _host_is_allowed(self, hostname: str) -> bool:
        allowed_hosts = tuple(getattr(settings, "SIG_ALLOWED_OUTBOUND_HOSTS", ()) or ())
        if not allowed_hosts:
            return False

        hostname = hostname.lower().strip(".")
        for allowed in allowed_hosts:
            allowed = allowed.lower().strip()
            if not allowed:
                continue
            if allowed.startswith("*.") and hostname.endswith(allowed[1:]):
                return True
            if hostname == allowed.strip("."):
                return True
        return False

    def _host_resolves_private(self, hostname: str) -> bool:
        try:
            addresses = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
        except socket.gaierror:
            return False

        for address in addresses:
            ip_value = address[4][0]
            try:
                ip = ipaddress.ip_address(ip_value)
            except ValueError:
                continue
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return True
        return False

    def _validate_outbound_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("URL externa invalida para consumo API.")

        if getattr(settings, "SIG_REQUIRE_HTTPS_OUTBOUND", True) and parsed.scheme != "https":
            raise ValueError("Las integraciones externas deben usar HTTPS.")

        hostname = parsed.hostname
        if self._host_is_allowed(hostname):
            return

        if getattr(settings, "SIG_BLOCK_PRIVATE_OUTBOUND", True) and self._host_resolves_private(hostname):
            raise ValueError("Destino bloqueado por politica SSRF.")

    def _mock_response(self, endpoint, method, data):
        payload = {
            "mock": True,
            "servicio": self.api_servicio.nombre_servicio,
            "endpoint": endpoint,
            "method": method.upper(),
            "data": data or {},
        }
        api_log_service.registrar_consumo_api(
            api_servicio=self.api_servicio,
            endpoint=endpoint,
            metodo_http=method,
            usuario=self.usuario,
            ip=self.ip,
            resultado="200",
            detalle=payload,
        )
        return {"status_code": 200, "data": payload, "headers": {}}

    def request(self, endpoint, method="GET", data=None, token=None):
        if not self.api_servicio.url_base:
            return self._mock_response(endpoint, method, data)

        token_value = token
        if token and hasattr(token, "access_token_encriptado"):
            token_value = token_service.get_access_token_plain(token)
        if not token_value:
            token_value = token_service.get_access_token_plain(
                token_service.get_valid_token(self.credencial)
            )

        url = self._build_url(endpoint)
        try:
            self._validate_outbound_url(url)
        except ValueError as exc:
            api_log_service.registrar_consumo_api(
                api_servicio=self.api_servicio,
                endpoint=endpoint,
                metodo_http=method,
                usuario=self.usuario,
                ip=self.ip,
                resultado="BLOCKED",
                detalle=str(exc),
            )
            return {"status_code": 400, "data": {"detail": str(exc)}, "headers": {}}

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token_value}",
        }
        body = None if data is None else json.dumps(data).encode("utf-8")
        request_obj = urllib_request.Request(
            url=url,
            data=body,
            headers=headers,
            method=method.upper(),
        )

        try:
            with urllib_request.urlopen(request_obj, timeout=self.timeout) as response:
                raw_body = response.read().decode("utf-8")
                if not raw_body:
                    payload = {}
                else:
                    try:
                        payload = json.loads(raw_body)
                    except json.JSONDecodeError:
                        payload = {"raw": raw_body}
                result = {
                    "status_code": response.status,
                    "data": payload,
                    "headers": dict(response.headers.items()),
                }
                api_log_service.registrar_consumo_api(
                    api_servicio=self.api_servicio,
                    endpoint=endpoint,
                    metodo_http=method,
                    usuario=self.usuario,
                    ip=self.ip,
                    resultado=str(response.status),
                    detalle=payload,
                )
                return result
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            api_log_service.registrar_consumo_api(
                api_servicio=self.api_servicio,
                endpoint=endpoint,
                metodo_http=method,
                usuario=self.usuario,
                ip=self.ip,
                resultado=str(exc.code),
                detalle=detail,
            )
            return {"status_code": exc.code, "data": {"detail": detail}, "headers": {}}
        except error.URLError as exc:
            api_log_service.registrar_consumo_api(
                api_servicio=self.api_servicio,
                endpoint=endpoint,
                metodo_http=method,
                usuario=self.usuario,
                ip=self.ip,
                resultado="ERROR",
                detalle=str(exc.reason),
            )
            return {"status_code": 503, "data": {"detail": str(exc.reason)}, "headers": {}}
