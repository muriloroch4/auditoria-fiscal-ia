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
from src.auditoria.annual import build_annual_comparison, generate_annual_markdown_report
from src.auditoria.models import RiskLevel, RuleFinding
from src.auditoria.parser import read_trial_balance_csv, read_trial_balance_csv_text, read_trial_balance_upload
from src.auditoria.report_ai import generate_markdown_report
from src.auditoria.serializers import audit_result_to_dict
from src.auditoria.risk import classify_total_risk, suggest_opinion_type
from src.auditoria.utils import format_brl, format_percent, sanitize_for_latin1
from src.auditoria.config_loader import _DEFAULT_CONFIG_PATH, load_config, get_rule_config, reload_config


class AuditPrototypeTest(unittest.TestCase):
    def test_sample_trial_balance_generates_report(self):
        sample = Path("samples/balancete_simples_servicos.csv")
        balance = read_trial_balance_csv(sample, cliente="Cliente Exemplo", periodo="2026-T1")

        result = run_quarterly_audit(balance)
        payload = audit_result_to_dict(result)

        self.assertEqual(result.nivel_geral, RiskLevel.ALTO)
        self.assertEqual(payload["_schema_version"], "2.0.0")
        self.assertIn("meta", payload)
        self.assertIn("identificacao", payload)
        self.assertIn("risco", payload)
        self.assertIn("metricas", payload)
        self.assertIn("achados", payload)
        self.assertIn("contexto_regime", payload)
        self.assertEqual(payload["risco"]["nivel_geral"], "alto")
        self.assertIn("explicacao_pontuacao", payload["risco"])
        self.assertIn("modalidade_opiniao_sugerida", payload["risco"])

    def test_local_markdown_report_uses_consultivo_template(self):
        sample = Path("samples/balancete_simples_servicos.csv")
        balance = read_trial_balance_csv(sample, cliente="Cliente Exemplo", periodo="2026-T1", cnpj="12.345.678/0001-90")

        result = run_quarterly_audit(balance)
        report = generate_markdown_report(result, use_ai=False)

        self.assertIn("PARECER TÉCNICO CONTÁBIL — CONSULTIVO TRIMESTRAL", report)
        self.assertIn("## 1. RESUMO EXECUTIVO", report)
        self.assertIn("## 2. ACHADOS E RECOMENDAÇÕES", report)
        self.assertIn("## 3. OPINIÃO TÉCNICA", report)
        self.assertIn("## 4. ASSINATURA", report)
        self.assertIn("CNPJ:     12.345.678/0001-90", report)

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
        self.assertTrue(len(finding_by_code["SN-008A"].normas_aplicaveis) > 0)

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

    def test_receivables_and_advances_generate_template_areas(self):
        content = dedent(
            """\
            codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual
            1.1.1;Banco;bancos;0;0;0;0
            1.1.2;Clientes;clientes;80000;0;0;80000
            1.1.3;Adiantamento a Fornecedores;adiantamentos;0;25000;0;25000
            2.1.1;Simples Nacional a Recolher;tributos;0;0;6000;6000
            3.1.1;Receita de Servicos;receita;0;0;100000;100000
            4.1.1;Pro Labore;folha;0;10000;0;-10000
            4.2.1;Despesas Administrativas;despesas;0;20000;0;-20000
            """
        )
        balance = read_trial_balance_csv_text(content, cliente="Recebiveis", periodo="2026-T1")
        result = run_quarterly_audit(balance)
        codes = {finding.codigo for finding in result.achados}

        self.assertIn("SN-010A", codes)
        self.assertIn("SN-011A", codes)

    def test_serialized_payload_contains_normas_aplicaveis(self):
        content = dedent(
            """\
            codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual
            1.1.1;Banco;bancos;0;0;0;0
            3.1.1;Receita;receita;0;0;100000;100000
            """
        )
        balance = read_trial_balance_csv_text(content, cliente="Normas", periodo="2026-T1")
        result = run_quarterly_audit(balance)
        payload = audit_result_to_dict(result)

        for achado in payload["achados"]:
            self.assertIn("normas_aplicaveis", achado)
            self.assertIsInstance(achado["normas_aplicaveis"], list)

    def test_suggest_opinion_type_logic(self):
        alto = RuleFinding(codigo="SN-008A", titulo="Test", nivel=RiskLevel.ALTO, pontuacao=20, descricao="Test")
        medio = RuleFinding(codigo="SN-007", titulo="Test", nivel=RiskLevel.MEDIO, pontuacao=16, descricao="Test")
        baixo = RuleFinding(codigo="SN-999", titulo="Test", nivel=RiskLevel.BAIXO, pontuacao=5, descricao="Test")
        composto = RuleFinding(codigo="SN-COMP-01", titulo="Test", nivel=RiskLevel.ALTO, pontuacao=15, descricao="Test")

        self.assertEqual(suggest_opinion_type(RiskLevel.ALTO, [alto]), "adversa")
        self.assertEqual(suggest_opinion_type(RiskLevel.MEDIO, [medio]), "com_ressalva")
        self.assertEqual(suggest_opinion_type(RiskLevel.BAIXO, [baixo]), "sem_ressalva")
        self.assertEqual(suggest_opinion_type(RiskLevel.BAIXO, [composto]), "adversa")

    def test_contexto_regime_is_present(self):
        content = dedent(
            """\
            codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual
            1.1.1;Banco;bancos;0;0;0;0
            3.1.1;Receita;receita;0;0;100000;100000
            """
        )
        balance = read_trial_balance_csv_text(content, cliente="Contexto", periodo="2026-T1")
        result = run_quarterly_audit(balance)

        self.assertEqual(result.regime_tributario, "Simples Nacional")
        self.assertIn("regime", result.contexto_regime)
        self.assertIn("faixa_receita_estimada", result.contexto_regime)
        self.assertIn("aliquota_efetiva_esperada", result.contexto_regime)

    def test_metricas_valores_in_result(self):
        content = dedent(
            """\
            codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual
            1.1.1;Banco;bancos;0;0;0;0
            3.1.1;Receita;receita;0;0;100000;100000
            """
        )
        balance = read_trial_balance_csv_text(content, cliente="Metricas", periodo="2026-T1")
        result = run_quarterly_audit(balance)

        self.assertIn("receita_servicos", result.metricas_valores)
        self.assertIn("indicadores_derivados", result.metricas_valores)
        self.assertIn("carga_tributaria_efetiva_percentual", result.metricas_valores["indicadores_derivados"])


