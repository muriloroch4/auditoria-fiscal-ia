import io
import json
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
from src.auditoria.storage import infer_year_quarter
from src.auditoria.risk import classify_total_risk, suggest_opinion_type
from src.auditoria.utils import format_brl, format_percent, sanitize_for_latin1
from src.auditoria.config_loader import (
    _DEFAULT_ACCOUNT_MAP_PATH,
    _DEFAULT_CONFIG_PATH,
    get_rule_config,
    load_account_map,
    load_config,
    reload_config,
)


def _iter_text_project_files(roots: list[Path], suffixes: set[str]):
    for root in roots:
        if not root.exists():
            continue
        candidates = [root] if root.is_file() else root.rglob("*")
        for path in candidates:
            if path.is_file() and path.suffix.lower() in suffixes:
                yield path


class AuditPrototypeTest(unittest.TestCase):
    def test_sample_trial_balance_generates_report(self):
        sample = Path("samples/balancete_simples_servicos.csv")
        balance = read_trial_balance_csv(sample, cliente="Cliente Exemplo", periodo="2026-T1")

        result = run_quarterly_audit(balance)
        payload = audit_result_to_dict(result)

        self.assertEqual(result.nivel_geral, RiskLevel.ALTO)
        self.assertEqual(payload["metadados"]["versao_schema"], "3.0.0")
        self.assertIn("identificacao_empresa", payload)
        self.assertIn("resumo_analise", payload)
        self.assertIn("principais_achados", payload)
        self.assertIn("fundamentacao_tecnica_resumida", payload)
        self.assertIn("conclusao_tecnica", payload)
        self.assertIn("recomendacoes_tecnicas", payload)
        self.assertEqual(payload["resumo_analise"]["risco_geral"], "alto")
        self.assertIn("principais_pontos", payload["resumo_analise"])
        self.assertIn("conclusao_sugerida", payload["conclusao_tecnica"])

    def test_local_markdown_report_uses_consultivo_template(self):
        sample = Path("samples/balancete_simples_servicos.csv")
        balance = read_trial_balance_csv(sample, cliente="Cliente Exemplo", periodo="2026-T1", cnpj="12.345.678/0001-90")

        result = run_quarterly_audit(balance)
        report = generate_markdown_report(result, use_ai=False)

        self.assertIn("Parecer técnico contábil consultivo trimestral", report)
        self.assertIn("## 1. Resumo executivo", report)
        self.assertIn("## 2. Achados e recomendações", report)
        self.assertIn("## 3. Opinião técnica", report)
        self.assertIn("## 4. Assinatura", report)
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

        for achado in payload["principais_achados"]:
            self.assertIn("norma_fundamento", achado)
            self.assertIsInstance(achado["norma_fundamento"], list)

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

    def test_contexto_comercio_usa_anexo_i(self):
        content = dedent(
            """\
            codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual
            1.1.5;Mercadorias;estoques;0;0;0;30000
            3.1.1;Receita de Comercio;receita;0;0;100000;100000
            4.1.1;CMV;custos;0;40000;0;-40000
            """
        )
        balance = read_trial_balance_csv_text(content, cliente="Comercio", periodo="2026-T1")
        result = run_quarterly_audit(balance, atividade="comercio")

        self.assertIn("Anexo I", result.contexto_regime["anexo_estimado"])
        self.assertEqual(result.contexto_regime["aliquota_nominal_estimada"], "9,50%")
        self.assertIn("efetiva estimada 6,04%", result.contexto_regime["aliquota_efetiva_esperada"])

    def test_contexto_servicos_fator_r_baixo_usa_anexo_v(self):
        content = dedent(
            """\
            codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual
            3.1.1;Receita de Servicos;receita;0;0;100000;100000
            4.1.1;Folha;folha;0;10000;0;-10000
            """
        )
        balance = read_trial_balance_csv_text(content, cliente="Servicos", periodo="2026-T1")
        result = run_quarterly_audit(balance, atividade="servicos")

        self.assertIn("Anexo V", result.contexto_regime["anexo_estimado"])
        self.assertEqual(result.contexto_regime["aliquota_nominal_estimada"], "19,50%")

    def test_contexto_servicos_fator_r_alto_usa_anexo_iii(self):
        content = dedent(
            """\
            codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual
            3.1.1;Receita de Servicos;receita;0;0;100000;100000
            4.1.1;Folha;folha;0;40000;0;-40000
            """
        )
        balance = read_trial_balance_csv_text(content, cliente="Servicos", periodo="2026-T1")
        result = run_quarterly_audit(balance, atividade="servicos")

        self.assertIn("Anexo III", result.contexto_regime["anexo_estimado"])
        self.assertEqual(result.contexto_regime["aliquota_nominal_estimada"], "13,50%")

    def test_contexto_rbt12_substitui_receita_anualizada(self):
        content = dedent(
            """\
            codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual
            1.1.5;Mercadorias;estoques;0;0;0;30000
            3.1.1;Receita de Comercio;receita;0;0;100000;100000
            4.1.1;CMV;custos;0;40000;0;-40000
            """
        )
        balance = read_trial_balance_csv_text(content, cliente="Comercio RBT12", periodo="2026-T4")
        result = run_quarterly_audit(
            balance,
            atividade="comercio",
            contexto_rbt12={
                "receita": 1000000,
                "origem": "teste",
                "base_calculo": "RBT12 real informado",
            },
        )

        self.assertTrue(result.contexto_regime["rbt12_disponivel"])
        self.assertEqual(result.contexto_regime["receita_rbt12_utilizada"], "R$ 1.000.000,00")
        self.assertEqual(result.contexto_regime["aliquota_nominal_estimada"], "10,70%")
        self.assertEqual(result.contexto_regime["base_calculo_estimativa"], "RBT12 real informado")

    def test_fator_r_usa_rbt12_quando_disponivel(self):
        content = dedent(
            """\
            codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual
            3.1.1;Receita de Servicos;receita;0;0;100000;100000
            4.1.1;Folha;folha;0;10000;0;-10000
            """
        )
        balance = read_trial_balance_csv_text(content, cliente="Servico RBT12", periodo="2026-T4")
        result = run_quarterly_audit(
            balance,
            atividade="servicos",
            contexto_rbt12={"receita": 400000, "folha": 200000, "base_calculo": "RBT12 real informado"},
        )

        self.assertIn("Anexo III", result.contexto_regime["anexo_estimado"])
        self.assertEqual(result.contexto_regime["fator_r_calculado"], "50,00%")
        self.assertEqual(result.contexto_regime["fator_r_base"], "RBT12 consolidado")

    def test_sn001_usa_rbt12_quando_disponivel(self):
        content = dedent(
            """\
            codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual
            3.1.1;Receita de Servicos;receita;0;0;100000;100000
            4.1.1;Folha;folha;0;40000;0;-40000
            """
        )
        balance = read_trial_balance_csv_text(content, cliente="Limite RBT12", periodo="2026-T4")
        result = run_quarterly_audit(balance, contexto_rbt12={"receita": 4400000, "folha": 1000000})
        finding = next(f for f in result.achados if f.codigo == "SN-001B")

        self.assertEqual(finding.evidencia["base_calculo_limite"], "RBT12 consolidado pelo historico")
        self.assertEqual(finding.evidencia["receita_anualizada_estimativa"], "R$ 4.400.000,00")

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


