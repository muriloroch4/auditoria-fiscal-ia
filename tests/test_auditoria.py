import io
import os
import unittest
import unittest.mock
import zipfile
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from textwrap import dedent
from xml.sax.saxutils import escape

from src.auditoria.audit import run_quarterly_audit
from src.auditoria.models import RiskLevel
from src.auditoria.parser import read_trial_balance_csv, read_trial_balance_csv_text, read_trial_balance_upload
from src.auditoria.report_ai import build_report_prompt, generate_markdown_report
from src.auditoria.serializers import audit_result_to_dict
from src.auditoria.ai_client import is_api_key_configured
from src.auditoria.risk import classify_total_risk
from src.auditoria.pdf_export import markdown_to_pdf
from src.auditoria.utils import format_brl, format_percent, sanitize_for_latin1


class AuditPrototypeTest(unittest.TestCase):
    def test_sample_trial_balance_generates_report(self):
        sample = Path("samples/balancete_simples_servicos.csv")
        balance = read_trial_balance_csv(sample, cliente="Cliente Exemplo", periodo="2026-T1")

        result = run_quarterly_audit(balance)
        report = generate_markdown_report(result, use_ai=False)
        prompt_payload = build_report_prompt(result)
        api_payload = audit_result_to_dict(result, report_markdown=report)

        self.assertEqual(result.nivel_geral, RiskLevel.ALTO)
        self.assertEqual(result.pontuacao_total, 50)
        self.assertEqual({finding.codigo for finding in result.achados}, {"SN-004A", "SN-005"})
        self.assertIn("Distribuição de lucros acima do lucro apurado", report)
        self.assertEqual(prompt_payload["nivel_geral"], "alto")
        self.assertIn("explicacao_pontuacao", prompt_payload)
        self.assertEqual(api_payload["nivel_geral"], "alto")
        self.assertIn("explicacao_pontuacao", api_payload)
        self.assertIn("relatorio_markdown", api_payload)

    def test_csv_text_parser_supports_upload_flow(self):
        content = Path("samples/balancete_simples_servicos.csv").read_text(encoding="utf-8")

        balance = read_trial_balance_csv_text(content, cliente="Upload", periodo="2026-T1")

        self.assertEqual(balance.cliente, "Upload")
        self.assertEqual(balance.periodo, "2026-T1")
        self.assertEqual(len(balance.contas), 15)

    def test_zero_revenue_with_active_movement_generates_high_risk_finding(self):
        content = dedent(
            """\
            codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual
            1.1.1;Banco Conta Movimento;bancos;0;50000;48000;2000
            2.1.1;Simples Nacional a Recolher;tributos;0;0;0;0
            3.1.1;Receita de Servicos;receita;0;0;0;0
            4.1.1;Pro Labore;folha;0;8000;0;-8000
            4.2.1;Servicos de Terceiros;despesas;0;22000;0;-22000
            """
        )
        balance = read_trial_balance_csv_text(content, cliente="Sem Receita", periodo="2026-T1")

        result = run_quarterly_audit(balance)
        finding_by_code = {finding.codigo: finding for finding in result.achados}

        self.assertEqual(result.nivel_geral, RiskLevel.ALTO)
        self.assertIn("SN-008A", finding_by_code)
        self.assertEqual(finding_by_code["SN-008A"].pontuacao, 20)

    def test_tax_below_three_percent_of_revenue_generates_high_risk_finding(self):
        content = dedent(
            """\
            codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual
            1.1.1;Banco Conta Movimento;bancos;0;0;0;0
            2.1.1;Simples Nacional a Recolher;tributos;0;0;2000;2000
            3.1.1;Receita de Servicos;receita;0;0;100000;100000
            4.1.1;Pro Labore;folha;0;10000;0;-10000
            4.2.1;Despesas Administrativas;despesas;0;20000;0;-20000
            """
        )
        balance = read_trial_balance_csv_text(content, cliente="Imposto Baixo", periodo="2026-T1")

        result = run_quarterly_audit(balance)
        finding_by_code = {finding.codigo: finding for finding in result.achados}

        self.assertEqual(result.nivel_geral, RiskLevel.ALTO)
        self.assertIn("SN-002B", finding_by_code)
        self.assertEqual(finding_by_code["SN-002B"].pontuacao, 20)

    def test_profit_distribution_uses_reported_result_when_available(self):
        content = dedent(
            """\
            codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual
            1.1.1;Banco Conta Movimento;bancos;0;0;0;0
            2.1.1;Simples Nacional a Recolher;tributos;0;0;10000;10000
            3.1.1;Receita de Servicos;receita;0;0;100000;100000
            4.1.1;Pro Labore;folha;0;10000;0;-10000
            4.2.1;Despesas Administrativas;despesas;0;20000;0;-20000
            5.1.1;Distribuicao de Lucros;lucros;0;50000;0;-50000
            6.1.1;Resultado do Periodo;resultado;0;0;40000;40000
            """
        )
        balance = read_trial_balance_csv_text(content, cliente="Lucro Informado", periodo="2026-T1")

        result = run_quarterly_audit(balance)
        finding_by_code = {finding.codigo: finding for finding in result.achados}

        self.assertIn("SN-004A", finding_by_code)
        self.assertEqual(result.resumo_metricas["lucro_apurado_base"], "R$ 40.000,00")
        self.assertEqual(result.resumo_metricas["origem_lucro_apurado"], "resultado informado no balancete")

    def test_xlsx_upload_flow_generates_audit(self):
        rows = [
            ["codigo", "conta", "grupo", "saldo_anterior", "debito", "credito", "saldo_atual"],
            ["1.1.1", "Banco Conta Movimento", "bancos", "0", "0", "0", "0"],
            ["2.1.1", "Simples Nacional a Recolher", "tributos", "0", "0", "2000", "2000"],
            ["3.1.1", "Receita de Servicos", "receita", "0", "0", "100000", "100000"],
            ["4.1.1", "Pro Labore", "folha", "0", "10000", "0", "-10000"],
            ["4.2.1", "Despesas Administrativas", "despesas", "0", "20000", "0", "-20000"],
        ]
        content = _build_xlsx(rows)

        balance = read_trial_balance_upload(
            "balancete.xlsx",
            content,
            cliente="Excel Upload",
            periodo="2026-T1",
        )
        result = run_quarterly_audit(balance)

        self.assertEqual(balance.cliente, "Excel Upload")
        self.assertIn("SN-002B", {finding.codigo for finding in result.achados})

    def test_ai_report_uses_mock_when_api_call_fails(self):
        balance = read_trial_balance_csv_text(
            dedent(
                """\
                codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual
                1.1.1;Banco;bancos;0;0;0;0
                3.1.1;Receita de Servicos;receita;0;0;100000;100000
                """
            ),
            cliente="Falha IA",
            periodo="2026-T1",
        )
        result = run_quarterly_audit(balance)

        with unittest.mock.patch("src.auditoria.ai_client.call_openrouter", side_effect=ConnectionError("Erro")):
            report = generate_markdown_report(result, use_ai=True)

            self.assertIn("Relatório Trimestral de Risco Fiscal", report)
            self.assertIn("Falha IA", report)

    def test_ai_report_calls_openrouter_when_configured(self):
        balance = read_trial_balance_csv_text(
            dedent(
                """\
                codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual
                1.1.1;Banco;bancos;0;0;0;0
                3.1.1;Receita de Servicos;receita;0;0;100000;100000
                """
            ),
            cliente="Com IA",
            periodo="2026-T1",
        )
        result = run_quarterly_audit(balance)
        ai_response = "# Relatorio gerado pela IA\n\nAnalise contextual dos achados."

        with unittest.mock.patch("src.auditoria.ai_client.call_openrouter", return_value=ai_response) as mock_call:
            report = generate_markdown_report(result, use_ai=True)

            mock_call.assert_called_once()
            messages = mock_call.call_args.args[0]
            self.assertEqual(messages[0]["role"], "system")
            self.assertEqual(messages[1]["role"], "user")
            self.assertIn("Com IA", messages[1]["content"])
            self.assertIn("100.000", messages[1]["content"])
            self.assertEqual(report, ai_response)

    def test_ai_report_disabled_when_use_ai_false(self):
        balance = read_trial_balance_csv_text(
            dedent(
                """\
                codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual
                1.1.1;Banco;bancos;0;0;0;0
                3.1.1;Receita de Servicos;receita;0;0;100000;100000
                """
            ),
            cliente="IA Desabilitada",
            periodo="2026-T1",
        )
        result = run_quarterly_audit(balance)

        with unittest.mock.patch("src.auditoria.ai_client.call_openrouter") as mock_call:
            report = generate_markdown_report(result, use_ai=False)

            mock_call.assert_not_called()
            self.assertIn("Relatório Trimestral de Risco Fiscal", report)
            self.assertIn("IA Desabilitada", report)

    def test_is_api_key_configured_logic(self):
        with unittest.mock.patch("src.auditoria.ai_client._load_env_file"):
            with unittest.mock.patch.dict(os.environ, {}, clear=True):
                self.assertFalse(is_api_key_configured())
                self.assertFalse(is_api_key_configured(""))
                self.assertFalse(is_api_key_configured("   "))
                self.assertTrue(is_api_key_configured("sk-test-key"))

    def test_is_api_key_configured_with_env(self):
        with unittest.mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-test-env"}):
            self.assertTrue(is_api_key_configured())


