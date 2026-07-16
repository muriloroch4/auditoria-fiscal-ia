from __future__ import annotations

import json
import tempfile
import unittest
import unittest.mock
from argparse import Namespace
from pathlib import Path

from src.auditoria import main as cli


def _args(**overrides) -> Namespace:
    values = {
        "balancete": None,
        "anual": None,
        "cliente": None,
        "periodo": None,
        "cnpj": "",
        "atividade": "servicos",
        "saida": None,
        "markdown": False,
        "no_ai": True,
        "openrouter_key": None,
        "ascii_output": False,
    }
    values.update(overrides)
    return Namespace(**values)


class CLIMainTest(unittest.TestCase):
    def test_parse_args_supports_quarterly_options(self):
        argv = [
            "auditoria",
            "balancete.csv",
            "--cliente",
            "Cliente",
            "--periodo",
            "2026-T1",
            "--cnpj",
            "12.345.678/0001-90",
            "--atividade",
            "comercio",
            "--saida",
            "saida.md",
            "--markdown",
            "--no-ai",
            "--openrouter-key",
            "key",
            "--ascii-output",
        ]

        with unittest.mock.patch.object(cli.sys, "argv", argv):
            args = cli._parse_args()

        self.assertEqual(args.balancete, "balancete.csv")
        self.assertEqual(args.cliente, "Cliente")
        self.assertEqual(args.periodo, "2026-T1")
        self.assertEqual(args.atividade, "comercio")
        self.assertTrue(args.markdown)
        self.assertTrue(args.no_ai)
        self.assertTrue(args.ascii_output)

    def test_main_requires_quarterly_balancete_cliente_and_periodo(self):
        with unittest.mock.patch.object(cli, "_parse_args", return_value=_args()):
            with self.assertRaisesRegex(SystemExit, "caminho do balancete"):
                cli.main()

        with unittest.mock.patch.object(cli, "_parse_args", return_value=_args(balancete="balancete.csv", cliente="Cliente")):
            with self.assertRaisesRegex(SystemExit, "cliente e --periodo"):
                cli.main()

    def test_main_generates_quarterly_json_payload(self):
        result = object()
        balance = object()
        with (
            unittest.mock.patch.object(cli, "_parse_args", return_value=_args(balancete="balancete.csv", cliente="Cliente", periodo="2026-T1")),
            unittest.mock.patch.object(cli, "read_trial_balance", return_value=balance) as read_balance,
            unittest.mock.patch.object(cli, "run_quarterly_audit", return_value=result) as run_audit,
            unittest.mock.patch.object(cli, "audit_result_to_dict", return_value={"ok": True}) as serialize,
            unittest.mock.patch.object(cli, "_write_or_print") as write,
        ):
            cli.main()

        read_balance.assert_called_once_with("balancete.csv", cliente="Cliente", periodo="2026-T1", cnpj="")
        run_audit.assert_called_once_with(balance, atividade="servicos")
        serialize.assert_called_once_with(result)
        self.assertEqual(json.loads(write.call_args.args[0]), {"ok": True})

    def test_main_generates_quarterly_markdown_payload(self):
        result = object()
        with (
            unittest.mock.patch.object(
                cli,
                "_parse_args",
                return_value=_args(
                    balancete="balancete.csv",
                    cliente="Cliente",
                    periodo="2026-T1",
                    markdown=True,
                    no_ai=False,
                    openrouter_key="key",
                    cnpj="12.345.678/0001-90",
                ),
            ),
            unittest.mock.patch.object(cli, "read_trial_balance", return_value=object()),
            unittest.mock.patch.object(cli, "run_quarterly_audit", return_value=result),
            unittest.mock.patch.object(cli, "audit_result_to_dict", return_value={"ok": True}),
            unittest.mock.patch("src.auditoria.report_ai.generate_markdown_report", return_value="markdown") as report,
            unittest.mock.patch.object(cli, "_write_or_print") as write,
        ):
            cli.main()

        report.assert_called_once_with(result, use_ai=True, api_key="key", cnpj="12.345.678/0001-90")
        write.assert_called_once_with("markdown", None, ascii_output=False)

    def test_main_generates_annual_json_and_markdown(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "t1.json"
            source.write_text(json.dumps({"identificacao_empresa": {"periodo_analisado": "2026-T1"}}), encoding="utf-8")

            with (
                unittest.mock.patch.object(cli, "_parse_args", return_value=_args(anual=[str(source)])),
                unittest.mock.patch("src.auditoria.annual.build_annual_comparison", return_value={"annual": True}) as build,
                unittest.mock.patch.object(cli, "_write_or_print") as write,
            ):
                cli.main()

            build.assert_called_once()
            self.assertEqual(json.loads(write.call_args.args[0]), {"annual": True})

            with (
                unittest.mock.patch.object(cli, "_parse_args", return_value=_args(anual=[str(source)], markdown=True, saida="annual.md")),
                unittest.mock.patch("src.auditoria.annual.build_annual_comparison", return_value={"annual": True}),
                unittest.mock.patch("src.auditoria.annual.generate_annual_markdown_report", return_value="annual markdown") as report,
                unittest.mock.patch.object(cli, "_write_or_print") as write,
            ):
                cli.main()

            report.assert_called_once_with({"annual": True})
            write.assert_called_once_with("annual markdown", "annual.md", ascii_output=False)

    def test_write_or_print_outputs_to_stdout_or_file_with_ascii_option(self):
        with unittest.mock.patch("builtins.print") as print_mock:
            cli._write_or_print("ol\u00e1", None, ascii_output=True)
        print_mock.assert_called_once_with("ola")

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "saida.txt"
            with unittest.mock.patch("builtins.print") as print_mock:
                cli._write_or_print("conteudo", str(output))

            self.assertEqual(output.read_text(encoding="utf-8"), "conteudo")
            self.assertIn("Resultado salvo", print_mock.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
