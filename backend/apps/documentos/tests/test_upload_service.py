from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.documentos.services.upload_service import _structured_evidence_file_name


class StructuredEvidenceFileNameTests(SimpleTestCase):
    def test_file_name_uses_indicator_element_and_year(self):
        ciclo = SimpleNamespace(anio=2026, fecha_inicio=None, nombre="Ciclo autoevaluacion institucional 2026")
        indicador = SimpleNamespace(codigo_indicador="CACES-01", nombre_indicador="Planificacion estrategica y operativa")
        elemento = SimpleNamespace(codigo_elemento="EF-07", orden_visual=3, pk=99)

        file_name = _structured_evidence_file_name(
            ciclo=ciclo,
            indicador=indicador,
            elemento=elemento,
            original_name="documento final.PDF",
        )

        self.assertEqual(file_name, "PEO_AI_EL07_2026.pdf")

    def test_file_name_uses_element_order_when_code_has_no_number(self):
        ciclo = SimpleNamespace(
            anio=None,
            fecha_inicio=SimpleNamespace(year=2027),
            nombre="Ciclo evaluacion 2027",
        )
        indicador = SimpleNamespace(
            codigo_indicador="CACES-24",
            nombre_indicador="Seguimiento, control y evaluacion del proceso docente",
        )
        elemento = SimpleNamespace(codigo_elemento="Elemento base", orden_visual=4, pk=12)

        file_name = _structured_evidence_file_name(
            ciclo=ciclo,
            indicador=indicador,
            elemento=elemento,
            original_name="anexo.docx",
        )

        self.assertEqual(file_name, "SCEPD_E_EL04_2027.docx")