class RiskClassificationTest(unittest.TestCase):
    def _make_finding(self, codigo="X", nivel=RiskLevel.BAIXO, pontuacao=5):
        from src.auditoria.models import RuleFinding
        return RuleFinding(
            codigo=codigo,
            titulo="Test",
            nivel=nivel,
            pontuacao=pontuacao,
            descricao="Test",
        )

    def test_no_findings_means_low_risk(self):
        level, score = classify_total_risk([])
        self.assertEqual(level, RiskLevel.BAIXO)
        self.assertEqual(score, 0)

    def test_single_low_finding_stays_low(self):
        findings = [self._make_finding(pontuacao=5)]
        level, score = classify_total_risk(findings)
        self.assertEqual(level, RiskLevel.BAIXO)
        self.assertEqual(score, 5)

    def test_score_above_30_means_medium(self):
        findings = [self._make_finding(pontuacao=15), self._make_finding(pontuacao=18)]
        level, score = classify_total_risk(findings)
        self.assertEqual(level, RiskLevel.MEDIO)
        self.assertEqual(score, 33)

    def test_any_high_finding_means_high(self):
        findings = [self._make_finding(nivel=RiskLevel.ALTO, pontuacao=20)]
        level, score = classify_total_risk(findings)
        self.assertEqual(level, RiskLevel.ALTO)
        self.assertEqual(score, 20)

    def test_score_above_70_means_high(self):
        findings = [self._make_finding(pontuacao=25) for _ in range(3)]
        level, score = classify_total_risk(findings)
        self.assertEqual(level, RiskLevel.ALTO)
        self.assertEqual(score, 75)

    def test_any_medium_finding_means_medium(self):
        findings = [self._make_finding(nivel=RiskLevel.MEDIO, pontuacao=10)]
        level, score = classify_total_risk(findings)
        self.assertEqual(level, RiskLevel.MEDIO)