class RiskClassificationTest(unittest.TestCase):
    def _make_finding(self, codigo="X", nivel=RiskLevel.BAIXO, pontuacao=5):
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


class ConfigTest(unittest.TestCase):
    def test_default_config_path_points_to_project_config_dir(self):
        self.assertEqual(_DEFAULT_CONFIG_PATH, Path("config/rules.json").resolve())

    def test_load_config_returns_dict(self):
        cfg = reload_config()
        self.assertIsInstance(cfg, dict)
        self.assertIn("descricao", cfg)
        self.assertIn("limites_gerais", cfg)
        self.assertIn("SN-001", cfg)

    def test_get_rule_config(self):
        cfg = get_rule_config("SN-003")
        self.assertIn("limite_medio", cfg)

    def test_get_rule_config_missing(self):
        cfg = get_rule_config("SN-999")
        self.assertEqual(cfg, {})


class SN009AccountingLossTest(unittest.TestCase):
    def test_significant_loss_triggers_sn009b(self):
        content = dedent(
            """\
            codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual
            1.1.1;Banco;bancos;0;0;20000;20000
            3.1.1;Receita de Servicos;receita;0;0;50000;50000
            4.1.1;Despesas;despesas;0;60000;0;-60000
            """
        )
        balance = read_trial_balance_csv_text(content, cliente="Prejuizo", periodo="2026-T1")
        result = run_quarterly_audit(balance)
        codes = {f.codigo for f in result.achados}
        self.assertTrue(any(c.startswith("SN-009") for c in codes), f"Expected SN-009 finding, got: {codes}")

    def test_no_loss_when_profitable(self):
        content = dedent(
            """\
            codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual
            1.1.1;Banco;bancos;0;0;100000;100000
            3.1.1;Receita;receita;0;0;100000;100000
            4.1.1;Despesas;despesas;0;20000;0;-20000
            """
        )
        balance = read_trial_balance_csv_text(content, cliente="Lucrativo", periodo="2026-T1")
        result = run_quarterly_audit(balance)
        codes = {f.codigo for f in result.achados}
        self.assertFalse(any(c.startswith("SN-009") for c in codes))


