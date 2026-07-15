from __future__ import annotations

import unittest
import unittest.mock
from pathlib import Path
from textwrap import dedent

from src.auditoria.audit import run_quarterly_audit
from src.auditoria.parser import read_trial_balance_csv, read_trial_balance_csv_text
from src.auditoria.report_ai import generate_markdown_report


class LocalReportRendererTest(unittest.TestCase):
    def test_local_report_keeps_consultive_structure_snapshot(self):
        balance = read_trial_balance_csv(
            Path("samples/exemplo_balancete_todas_regras.csv"),
            cliente="Golden Todas Regras",
            periodo="2026-T1",
            cnpj="12.345.678/0001-90",
        )
        result = run_quarterly_audit(balance)

        report = generate_markdown_report(result, use_ai=False, cnpj="12.345.678/0001-90")
        sections = [line for line in report.splitlines() if line.startswith("## ")]

        self.assertEqual(
            sections,
            [
                "## 1. Resumo executivo",
                "## 2. Leitura para o cliente",
                "## 3. Plano de ação consultivo",
                "## 4. Análise técnica para a contabilidade",
                "## 5. Conclusão técnica e próximos passos",
            ],
        )
        self.assertTrue(report.startswith("Parecer técnico contábil consultivo trimestral"))
        self.assertIn("Cliente:  Golden Todas Regras", report)
        self.assertIn("CNPJ:     12.345.678/0001-90", report)
        self.assertIn("pontuação total de", report.lower())
        self.assertIn("/100", report)
        self.assertIn("SN-025", report)
        self.assertIn("Servicos prestados por terceiros", report)
        self.assertNotIn("## 4. Assinatura", report)
        self.assertNotIn("carimbo", report.lower())

    def test_local_report_without_findings_uses_preventive_language(self):
        content = dedent(
            """\
            codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual
            1.1.1;Banco;bancos;0;0;0;0
            """
        )
        balance = read_trial_balance_csv_text(content, cliente="Sem Achados", periodo="2026-T1")
        result = run_quarterly_audit(balance)

        report = generate_markdown_report(result, use_ai=False)

        self.assertIn("Nenhuma regra foi acionada", report)
        self.assertIn("Nenhuma ação corretiva prioritária", report)
        self.assertIn("manter a documentação suporte", report)

    def test_ai_generation_falls_back_to_local_report(self):
        content = dedent(
            """\
            codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual
            1.1.1;Banco;bancos;0;0;0;0
            """
        )
        balance = read_trial_balance_csv_text(content, cliente="Fallback IA", periodo="2026-T1")
        result = run_quarterly_audit(balance)

        with (
            unittest.mock.patch("src.auditoria.ai_client.call_openrouter", side_effect=RuntimeError("offline")),
            unittest.mock.patch("src.auditoria.report_ai._logger.warning"),
        ):
            report = generate_markdown_report(result, use_ai=True)

        self.assertIn("Parecer técnico contábil consultivo trimestral", report)
        self.assertIn("Cliente:  Fallback IA", report)


if __name__ == "__main__":
    unittest.main()