class UtilsTest(unittest.TestCase):
    def test_format_brl(self):
        self.assertEqual(format_brl(Decimal("1000.50")), "R$ 1.000,50")
        self.assertEqual(format_brl(Decimal("0")), "R$ 0,00")
        self.assertEqual(format_brl(Decimal("4800000")), "R$ 4.800.000,00")

    def test_format_percent(self):
        self.assertEqual(format_percent(Decimal("0.055")), "5,50%")
        self.assertEqual(format_percent(Decimal("1")), "100,00%")

    def test_sanitize_for_latin1_removes_unicode(self):
        self.assertEqual(sanitize_for_latin1("Teste com — travessão"), "Teste com - travessao")
        self.assertIn("caixa", sanitize_for_latin1("caixa"))
        self.assertEqual(sanitize_for_latin1("joão"), "joao")


class PDFExportTest(unittest.TestCase):
    def test_generate_pdf_from_markdown(self):
        markdown = "# Relatório Teste\n\n**Cliente:** Teste\n\n- Item 1\n- Item 2"
        buffer = io.BytesIO()
        markdown_to_pdf(markdown, buffer)
        buffer.seek(0)
        header = buffer.read(5)
        self.assertEqual(header, b"%PDF-")

    def test_generate_pdf_with_tables(self):
        markdown = (
            "# Relatório\n\n"
            "| Campo | Valor |\n"
            "| --- | --- |\n"
            "| Risco | ALTO |\n"
            "| Pontos | 50 |\n"
        )
        buffer = io.BytesIO()
        markdown_to_pdf(markdown, buffer)
        buffer.seek(0)
        self.assertTrue(buffer.read().startswith(b"%PDF-"))

    def test_generate_pdf_with_blockquote(self):
        markdown = "# Relatório\n\n> Recomendação técnica para o cliente."
        buffer = io.BytesIO()
        markdown_to_pdf(markdown, buffer)
        buffer.seek(0)
        self.assertTrue(buffer.read().startswith(b"%PDF-"))