class MelhoriasMotorFiscalTest(unittest.TestCase):
    def test_receita_dominio_pode_vir_pelo_saldo_atual(self):
        content = dedent(
            """\
            codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual
            3.1.10;Servicos Prestados;receita;0;0;0;-190000
            3.1.20;(-) Simples Nacional;tributos_sobre_receita;0;0;0;12730
            4.2.20;Despesas Gerais;despesas;0;1603;0;1603
            """
        )
        balance = read_trial_balance_csv_text(content, cliente="Dominio Receita", periodo="2026-T3")
        result = run_quarterly_audit(balance)
        payload = audit_result_to_dict(result)

        self.assertEqual(payload["metricas"]["receita_servicos"]["valor"], 190000.0)
        self.assertEqual(payload["metricas"]["deducoes_receita"]["valor"], 12730.0)
        self.assertEqual(payload["metricas"]["lucro_apurado_base"]["valor"], 175667.0)

    def test_custos_entram_em_despesas_e_resultado_estimado(self):
        content = dedent(
            """\
            codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual
            1.1.1;Banco;bancos;0;0;0;0
            3.1.1;Receita de Servicos;receita;0;0;100000;100000
            4.1.1;Custos dos Servicos Prestados;custos;0;80000;0;-80000
            """
        )
        balance = read_trial_balance_csv_text(content, cliente="Custos", periodo="2026-T1")
        result = run_quarterly_audit(balance)
        payload = audit_result_to_dict(result)
        codes = {f.codigo for f in result.achados}

        self.assertIn("SN-007", codes)
        self.assertEqual(payload["metricas"]["despesas_operacionais"]["valor"], 80000.0)
        self.assertEqual(payload["metricas"]["lucro_apurado_base"]["valor"], 20000.0)

    def test_tributos_registrados_e_passivo_tributario_sao_metricas_separadas(self):
        content = dedent(
            """\
            codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual
            1.1.1;Banco;bancos;0;0;0;0
            2.1.4;Simples Nacional a Recolher;tributos_a_recolher;10000;0;20000;30000
            3.1.1;Receita de Servicos;receita;0;0;100000;100000
            3.1.2;(-) Simples Nacional;tributos_sobre_receita;0;2000;0;-2000
            """
        )
        balance = read_trial_balance_csv_text(content, cliente="Tributos separados", periodo="2026-T1")
        result = run_quarterly_audit(balance)
        payload = audit_result_to_dict(result)
        codes = {f.codigo for f in result.achados}

        self.assertIn("SN-002B", codes)
        self.assertIn("SN-012", codes)
        self.assertEqual(payload["metricas"]["tributos_registrados"]["valor"], 2000.0)
        self.assertEqual(payload["metricas"]["tributos_a_recolher"]["valor"], 30000.0)

    def test_adiantamentos_de_clientes_tambem_disparam_sn011(self):
        content = dedent(
            """\
            codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual
            1.1.1;Banco;bancos;0;0;0;0
            2.1.6;Adiantamentos de Clientes;adiantamentos_clientes;0;0;25000;-25000
            3.1.1;Receita de Servicos;receita;0;0;100000;100000
            """
        )
        balance = read_trial_balance_csv_text(content, cliente="Adiantamento Cliente", periodo="2026-T1")
        result = run_quarterly_audit(balance)
        codes = {f.codigo for f in result.achados}

        self.assertIn("SN-011A", codes)

    def test_lucros_a_pagar_por_credito_entram_como_distribuicao(self):
        content = dedent(
            """\
            codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual
            1.1.1;Banco;bancos;0;0;0;0
            2.1.7;Lucros e Dividendos a Pagar;lucros;0;0;60000;-60000
            3.1.1;Receita de Servicos;receita;0;0;100000;100000
            4.1.1;Custos;custos;0;70000;0;-70000
            """
        )
        balance = read_trial_balance_csv_text(content, cliente="Lucros Credito", periodo="2026-T1")
        result = run_quarterly_audit(balance)
        codes = {f.codigo for f in result.achados}

        self.assertIn("SN-004A", codes)

    def test_overlap_sn008_and_sn010_zero_revenue_with_receivables(self):
        content = dedent(
            """\
            codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual
            1.1.1;Banco Conta Movimento;bancos;0;50000;40000;10000
            1.1.2;Clientes;clientes;80000;0;0;80000
            3.1.1;Receita de Servicos;receita;0;0;0;0
            """
        )
        balance = read_trial_balance_csv_text(content, cliente="SN008xSN010", periodo="2026-T1")
        result = run_quarterly_audit(balance)
        codes = {f.codigo for f in result.achados}
        self.assertIn("SN-008A", codes)
        self.assertIn("SN-010A", codes)

    def test_sn011_advances_with_zero_revenue_does_not_trigger(self):
        content = dedent(
            """\
            codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual
            1.1.1;Banco;bancos;0;50000;40000;10000
            1.1.3;Adiantamento a Fornecedores;adiantamentos;0;25000;0;25000
            3.1.1;Receita;receita;0;0;0;0
            """
        )
        balance = read_trial_balance_csv_text(content, cliente="SN011 Zero", periodo="2026-T1")
        result = run_quarterly_audit(balance)
        codes = {f.codigo for f in result.achados}
        self.assertNotIn("SN-011A", codes)

    def test_sn_comp01_compound_rule_triggers(self):
        content = dedent(
            """\
            codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual
            1.1.1;Banco;bancos;0;100000;80000;20000
            3.1.1;Receita de Servicos;receita;0;0;5000;5000
            4.2.1;Despesas Gerais;despesas;0;8000;0;-8000
            """
        )
        balance = read_trial_balance_csv_text(content, cliente="SN-COMP-01", periodo="2026-T1")
        result = run_quarterly_audit(balance)
        codes = {f.codigo for f in result.achados}
        self.assertIn("SN-008B", codes)
        self.assertIn("SN-007", codes)
        self.assertIn("SN-COMP-01", codes)

    def test_sn012_tax_liability_growth_triggers(self):
        content = dedent(
            """\
            codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual
            1.1.1;Banco;bancos;0;0;0;0
            2.1.1;Simples a Recolher;tributos;10000;0;20000;30000
            3.1.1;Receita;receita;0;0;100000;100000
            """
        )
        balance = read_trial_balance_csv_text(content, cliente="SN-012", periodo="2026-T1")
        result = run_quarterly_audit(balance)
        codes = {f.codigo for f in result.achados}
        self.assertIn("SN-012", codes)

    def test_sn014_missing_provisions_with_significant_payroll(self):
        content = dedent(
            """\
            codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual
            1.1.1;Banco;bancos;0;0;0;0
            3.1.1;Receita;receita;0;0;100000;100000
            4.1.1;Salarios;folha;0;25000;0;-25000
            4.2.1;Despesas;despesas;0;10000;0;-10000
            """
        )
        balance = read_trial_balance_csv_text(content, cliente="SN-014", periodo="2026-T1")
        result = run_quarterly_audit(balance)
        codes = {f.codigo for f in result.achados}
        self.assertIn("SN-014", codes)

    def test_inferencia_grupo_from_conta_fallback(self):
        content = dedent(
            """\
            codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual
            1.1.1;Banco;bancos;0;0;0;0
            4.1.1;Provisao de Ferias;custom;0;5000;0;-5000
            4.2.1;Despesas Representacao;custom;0;3000;0;-3000
            3.1.1;Receita;receita;0;0;100000;100000
            """
        )
        balance = read_trial_balance_csv_text(content, cliente="Inferencia", periodo="2026-T1")
        contas_por_grupo = {c.grupo for c in balance.contas}
        self.assertIn("provisoes", contas_por_grupo)
        self.assertIn("despesas_representacao", contas_por_grupo)


