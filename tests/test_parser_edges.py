from __future__ import annotations

import tempfile
import unittest
import unittest.mock
from decimal import Decimal
from pathlib import Path

from src.auditoria import parser
from src.auditoria.dominio_parser import (
    DOM_COL_CODIGO,
    DOM_COL_CREDITO,
    DOM_COL_DEBITO,
    DOM_COL_DESCRICAO,
    DOM_COL_SALDO_ANTERIOR,
    DOM_COL_SALDO_ATUAL,
    DOM_LINHA_CNPJ,
    DOM_LINHA_EMPRESA,
    DOM_LINHA_HEADER,
    DOM_LINHA_PERIODO,
    DOM_MIN_COLUNAS,
    dominio_cell,
    dominio_decimal,
    dominio_header_index,
    dominio_records,
    dominio_table_rows,
    find_dominio_header,
    is_dominio_format,
    looks_like_periodo,
    parse_dominio_balancete,
)
from src.auditoria.models import LedgerAccount, TrialBalance


def _blank_row() -> list[str]:
    return [""] * (DOM_MIN_COLUNAS + 1)


def _dominio_base_rows() -> list[list[str]]:
    rows = [_blank_row() for _ in range(8)]
    rows[DOM_LINHA_EMPRESA][1] = "EMPRESA TESTE LTDA"
    rows[DOM_LINHA_CNPJ][1] = "12.345.678/0001-90"
    rows[DOM_LINHA_PERIODO][1] = "1o Trimestre 2026"
    rows[DOM_LINHA_HEADER][DOM_COL_CODIGO] = "Classificacao"
    rows[DOM_LINHA_HEADER][DOM_COL_DESCRICAO] = "Descricao da conta"
    rows[7][DOM_COL_CODIGO] = "1.1.10.100.001"
    rows[7][DOM_COL_DESCRICAO] = "CAIXA MATRIZ"
    rows[7][DOM_COL_SALDO_ANTERIOR] = "1.234,56"
    rows[7][DOM_COL_DEBITO] = "100,00"
    rows[7][DOM_COL_CREDITO] = "50,00"
    rows[7][DOM_COL_SALDO_ATUAL] = "1.284,56"
    return rows


class DominioParserEdgeTest(unittest.TestCase):
    def test_is_dominio_format_rejects_each_required_metadata_piece(self):
        short_rows = [_blank_row() for _ in range(DOM_LINHA_HEADER)]
        self.assertFalse(is_dominio_format(short_rows))

        narrow_rows = [["x"] for _ in range(DOM_LINHA_HEADER + 1)]
        self.assertFalse(is_dominio_format(narrow_rows))

        for row_index, col_index, replacement in [
            (DOM_LINHA_EMPRESA, 1, ""),
            (DOM_LINHA_CNPJ, 1, "cnpj invalido"),
            (DOM_LINHA_PERIODO, 1, "periodo invalido"),
        ]:
            rows = _dominio_base_rows()
            rows[row_index][col_index] = replacement
            self.assertFalse(is_dominio_format(rows))

        rows_without_header = _dominio_base_rows()
        rows_without_header[DOM_LINHA_HEADER][DOM_COL_CODIGO] = "Outro"
        rows_without_header[DOM_LINHA_HEADER][DOM_COL_DESCRICAO] = "Cabecalho"
        self.assertFalse(is_dominio_format(rows_without_header))

        self.assertFalse(is_dominio_format([None]))  # type: ignore[list-item]

    def test_period_detection_supports_common_quarter_formats(self):
        for value in ("01/01/2026 - 31/03/2026", "Q1 2026", "1o Trimestre 2026", "Jan-Mar 2026"):
            with self.subTest(value=value):
                self.assertTrue(looks_like_periodo(value))
        self.assertFalse(looks_like_periodo("fechamento sem ano"))

    def test_parse_dominio_rejects_invalid_format_and_without_leaf_accounts(self):
        with self.assertRaisesRegex(ValueError, "nao foi reconhecido"):
            parse_dominio_balancete(b"codigo;conta\n1;Caixa\n", filename="generico.csv")

        rows = _dominio_base_rows()
        rows[7][DOM_COL_CODIGO] = "1.1"
        text = "\n".join(";".join(row) for row in rows)

        with self.assertRaisesRegex(ValueError, "Nenhuma conta folha"):
            parse_dominio_balancete(text.encode("utf-8"), filename="dominio.csv")

    def test_dominio_table_rows_uses_latin1_fallback_and_decimal_variants(self):
        rows = dominio_table_rows("codigo;conta\n1;A\u00e7\u00e3o\n".encode("latin-1"), "teste.csv")

        self.assertEqual(rows[1][1], "A\u00e7\u00e3o")
        self.assertEqual(dominio_decimal(""), Decimal("0"))
        self.assertEqual(dominio_decimal("nan"), Decimal("0"))
        self.assertEqual(dominio_decimal("\u22121.234,50"), Decimal("-1234.50"))
        self.assertEqual(dominio_decimal("1234.50"), Decimal("1234.50"))
        with self.assertRaisesRegex(ValueError, "Valor numerico invalido"):
            dominio_decimal("abc")

    def test_dominio_cell_and_header_fallbacks(self):
        rows = _dominio_base_rows()
        self.assertEqual(dominio_cell(rows, 999, 1), "")
        self.assertEqual(dominio_header_index(rows), DOM_LINHA_HEADER)

        moved_header = [_blank_row() for _ in range(3)]
        moved_header.append(["Codigo", "Classificacao", "Descricao da conta", "Saldo anterior", "Debito", "Credito", "Saldo atual"])
        self.assertEqual(find_dominio_header(moved_header), 3)

    def test_dominio_records_handles_missing_header_missing_columns_and_valid_records(self):
        self.assertIsNone(dominio_records([["sem", "header"]]))
        self.assertIsNone(dominio_records([["Codigo", "Classificacao", "Descricao da conta"]]))

        table = [
            ["Ignorar"],
            ["Codigo", "Classificacao", "Descricao da conta", "Saldo anterior", "Debito", "Credito", "Saldo atual"],
            ["1", "1.1", "ATIVO TOTAL", "0", "0", "0", "0"],
            ["2", "ABC", "INVALIDA", "0", "0", "0", "0"],
            ["3", "1.1.10.100.001", "CAIXA MATRIZ", "0", "10", "5", "5"],
            ["4", "3.1.10.200.001", "SERVICOS PRESTADOS", "0", "0", "100", "100"],
        ]

        records = dominio_records(table)

        self.assertEqual(len(records or []), 2)
        self.assertEqual(records[0]["codigo"], "1.1.10.100.001")
        self.assertEqual(records[0]["grupo"], "caixa")
        self.assertEqual(records[1]["grupo"], "receita")

        with unittest.mock.patch("src.auditoria.dominio_parser._dominio_group", return_value=""):
            self.assertEqual(dominio_records(table), [])