class GoldenPipelineTest(unittest.TestCase):
    def _sample_result_and_payload(self):
        sample = Path("samples/exemplo_balancete_todas_regras.csv")
        balance = read_trial_balance_csv(
            sample,
            cliente="Golden Todas Regras",
            periodo="2026-T1",
            cnpj="12.345.678/0001-90",
        )
        result = run_quarterly_audit(balance)
        payload = audit_result_to_dict(result)
        payload["metadados"]["data_analise"] = "2000-01-01T00:00:00"
        return result, payload

    def test_exemplo_balancete_todas_regras_matches_golden_json(self):
        _, payload = self._sample_result_and_payload()
        expected = Path("tests/golden/exemplo_balancete_todas_regras.v3.json").read_text(encoding="utf-8").strip()
        actual = json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True)

        self.assertEqual(actual, expected)

    def test_exemplo_balancete_todas_regras_markdown_outputs_sem_mojibake(self):
        result, payload = self._sample_result_and_payload()
        markdown = generate_markdown_report(result, use_ai=False, cnpj="12.345.678/0001-90")
        annual_payload = build_annual_comparison([
            self._payload_for_annual(result, payload, f"2026-T{quarter}")
            for quarter in range(1, 5)
        ])
        annual_markdown = generate_annual_markdown_report(annual_payload)
        combined = markdown + "\n" + annual_markdown

        self.assertIn("Créditos fiscais finais", annual_markdown)
        for token in ("\u00c3\u00a9", "\u00c3\u00a1", "\u00c3\u00a3", "\u00c3\u00a7", "\u00c3\u00aa", "\u00c3\u00ad", "\u00c3\u00b3", "\u00c3\u00ba", "\u00c3\u0192", "\ufffd"):
            self.assertNotIn(token, combined)

    def _payload_for_annual(self, result, payload, periodo: str) -> dict:
        cloned = json.loads(json.dumps(payload))
        cloned["identificacao_empresa"]["periodo_analisado"] = periodo
        cloned["metricas"] = {
            key: {
                "valor": value,
                "formatado": result.resumo_metricas.get(key, str(value)),
            }
            for key, value in result.metricas_valores.items()
            if isinstance(value, (int, float))
        }
        return cloned


