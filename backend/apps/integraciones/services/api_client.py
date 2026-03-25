import json
from urllib import error, request as urllib_request

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