class GenericParserEdgeTest(unittest.TestCase):
    def _balance(self) -> TrialBalance:
        return TrialBalance(
            cliente="Cliente",
            periodo="2026-T1",
            cnpj="12.345.678/0001-90",
            contas=[
                LedgerAccount(
                    codigo="1.1.1",
                    conta="Banco",
                    grupo="bancos",
                    saldo_anterior=Decimal("0"),
                    debito=Decimal("0"),
                    credito=Decimal("0"),
                    saldo_atual=Decimal("0"),
                )
            ],
        )

    def test_read_trial_balance_routes_by_extension_and_rejects_unknown(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            csv_path = tmp / "balancete.csv"
            xlsx_path = tmp / "balancete.xlsx"
            xls_path = tmp / "balancete.xls"
            txt_path = tmp / "balancete.txt"
            csv_path.write_text("codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual\n1;Banco;bancos;0;0;0;0\n", encoding="utf-8")
            xlsx_path.write_bytes(b"xlsx")
            xls_path.write_bytes(b"xls")
            txt_path.write_text("x", encoding="utf-8")

            with unittest.mock.patch.object(parser, "read_trial_balance_xlsx_bytes", return_value=self._balance()) as xlsx:
                self.assertEqual(parser.read_trial_balance_xlsx(xlsx_path, "Cliente", "2026-T1").cliente, "Cliente")
                xlsx.assert_called_once()

            with unittest.mock.patch.object(parser, "read_trial_balance_xls_bytes", return_value=self._balance()) as xls:
                self.assertEqual(parser.read_trial_balance(xls_path, "Cliente", "2026-T1").cliente, "Cliente")
                xls.assert_called_once()

            with self.assertRaisesRegex(ValueError, "Formato nao suportado"):
                parser.read_trial_balance(txt_path, "Cliente", "2026-T1")

    def test_read_trial_balance_upload_routes_xls_and_unsupported_extensions(self):
        with unittest.mock.patch.object(parser, "read_trial_balance_xls_bytes", return_value=self._balance()) as xls:
            balance = parser.read_trial_balance_upload("balancete.xls", b"\xff\xfe", cliente="Cliente", periodo="2026-T1")

        self.assertEqual(balance.cliente, "Cliente")
        xls.assert_called_once()

        with self.assertRaisesRegex(ValueError, "Formato nao suportado"):
            parser.read_trial_balance_upload("balancete.pdf", b"%PDF")

    def test_read_trial_balance_upload_accepts_textual_dominio_xls(self):
        rows = _dominio_base_rows()
        text = "\n".join(";".join(row) for row in rows)

        balance = parser.read_trial_balance_upload("balancete.xls", text.encode("utf-8"), cliente="Override")

        self.assertEqual(balance.cliente, "Override")
        self.assertEqual(len(balance.contas), 1)
        self.assertEqual(balance.contas[0].grupo, "caixa")

    def test_xls_conversion_delegates_to_converted_xlsx_reader(self):
        with (
            unittest.mock.patch.object(parser, "_convert_xls_to_xlsx") as convert,
            unittest.mock.patch.object(parser, "read_trial_balance_xlsx", return_value=self._balance()) as read_xlsx,
        ):
            balance = parser.read_trial_balance_xls_bytes(b"xls-binary", cliente="Cliente", periodo="2026-T1")

        self.assertEqual(balance.cliente, "Cliente")
        convert.assert_called_once()
        read_xlsx.assert_called_once()

    def test_xlsx_records_uses_table_rows_converter(self):
        table = [["codigo", "conta", "grupo", "saldo_anterior", "debito", "credito", "saldo_atual"]]
        with (
            unittest.mock.patch.object(parser, "_xlsx_table_rows", return_value=table) as rows,
            unittest.mock.patch.object(parser, "_records_from_table_rows", return_value=[]) as records,
        ):
            self.assertEqual(parser._xlsx_records(b"xlsx"), [])

        rows.assert_called_once_with(b"xlsx")
        records.assert_called_once_with(table, source_name="XLSX")


if __name__ == "__main__":
    unittest.main()