class SchemaV2Test(unittest.TestCase):
    def test_audit_result_dict_has_schema_version(self):
        content = dedent(
            """\
            codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual
            1.1.1;Banco;bancos;0;0;0;0
            3.1.1;Receita;receita;0;0;100000;100000
            """
        )
        balance = read_trial_balance_csv_text(content, cliente="Schema", periodo="2026-T1")
        result = run_quarterly_audit(balance)
        payload = audit_result_to_dict(result)

        self.assertEqual(payload["_schema_version"], "2.0.0")
        self.assertEqual(payload["meta"]["versao_schema"], "2.0.0")
        self.assertEqual(payload["identificacao"]["regime_tributario"], "Simples Nacional")
        self.assertIn("total_contas_analisadas", payload["meta"])
        self.assertIn("total_regras_verificadas", payload["meta"])

    def test_risco_block_has_classificacao_and_opiniao(self):
        content = dedent(
            """\
            codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual
            1.1.1;Banco;bancos;0;0;0;0
            3.1.1;Receita;receita;0;0;100000;100000
            """
        )
        balance = read_trial_balance_csv_text(content, cliente="Risco", periodo="2026-T1")
        result = run_quarterly_audit(balance)
        payload = audit_result_to_dict(result)
        risco = payload["risco"]

        self.assertIn("classificacao", risco)
        self.assertIn("modalidade_opiniao_sugerida", risco)
        self.assertIn("achados_alto", risco["classificacao"])
        self.assertIn("achados_medio", risco["classificacao"])
        self.assertIn("achados_baixo", risco["classificacao"])
        self.assertIn("achados_compostos", risco["classificacao"])

    def test_metricas_block_has_valor_and_formatado(self):
        content = dedent(
            """\
            codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual
            1.1.1;Banco;bancos;0;0;0;0
            1.1.2;Clientes;clientes;70000;0;0;70000
            3.1.1;Receita;receita;0;0;100000;100000
            """
        )
        balance = read_trial_balance_csv_text(content, cliente="MetricasV2", periodo="2026-T1")
        result = run_quarterly_audit(balance)
        payload = audit_result_to_dict(result)
        metricas = payload["metricas"]

        self.assertIn("valor", metricas["receita_servicos"])
        self.assertIn("formatado", metricas["receita_servicos"])
        self.assertEqual(metricas["clientes_recebiveis"]["valor"], 70000.0)
        self.assertEqual(metricas["clientes_recebiveis"]["formatado"], "R$ 70.000,00")
        self.assertIn("indicadores_derivados", metricas)

    def test_total_regras_verificadas_uses_configured_sn_rules(self):
        content = dedent(
            """\
            codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual
            1.1.1;Banco;bancos;0;0;0;0
            3.1.1;Receita;receita;0;0;100000;100000
            """
        )
        balance = read_trial_balance_csv_text(content, cliente="Regras", periodo="2026-T1")
        result = run_quarterly_audit(balance)
        payload = audit_result_to_dict(result)
        expected_total = sum(1 for key in load_config() if key.startswith("SN-"))

        self.assertEqual(payload["meta"]["total_regras_verificadas"], expected_total)