class ProjectQualityTest(unittest.TestCase):
    def test_text_files_do_not_contain_mojibake_markers(self):
        roots = [
            Path("src"),
            Path("tests"),
            Path("docs"),
            Path("config"),
            Path(".github"),
            Path("README.md"),
            Path("REGRAS.md"),
            Path("pyproject.toml"),
            Path("requirements.txt"),
            Path("requirements-dev.txt"),
        ]
        suffixes = {".py", ".js", ".css", ".html", ".md", ".json", ".toml", ".txt", ".yml", ".yaml"}
        bad_tokens = (
            "\u00c3",
            "\u00c2",
            "\ufffd",
        )
        offenders: list[str] = []

        for path in _iter_text_project_files(roots, suffixes):
            text = path.read_text(encoding="utf-8", errors="replace")
            for line_number, line in enumerate(text.splitlines(), start=1):
                if any(token in line for token in bad_tokens):
                    offenders.append(f"{path}:{line_number}: {line[:160]}")

        self.assertEqual(offenders, [])


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

    def test_default_account_map_path_points_to_project_config_dir(self):
        self.assertEqual(_DEFAULT_ACCOUNT_MAP_PATH, Path("config/plano_contas_map.json").resolve())

    def test_load_config_returns_dict(self):
        cfg = reload_config()
        self.assertIsInstance(cfg, dict)
        self.assertIn("descricao", cfg)
        self.assertIn("limites_gerais", cfg)
        self.assertIn("SN-001", cfg)

    def test_load_account_map_contains_conta_325(self):
        account_map = load_account_map()
        self.assertIsInstance(account_map, dict)
        self.assertTrue(any("325" in item.get("codigos_exatos", []) for item in account_map.get("mapeamentos", [])))

    def test_get_rule_config(self):
        cfg = get_rule_config("SN-003")
        self.assertIn("limite_medio", cfg)

    def test_get_rule_config_missing(self):
        cfg = get_rule_config("SN-999")
        self.assertEqual(cfg, {})


