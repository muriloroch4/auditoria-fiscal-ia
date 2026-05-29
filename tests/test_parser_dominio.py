from __future__ import annotations

import unittest
from decimal import Decimal
from pathlib import Path

from src.auditoria.parser import (
    VALID_GRUPOS,
    _csv_table_rows,
    _dominio_extract_metadata,
    _dominio_group,
    _dominio_is_leaf,
    is_dominio_format,
    parse_dominio_balancete,
    read_trial_balance_upload,
)


DOMINIO_XLS_SIMULADO = (
    ",SSA TELECOM LTDA,,,,,,,,,,,,,,\n"
    ",54.244.372/0001-92,,,,,,,,,,,,,,\n"
    ",01/07/2025 - 30/09/2025,,,,,,,,,,,,,,\n"
    ",,,,,,,,,,,,,,,\n"
    "BALANCETE,,,,,,,,,,,,,,,\n"
    ",,,,,,,,,,,,,,,\n"
    ",Classificacao,,Descricao da conta,,,,Saldo Anterior,,Debito,,Credito,,Saldo Atual,\n"
    ",1,,ATIVO,,,,190005.48,,41397.02,,40149.58,,191252.92,\n"
    ",1.1.10.1,,CAIXA E EQUIVALENTES,,,,5.25,,0,,3116.99,,-3111.74,\n"
    ",1.1.10.100.001,,CAIXA MATRIZ,,,,5.25,,0,,3116.99,,-3111.74,\n"
    ",1.1.10.200.006,,BANCO ITAU,,,,0.23,,36245.29,,36240.01,,5.51,\n"
    ",1.1.20.100.001,,CLIENTES PULVERIZADOS,,,,190000,,0,,0,,190000,\n"
    ",1.1.30.500.001,,ADIANTAMENTOS A FORNECEDORES,,,,0,,4359.15,,0,,4359.15,\n"
    ",1.1.30.800.006,,INSS A RECUPERAR,,,,0,,792.58,,792.58,,0,\n"
    ",2.1.40.100.008,,SIMPLES NACIONAL A RECOLHER,,,,-12730,,0,,0,,-12730,\n"
    ",2.1.50.100.001,,SALARIOS E ORDENADOS A PAGAR,,,,-4963.33,,17526.59,,27751.59,,-15188.33,\n"
    ",2.1.50.200.001,,INSS A RECOLHER,,,,-1328.99,,4784.53,,4906.97,,-1451.43,\n"
    ",2.1.60.100.001,,ADIANTAMENTO DE CLIENTES,,,,-0.23,,0,,0,,-0.23,\n"
    ",2.1.60.600.002,,SOCIOS ADMINISTRADORES E PESSOAS LIGADAS,,,,0,,0,,500,,-500,\n"
    ",2.2.11.300.001,,EMPRESTIMO DE TERCEIROS,,,,0,,0,,35745.29,,-35745.29,\n"
    ",2.3.10.100.001,,CAPITAL SOCIAL,,,,-20000,,0,,0,,-20000,\n"
    ",3.1.10.200.001,,SERVICOS PRESTADOS,,,,-190000,,0,,0,,-190000,\n"
    ",3.1.20.300.008,,(-) SIMPLES NACIONAL,,,,12730,,0,,0,,12730,\n"
    ",4.1.20.400.001,,ASSISTENCIA MEDICA E MEDICAMENTOS,,,,0,,444,,0,,444,\n"
    ",4.2.20.100.002,,PRO-LABORE,,,,24472.23,,24472.23,,0,,48944.46,\n"
    ",4.2.20.300.007,,MULTAS DE MORA,,,,1.73,,0,,0,,1.73,\n"
    ",4.2.20.400.008,,ASSISTENCIA CONTABIL,,,,0,,1000,,0,,1000,\n"
    ",4.2.20.500.008,,DESPESAS BANCARIAS,,,,0,,159,,0,,159,\n"
).encode("utf-8")