class ParserEdgeCaseTest(unittest.TestCase):
    def test_csv_with_comma_delimiter(self):
        content = dedent(
            """\
            codigo,conta,grupo,saldo_anterior,debito,credito,saldo_atual
            1.1.1,Banco,bancos,0,1000,500,-500
            3.1.1,Receita,receita,0,0,50000,50000
            """
        )
        balance = read_trial_balance_csv_text(content, cliente="Comma CSV", periodo="2026-T1")
        self.assertEqual(balance.cliente, "Comma CSV")
        self.assertEqual(len(balance.contas), 2)

    def test_csv_with_tab_delimiter(self):
        content = "codigo\tconta\tgrupo\tsaldo_anterior\tdebito\tcredito\tsaldo_atual\n1.1.1\tBanco\tbancos\t0\t1000\t500\t-500\n"
        balance = read_trial_balance_csv_text(content, cliente="Tab CSV", periodo="2026-T1")
        self.assertEqual(len(balance.contas), 1)

    def test_empty_csv_raises_error(self):
        with self.assertRaises(ValueError):
            read_trial_balance_csv_text("", cliente="X", periodo="Y")

    def test_csv_missing_columns_raises_error(self):
        content = "codigo;conta;grupo\n1.1.1;Banco;bancos\n"
        with self.assertRaises(ValueError):
            read_trial_balance_csv_text(content, cliente="X", periodo="Y")

    def test_zero_revenue_no_active_movement_no_finding(self):
        content = dedent(
            """\
            codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual
            1.1.1;Banco;bancos;0;100;80;-20
            3.1.1;Receita;receita;0;0;0;0
            """
        )
        balance = read_trial_balance_csv_text(content, cliente="Low Movement", periodo="2026-T1")
        result = run_quarterly_audit(balance)
        finding_codes = {f.codigo for f in result.achados}
        self.assertNotIn("SN-008A", finding_codes)


if __name__ == "__main__":
    unittest.main()


def _build_xlsx(rows: list[list[str]]) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _content_types_xml())
        archive.writestr("_rels/.rels", _root_rels_xml())
        archive.writestr("xl/workbook.xml", _workbook_xml())
        archive.writestr("xl/_rels/workbook.xml.rels", _workbook_rels_xml())
        archive.writestr("xl/worksheets/sheet1.xml", _sheet_xml(rows))
    return output.getvalue()


def _sheet_xml(rows: list[list[str]]) -> str:
    row_xml = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for col_index, value in enumerate(row):
            ref = f"{_column_name(col_index)}{row_index}"
            cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>')
        row_xml.append(f'<row r="{row_index}">{"".join(cells)}</row>')

    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(row_xml)}</sheetData>'
        '</worksheet>'
    )


def _column_name(index: int) -> str:
    name = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _content_types_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '</Types>'
    )


def _root_rels_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '</Relationships>'
    )


def _workbook_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Balancete" sheetId="1" r:id="rId1"/></sheets>'
        '</workbook>'
    )


def _workbook_rels_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '</Relationships>'
    )