class PeriodInferenceTest(unittest.TestCase):
    def test_infer_year_quarter_accepts_common_quarter_formats(self):
        cases = {
            "2026-T1": (2026, 1),
            "T2/2026": (2026, 2),
            "2026 Q3": (2026, 3),
            "1T2026": (2026, 1),
            "1º Trimestre/2026": (2026, 1),
            "Terceiro trimestre de 2026": (2026, 3),
            "Jan-Mar 2026": (2026, 1),
            "Out-Dez/2026": (2026, 4),
            "01/04/2026 - 30/06/2026": (2026, 2),
        }
        for periodo, expected in cases.items():
            with self.subTest(periodo=periodo):
                self.assertEqual(infer_year_quarter(periodo), expected)

    def test_infer_year_quarter_unknown_format_keeps_year_and_zero_quarter(self):
        self.assertEqual(infer_year_quarter("Exercicio 2026"), (2026, 0))


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

        self.assertEqual(result.metricas_valores["receita_servicos"], 190000.0)
        self.assertEqual(result.metricas_valores["deducoes_receita"], 12730.0)
        self.assertEqual(result.metricas_valores["lucro_apurado_base"], 175667.0)

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
        codes = {f.codigo for f in result.achados}

        self.assertIn("SN-007", codes)
        self.assertEqual(result.metricas_valores["despesas_operacionais"], 80000.0)
        self.assertEqual(result.metricas_valores["lucro_apurado_base"], 20000.0)

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
        codes = {f.codigo for f in result.achados}

        self.assertIn("SN-002B", codes)
        self.assertIn("SN-012", codes)
        self.assertEqual(result.metricas_valores["tributos_registrados"], 2000.0)
        self.assertEqual(result.metricas_valores["tributos_a_recolher"], 30000.0)

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

    def test_lucros_acumulados_suportam_distribuicao_trimestral(self):
        content = dedent(
            """\
            codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual
            1.1.1;Banco;bancos;0;0;0;0
            2.3.20;Lucros Acumulados;patrimonio;0;0;90000;-90000
            3.1.1;Receita de Servicos;receita;0;0;100000;100000
            4.1.1;Custos;custos;0;120000;0;-120000
            5.1.1;Distribuicao de Lucros;lucros;0;50000;0;-50000
            """
        )
        balance = read_trial_balance_csv_text(content, cliente="Lucros Acumulados", periodo="2026-T1")
        result = run_quarterly_audit(balance)
        codes = {f.codigo for f in result.achados}

        self.assertNotIn("SN-004A", codes)
        self.assertIn("SN-004B", codes)

    def test_sn001_evidencia_receita_trimestral_anualizada(self):
        content = dedent(
            """\
            codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual
            1.1.1;Banco;bancos;0;0;0;0
            3.1.1;Receita de Servicos;receita;0;0;900000;900000
            4.1.1;Folha;folha;0;100000;0;-100000
            """
        )
        balance = read_trial_balance_csv_text(content, cliente="Receita Alta", periodo="2026-T1")
        result = run_quarterly_audit(balance)
        finding = next(f for f in result.achados if f.codigo == "SN-001A")

        self.assertIn("receita_anualizada_estimativa", finding.evidencia)
        self.assertIn("limite_anual_simples", finding.evidencia)

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

    def test_sn011_usa_maior_referencia_entre_percentual_e_valor_absoluto(self):
        content = dedent(
            """\
            codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual
            1.1.1;Banco;bancos;0;0;0;0
            1.1.3;Adiantamento a Fornecedores;adiantamentos;0;15000;0;15000
            3.1.1;Receita;receita;0;0;200000;200000
            """
        )
        balance = read_trial_balance_csv_text(content, cliente="SN011 Referencia", periodo="2026-T1")
        result = run_quarterly_audit(balance)
        codes = {f.codigo for f in result.achados}

        self.assertNotIn("SN-011A", codes)

    def test_sn011_dispara_acima_da_maior_referencia(self):
        content = dedent(
            """\
            codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual
            1.1.1;Banco;bancos;0;0;0;0
            1.1.3;Adiantamento a Fornecedores;adiantamentos;0;25000;0;25000
            3.1.1;Receita;receita;0;0;200000;200000
            """
        )
        balance = read_trial_balance_csv_text(content, cliente="SN011 Acima", periodo="2026-T1")
        result = run_quarterly_audit(balance)
        finding = next(f for f in result.achados if f.codigo == "SN-011A")

        self.assertEqual(finding.evidencia["referencia_aplicada"], "R$ 20.000,00")

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

    def test_simples_comercio_triggers_commerce_rules(self):
        content = dedent(
            """\
            codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual
            1.1.1;Banco;bancos;0;100000;90000;10000
            1.1.5;Mercadorias para revenda;estoques;0;0;0;250000
            1.1.8;ICMS a recuperar;creditos_fiscais;0;0;0;10000
            2.1.3;Fornecedores nacionais;fornecedores;0;0;0;180000
            3.1.1;Receita de venda de mercadorias;receita;0;0;100000;100000
            4.1.1;CMV;custos;0;0;0;0
            """
        )
        balance = read_trial_balance_csv_text(content, cliente="Comercio", periodo="2026-T1")
        result = run_quarterly_audit(balance, atividade="comercio")
        payload = audit_result_to_dict(result)
        codes = {f.codigo for f in result.achados}

        self.assertEqual(result.conjunto_regras, "simples_comercio")
        self.assertEqual(payload["metadados"]["conjunto_regras"], "simples_comercio")
        self.assertIn("SN-015C", codes)
        self.assertIn("SN-016C", codes)
        self.assertIn("SN-017", codes)
        self.assertIn("SN-018A", codes)
        self.assertIn("SN-024", codes)
        self.assertIn("SN-COMP-04", codes)
        self.assertNotIn("SN-003", codes)

    def test_simples_comercio_servicos_triggers_revenue_segregation_rule(self):
        content = dedent(
            """\
            codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual
            1.1.1;Banco;bancos;0;150000;120000;30000
            1.1.5;Mercadorias para revenda;estoques;0;0;0;40000
            2.1.3;Fornecedores nacionais;fornecedores;0;0;0;30000
            3.1.1;Receita operacional;receita;0;0;150000;150000
            3.1.2;Simples Nacional;tributos_sobre_receita;0;10000;0;-10000
            4.1.1;Folha;folha;0;20000;0;-20000
            4.2.1;CMV;custos;0;60000;0;-60000
            """
        )
        balance = read_trial_balance_csv_text(content, cliente="Mista", periodo="2026-T1")
        result = run_quarterly_audit(balance, atividade="comercio_servicos")
        payload = audit_result_to_dict(result)
        codes = {f.codigo for f in result.achados}

        self.assertEqual(result.conjunto_regras, "simples_comercio_servicos")
        self.assertEqual(payload["metadados"]["conjunto_regras"], "simples_comercio_servicos")
        self.assertIn("SN-020", codes)
        self.assertIn("SN-020", {achado["codigo"] for achado in payload["principais_achados"]})

    def test_high_profit_margin_triggers_attention_rule(self):
        content = dedent(
            """\
            codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual
            1.1.1;Banco;bancos;0;100000;50000;50000
            3.1.1;Receita de Servicos;receita;0;0;250000;250000
            4.2.1;Despesas Gerais;despesas;0;40000;0;-40000
            """
        )
        balance = read_trial_balance_csv_text(content, cliente="Margem", periodo="2026-T1")
        result = run_quarterly_audit(balance)
        codes = {f.codigo for f in result.achados}

        self.assertIn("SN-021B", codes)

    def test_physical_cash_above_activity_parameter_triggers_rule(self):
        content = dedent(
            """\
            codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual
            1.1.1;Caixa;caixa;0;0;0;15000
            1.1.2;Banco;bancos;0;100000;90000;10000
            3.1.1;Receita de Servicos;receita;0;0;100000;100000
            4.2.1;Despesas Gerais;despesas;0;50000;0;-50000
            """
        )
        balance = read_trial_balance_csv_text(content, cliente="Caixa", periodo="2026-T1")
        result = run_quarterly_audit(balance)
        codes = {f.codigo for f in result.achados}

        self.assertIn("SN-022B", codes)

    def test_zero_receivables_with_relevant_revenue_triggers_attention_rule(self):
        content = dedent(
            """\
            codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual
            1.1.1;Banco;bancos;0;250000;200000;50000
            3.1.1;Receita de Servicos;receita;0;0;250000;250000
            4.2.1;Despesas Gerais;despesas;0;100000;0;-100000
            """
        )
        balance = read_trial_balance_csv_text(content, cliente="Clientes Zerados", periodo="2026-T1")
        result = run_quarterly_audit(balance)
        codes = {f.codigo for f in result.achados}

        self.assertIn("SN-023", codes)

    def test_servicos_terceiros_relevantes_triggers_sn025(self):
        content = dedent(
            """\
            codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual
            1.1.1;Banco;bancos;0;150000;120000;30000
            3.1.1;Receita de Servicos;receita;0;0;200000;200000
            4.2.325;Servicos Prestados por Terceiros;despesas;0;60000;0;-60000
            4.2.1;Despesas Gerais;despesas;0;40000;0;-40000
            """
        )
        balance = read_trial_balance_csv_text(content, cliente="Servicos Terceiros", periodo="2026-T1")
        result = run_quarterly_audit(balance)
        payload = audit_result_to_dict(result)
        finding = next(f for f in result.achados if f.codigo == "SN-025")
        serialized = next(achado for achado in payload["principais_achados"] if achado["codigo"] == "SN-025")

        self.assertEqual(result.metricas_valores["servicos_terceiros"], 60000.0)
        self.assertEqual(finding.evidencia["percentual_sobre_despesas"], "60,00%")
        self.assertEqual(finding.evidencia["quantidade_contas_identificadas"], "1")
        self.assertIn("4.2.325 - Servicos Prestados por Terceiros", finding.evidencia["contas_identificadas"])
        self.assertIn("Validacao documental", serialized["impacto_tecnico"])

    def test_mapa_contabil_classifica_conta_325_com_grupo_custom(self):
        content = dedent(
            """\
            codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual
            1.1.1;Banco;bancos;0;80000;50000;30000
            3.1.1;Receita de Servicos;receita;0;0;100000;100000
            4.2.325;Servicos Prestados por Terceiros;custom;0;25000;0;-25000
            """
        )
        balance = read_trial_balance_csv_text(content, cliente="Mapa Conta 325", periodo="2026-T1")
        account = next(conta for conta in balance.contas if conta.codigo == "4.2.325")
        result = run_quarterly_audit(balance)
        codes = {finding.codigo for finding in result.achados}

        self.assertEqual(account.grupo, "despesas")
        self.assertEqual(result.metricas_valores["despesas_operacionais"], 25000.0)
        self.assertIn("SN-025", codes)