class AnnualComparisonTest(unittest.TestCase):
    def test_build_annual_comparison_consolida_metricas_e_recorrencias(self):
        payloads = [
            self._quarter_payload("2026-T1", revenue=100000, expenses=80000),
            self._quarter_payload("2026-T2", revenue=100000, expenses=85000),
            self._quarter_payload("2026-T3", revenue=100000, expenses=10000),
            self._quarter_payload("2026-T4", revenue=100000, expenses=15000),
        ]

        annual = build_annual_comparison(payloads)
        codes = {finding["codigo"] for finding in annual["achados_anuais"]}

        self.assertEqual(annual["_schema_version"], "annual-1.0.0")
        self.assertEqual(annual["identificacao"]["exercicio"], "2026")
        self.assertEqual(annual["metricas_anual"]["receita_servicos_total"]["valor"], 400000.0)
        self.assertEqual(annual["meta"]["trimestres_ausentes"], [])
        self.assertIn("AN-REC-SN-007", codes)
        self.assertEqual(len(annual["comparativo_trimestral"]), 4)

    def test_generate_annual_markdown_report(self):
        payloads = [
            self._quarter_payload("2026-T1", revenue=100000, expenses=80000),
            self._quarter_payload("2026-T2", revenue=100000, expenses=85000),
            self._quarter_payload("2026-T3", revenue=100000, expenses=10000),
            self._quarter_payload("2026-T4", revenue=100000, expenses=15000),
        ]
        annual = build_annual_comparison(payloads)

        report = generate_annual_markdown_report(annual)

        self.assertIn("PARECER TÉCNICO CONTÁBIL — CONSULTIVO ANUAL COMPARATIVO", report)
        self.assertIn("## 2. COMPARATIVO TRIMESTRAL", report)
        self.assertIn("AN-REC-SN-007", report)

    def _quarter_payload(self, periodo: str, revenue: int, expenses: int) -> dict:
        content = dedent(
            f"""\
            codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual
            2.1.4;Simples Nacional a Recolher;tributos_a_recolher;1000;0;0;1000
            2.1.5;Provisao de Ferias;provisoes;1000;0;0;1000
            3.1.1;Receita de Servicos;receita;0;0;{revenue};{revenue}
            3.1.2;(-) Simples Nacional;tributos_sobre_receita;0;0;0;-6000
            4.1.1;Folha;folha;0;10000;0;-10000
            4.2.1;Despesas Operacionais;despesas;0;{expenses};0;-{expenses}
            """
        )
        balance = read_trial_balance_csv_text(content, cliente="Cliente Anual", periodo=periodo, cnpj="12.345.678/0001-90")
        return audit_result_to_dict(run_quarterly_audit(balance))


