from types import SimpleNamespace

from django.test import RequestFactory, SimpleTestCase, override_settings

from application.services import build_document_drive_path
from apps.core.services.redirect_security import (
    build_login_redirect_url,
    get_auth_flow_redirect_blocklist,
    get_safe_redirect_target,
)


@override_settings(LOGIN_URL="/login/", LOGIN_REDIRECT_URL="/dashboard/", OTP_URL="/otp/")
class RedirectSecurityTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_safe_redirect_rejects_auth_flow_targets(self):
        for target in ("/login/", "/otp/", "/otp/reenviar/"):
            request = self.factory.get("/login/", {"next": target})

            redirect_target = get_safe_redirect_target(
                request,
                fallback="/dashboard/",
                disallowed_paths=get_auth_flow_redirect_blocklist(),
            )

            self.assertEqual(redirect_target, "/dashboard/")

    def test_safe_redirect_accepts_protected_local_target(self):
        request = self.factory.get("/login/", {"next": "/acreditacion/matriz-registro/"})

        redirect_target = get_safe_redirect_target(
            request,
            fallback="/dashboard/",
            disallowed_paths=get_auth_flow_redirect_blocklist(),
        )

        self.assertEqual(redirect_target, "/acreditacion/matriz-registro/")

    def test_login_redirect_does_not_preserve_otp_as_next(self):
        request = self.factory.get("/otp/")

        redirect_url = build_login_redirect_url(request)

        self.assertEqual(redirect_url, "/login/?next=%2Fdashboard%2F")


@override_settings(DOC_PATH_DRIVE="GESTION")
class DocumentDrivePathTests(SimpleTestCase):
    def test_document_path_uses_cycle_folder_directly_inside_element(self):
        criterio = SimpleNamespace(codigo_criterio="C001", nombre_criterio="Crit 1 prb")
        subcriterio = SimpleNamespace(
            codigo_subcriterio="SC001",
            nombre_subcriterio="Subcriterio prb1",
            criterio=criterio,
        )
        indicador = SimpleNamespace(
            codigo_indicador="IN001",
            nombre_indicador="Primer indicador",
            subcriterio=subcriterio,
        )
        elemento = SimpleNamespace(
            codigo_elemento="EL001",
            nombre_elemento="Primer elemento",
        )
        ciclo = SimpleNamespace(nombre="Ciclo prb 1", anio=2026, pk=1)

        path = build_document_drive_path(indicador, elemento, ciclo).as_posix()

        self.assertEqual(
            path,
            "GESTION/CRITERIO/C001_CRIT_1_PRB/SC001_SUBCRITERIO_PRB1/"
            "IN001_PRIMER_INDICADOR/EL001_PRIMER_ELEMENTO/2026_CICLO_PRB_1",
        )
        self.assertNotIn("/CICLO/", path)