class SchemaV3ResumoTest(unittest.TestCase):
    def test_audit_result_dict_has_summary_schema(self):
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

        self.assertEqual(
            list(payload.keys()),
            [
                "identificacao_empresa",
                "resumo_analise",
                "principais_achados",
                "fundamentacao_tecnica_resumida",
                "conclusao_tecnica",
                "recomendacoes_tecnicas",
                "metadados",
            ],
        )
        self.assertEqual(payload["metadados"]["versao_schema"], "3.0.0")
        self.assertEqual(payload["identificacao_empresa"]["regime_tributario"], "Simples Nacional")
        self.assertIn("total_regras_verificadas", payload["resumo_analise"])
        self.assertIn("total_regras_acionadas", payload["resumo_analise"])
        self.assertNotIn("_schema_version", payload)

    def test_resumo_and_conclusao_have_risk_and_opinion(self):
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
        resumo = payload["resumo_analise"]
        conclusao = payload["conclusao_tecnica"]

        self.assertIn("achados_por_severidade", resumo)
        self.assertIn("conclusao_sugerida", conclusao)
        self.assertIn("alta", resumo["achados_por_severidade"])
        self.assertIn("media", resumo["achados_por_severidade"])
        self.assertIn("baixa", resumo["achados_por_severidade"])
        self.assertTrue(conclusao["ressalva_base_json"])
        self.assertTrue(conclusao["necessita_validacao_documental"])

    def test_principais_achados_have_summary_fields(self):
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
        achado = payload["principais_achados"][0]

        self.assertIn("codigo", achado)
        self.assertIn("severidade", achado)
        self.assertIn("achado", achado)
        self.assertIn("evidencia_identificada", achado)
        self.assertIn("impacto_tecnico", achado)
        self.assertIn("pontuacao", achado)
        self.assertIn("norma_fundamento", achado)

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
        expected_total = len(load_config()["conjuntos_regras"]["simples_servicos"])

        self.assertEqual(payload["resumo_analise"]["total_regras_verificadas"], expected_total)


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
        self.assertEqual(annual["meta"]["trimestres_ausentes"], [])
        self.assertIn("AN-REC-SN-007", codes)
        self.assertEqual(len(annual["comparativo_trimestral"]), 4)

    def test_build_annual_comparison_consolida_metricas_comerciais(self):
        payloads = [
            self._legacy_commerce_quarter("2026-T1", inventory=30000, suppliers=20000, cogs=45000, tax_credits=2000),
            self._legacy_commerce_quarter("2026-T2", inventory=40000, suppliers=30000, cogs=50000, tax_credits=2500),
            self._legacy_commerce_quarter("2026-T3", inventory=45000, suppliers=35000, cogs=52000, tax_credits=3000),
            self._legacy_commerce_quarter("2026-T4", inventory=50000, suppliers=40000, cogs=55000, tax_credits=3500),
        ]

        annual = build_annual_comparison(payloads)

        self.assertEqual(annual["metricas_anual"]["estoques_final"]["valor"], 50000.0)
        self.assertEqual(annual["metricas_anual"]["fornecedores_final"]["valor"], 40000.0)
        self.assertEqual(annual["metricas_anual"]["cmv_custos_total"]["valor"], 202000.0)
        self.assertEqual(annual["metricas_anual"]["creditos_fiscais_final"]["valor"], 3500.0)
        self.assertIn("cmv_sobre_receita_anual", annual["metricas_anual"]["indicadores_derivados"])

    def test_build_annual_comparison_expoe_rbt12_consolidado(self):
        payloads = [
            self._legacy_commerce_quarter("2026-T1", inventory=30000, suppliers=20000, cogs=45000, tax_credits=2000),
            self._legacy_commerce_quarter("2026-T2", inventory=40000, suppliers=30000, cogs=50000, tax_credits=2500),
            self._legacy_commerce_quarter("2026-T3", inventory=45000, suppliers=35000, cogs=52000, tax_credits=3000),
            self._legacy_commerce_quarter("2026-T4", inventory=50000, suppliers=40000, cogs=55000, tax_credits=3500),
        ]

        annual = build_annual_comparison(payloads)

        self.assertEqual(annual["metricas_anual"]["rbt12_receita"]["valor"], 400000.0)
        self.assertTrue(annual["metricas_anual"]["contexto_rbt12"]["dados_suficientes"])
        self.assertEqual(annual["metricas_anual"]["contexto_rbt12"]["trimestres_considerados"], ["T1", "T2", "T3", "T4"])
        self.assertIn("recorrencia_por_severidade", annual["resumo_evolucao"])

    def test_build_annual_comparison_identifica_tendencia_de_piora(self):
        payloads = [
            self._legacy_quarter_with_risk("2026-T1", "baixo", 5),
            self._legacy_quarter_with_risk("2026-T2", "baixo", 5),
            self._legacy_quarter_with_risk("2026-T3", "medio", 20),
            self._legacy_quarter_with_risk("2026-T4", "alto", 50),
        ]

        annual = build_annual_comparison(payloads)
        codes = {finding["codigo"] for finding in annual["achados_anuais"]}

        self.assertIn("AN-TEND-RIS-001", codes)
        self.assertEqual(annual["resumo_evolucao"]["tendencia_risco"], "piora")

    def test_build_annual_comparison_identifica_servicos_terceiros_relevantes(self):
        payloads = [
            self._legacy_commerce_quarter("2026-T1", inventory=10000, suppliers=5000, cogs=40000, tax_credits=0, third_party_services=12000),
            self._legacy_commerce_quarter("2026-T2", inventory=10000, suppliers=5000, cogs=40000, tax_credits=0, third_party_services=13000),
            self._legacy_commerce_quarter("2026-T3", inventory=10000, suppliers=5000, cogs=40000, tax_credits=0, third_party_services=14000),
            self._legacy_commerce_quarter("2026-T4", inventory=10000, suppliers=5000, cogs=40000, tax_credits=0, third_party_services=15000),
        ]

        annual = build_annual_comparison(payloads)
        codes = {finding["codigo"] for finding in annual["achados_anuais"]}

        self.assertEqual(annual["metricas_anual"]["servicos_terceiros_total"]["valor"], 54000.0)
        self.assertIn("AN-DOC-325-001", codes)

    def test_generate_annual_markdown_report(self):
        payloads = [
            self._quarter_payload("2026-T1", revenue=100000, expenses=80000),
            self._quarter_payload("2026-T2", revenue=100000, expenses=85000),
            self._quarter_payload("2026-T3", revenue=100000, expenses=10000),
            self._quarter_payload("2026-T4", revenue=100000, expenses=15000),
        ]
        annual = build_annual_comparison(payloads)

        report = generate_annual_markdown_report(annual)

        self.assertIn("Parecer técnico contábil consultivo anual comparativo", report)
        self.assertIn("## 2. Comparativo trimestral", report)
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

    def _legacy_commerce_quarter(
        self,
        periodo: str,
        inventory: int,
        suppliers: int,
        cogs: int,
        tax_credits: int,
        third_party_services: int = 0,
    ) -> dict:
        return {
            "identificacao": {
                "cliente": "Comercio Anual",
                "cnpj": "12.345.678/0001-90",
                "regime_tributario": "Simples Nacional",
                "periodo": periodo,
            },
            "risco": {
                "nivel_geral": "baixo",
                "pontuacao_total": 0,
                "modalidade_opiniao_sugerida": "sem_ressalva",
            },
            "metricas": {
                "receita_servicos": {"valor": 100000, "formatado": "R$ 100.000,00"},
                "deducoes_receita": {"valor": 0, "formatado": "R$ 0,00"},
                "tributos_registrados": {"valor": 6000, "formatado": "R$ 6.000,00"},
                "tributos_a_recolher": {"valor": 2000, "formatado": "R$ 2.000,00"},
                "folha_pro_labore": {"valor": 0, "formatado": "R$ 0,00"},
                "despesas_operacionais": {"valor": 20000, "formatado": "R$ 20.000,00"},
                "servicos_terceiros": {"valor": third_party_services, "formatado": "R$ 0,00"},
                "lucros_distribuidos": {"valor": 0, "formatado": "R$ 0,00"},
                "lucro_apurado_base": {"valor": 30000, "formatado": "R$ 30.000,00"},
                "caixa_e_bancos": {"valor": 10000, "formatado": "R$ 10.000,00"},
                "clientes_recebiveis": {"valor": 5000, "formatado": "R$ 5.000,00"},
                "adiantamentos": {"valor": 0, "formatado": "R$ 0,00"},
                "emprestimos": {"valor": 0, "formatado": "R$ 0,00"},
                "fornecedores": {"valor": suppliers, "formatado": "R$ 0,00"},
                "estoques": {"valor": inventory, "formatado": "R$ 0,00"},
                "cmv_custos": {"valor": cogs, "formatado": "R$ 0,00"},
                "creditos_fiscais": {"valor": tax_credits, "formatado": "R$ 0,00"},
            },
            "achados": [],
        }

    def _legacy_quarter_with_risk(self, periodo: str, risk: str, score: int) -> dict:
        payload = self._legacy_commerce_quarter(periodo, inventory=10000, suppliers=5000, cogs=40000, tax_credits=0)
        payload["risco"]["nivel_geral"] = risk
        payload["risco"]["pontuacao_total"] = score
        payload["achados"] = [
            {
                "codigo": "SN-007",
                "titulo": "Despesas operacionais elevadas",
                "nivel": "medio",
                "pontuacao": 16,
                "descricao": "Teste",
                "evidencia": {},
                "recomendacao": "Teste",
                "normas_aplicaveis": [],
            }
        ]
        return payload


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