class APITest(unittest.TestCase):
    def _make_handler(self):
        from src.auditoria.api import AuditApiHandler
        class TestHandler(AuditApiHandler):
            def __init__(self):
                self.client_address = ("127.0.0.1", 8000)
        h = TestHandler()
        h.headers = {}
        h.wfile = io.BytesIO()
        h.rfile = io.BytesIO()
        return h

    def test_auth_check_rejects_missing_key(self):
        h = self._make_handler()
        h.api_key = "test-secret"
        h.headers = {}
        with unittest.mock.patch.object(h, "_send_json") as mock_send:
            result = h._check_auth()
            self.assertFalse(result)
            mock_send.assert_called_once()

    def test_auth_check_accepts_valid_key(self):
        h = self._make_handler()
        h.api_key = "test-secret"
        h.headers = {"X-API-Key": "test-secret"}
        result = h._check_auth()
        self.assertTrue(result)

    def test_no_auth_needed_when_api_key_none(self):
        h = self._make_handler()
        h.api_key = None
        h.headers = {}
        self.assertFalse(h.api_key)

    def test_max_upload_limit_constant(self):
        from src.auditoria.api import AuditApiHandler
        self.assertEqual(AuditApiHandler.max_upload_bytes, 10 * 1024 * 1024)


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