class DominioParserTest(unittest.TestCase):
    def _rows(self):
        return _csv_table_rows(DOMINIO_XLS_SIMULADO.decode("utf-8"))

    def test_is_dominio_format_reconhece_layout_real(self):
        self.assertTrue(is_dominio_format(self._rows()))

    def test_is_dominio_format_rejeita_csv_generico(self):
        rows = _csv_table_rows("codigo,conta,grupo,saldo_anterior,debito,credito,saldo_atual\n")
        self.assertFalse(is_dominio_format(rows))

    def test_extract_metadata(self):
        metadata = _dominio_extract_metadata(self._rows())
        self.assertEqual(metadata["cliente"], "SSA TELECOM LTDA")
        self.assertEqual(metadata["cnpj"], "54.244.372/0001-92")
        self.assertEqual(metadata["periodo"], "01/07/2025 - 30/09/2025")

    def test_dominio_is_leaf(self):
        cases = {
            "1": False,
            "1.1": False,
            "1.1.10.1": False,
            "1.1.10.100.001": True,
            "4.2.20.300.007": True,
            "1.1.10.100.001.1": True,
            "ABC": False,
            "": False,
        }
        for codigo, expected in cases.items():
            with self.subTest(codigo=codigo):
                self.assertEqual(_dominio_is_leaf(codigo), expected)

    def test_dominio_group_mapeamento_principal(self):
        cases = [
            ("1.1.10.100.001", "CAIXA MATRIZ", "caixa"),
            ("1.1.10.200.006", "BANCO ITAU", "bancos"),
            ("1.1.20.100.001", "CLIENTES PULVERIZADOS", "clientes"),
            ("1.1.30.500.001", "ADIANTAMENTOS A FORNECEDORES", "adiantamentos"),
            ("1.1.30.800.006", "INSS A RECUPERAR", "creditos_fiscais"),
            ("2.1.40.100.008", "SIMPLES NACIONAL A RECOLHER", "tributos"),
            ("2.1.50.100.001", "SALARIOS E ORDENADOS A PAGAR", "folha"),
            ("2.1.50.200.001", "INSS A RECOLHER", "tributos"),
            ("2.1.60.100.001", "ADIANTAMENTO DE CLIENTES", "adiantamentos_clientes"),
            ("2.1.60.600.002", "SOCIOS ADMINISTRADORES", "socios"),
            ("2.2.11.300.001", "EMPRESTIMO DE TERCEIROS", "emprestimos"),
            ("2.3.10.100.001", "CAPITAL SOCIAL", "patrimonio"),
            ("3.1.10.200.001", "SERVICOS PRESTADOS", "receita"),
            ("3.1.20.300.008", "(-) SIMPLES NACIONAL", "tributos"),
            ("4.2.20.300.007", "MULTAS DE MORA", "multas_fiscais"),
            ("4.2.20.400.009", "DESPESAS DE VIAGEM", "despesas_representacao"),
            ("4.2.20.500.010", "COMBUSTIVEL", "despesas_veiculos"),
        ]
        for codigo, descricao, expected in cases:
            with self.subTest(codigo=codigo):
                self.assertEqual(_dominio_group(codigo, descricao), expected)
                self.assertIn(expected, VALID_GRUPOS)

    def test_parse_dominio_balancete_filtra_totalizadores_e_preserva_sinais(self):
        balance = parse_dominio_balancete(DOMINIO_XLS_SIMULADO, filename="dominio.csv")
        self.assertEqual(balance.cliente, "SSA TELECOM LTDA")
        self.assertEqual(balance.cnpj, "54.244.372/0001-92")
        self.assertEqual(balance.periodo, "01/07/2025 - 30/09/2025")
        self.assertTrue(all(len(account.codigo.split(".")) >= 5 for account in balance.contas))

        accounts = {account.codigo: account for account in balance.contas}
        self.assertNotIn("1.1.10.1", accounts)
        self.assertEqual(accounts["2.1.40.100.008"].grupo, "tributos")
        self.assertEqual(accounts["2.1.40.100.008"].saldo_atual, Decimal("-12730"))
        self.assertEqual(accounts["1.1.10.200.006"].grupo, "bancos")
        self.assertEqual(accounts["1.1.10.200.006"].saldo_atual, Decimal("5.51"))
        self.assertEqual(accounts["4.2.20.300.007"].grupo, "multas_fiscais")

    def test_parse_dominio_overrides(self):
        balance = parse_dominio_balancete(
            DOMINIO_XLS_SIMULADO,
            filename="dominio.csv",
            cliente_override="OUTRA EMPRESA LTDA",
            periodo_override="2025-T3",
            cnpj_override="99.999.999/0001-99",
        )
        self.assertEqual(balance.cliente, "OUTRA EMPRESA LTDA")
        self.assertEqual(balance.periodo, "2025-T3")
        self.assertEqual(balance.cnpj, "99.999.999/0001-99")

    def test_read_trial_balance_upload_usa_dominio_automaticamente(self):
        balance = read_trial_balance_upload(
            filename="balancete_dominio.xls",
            content=DOMINIO_XLS_SIMULADO,
        )
        self.assertEqual(balance.cliente, "SSA TELECOM LTDA")
        self.assertEqual(balance.cnpj, "54.244.372/0001-92")
        self.assertGreater(len(balance.contas), 0)
        self.assertTrue(all(account.grupo in VALID_GRUPOS for account in balance.contas))

    def test_read_trial_balance_upload_reconhece_xlsx_real_ssa_telecom(self):
        path = Path("samples/Balancete - SSA TELECOM 3º TRIM.xlsx")
        if not path.exists():
            self.skipTest("Arquivo real SSA TELECOM nao encontrado em samples.")

        balance = read_trial_balance_upload(path.name, path.read_bytes())

        self.assertEqual(balance.cliente, "SSA TELECOM LTDA")
        self.assertEqual(balance.cnpj, "54.244.372/0001-92")
        self.assertEqual(balance.periodo, "01/07/2025 - 30/09/2025")
        self.assertEqual(len(balance.contas), 29)


if __name__ == "__main__":
    unittest.main()
