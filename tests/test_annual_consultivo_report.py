from __future__ import annotations

import unittest
import unittest.mock

from src.auditoria import annual_consultivo
from src.auditoria.annual_report import (
    _render_annual_action_plan,
    _render_annual_client_guidance,
    _render_annual_findings,
    _render_annual_opinion,
    _risk_label,
    generate_annual_markdown_report,
)


def _finding(code: str, level: str = "medio", title: str | None = None) -> dict:
    return {
        "codigo": code,
        "titulo": title or f"Achado {code}",
        "nivel": level,
        "pontuacao": 12,
        "descricao": f"Descricao {code}",
        "recomendacao": f"Recomendacao {code}",
        "evidencia": {
            "campos_extraidos": {"valor": "R$ 1.000,00"},
            "fonte_dado": "json_trimestral",
            "confianca": "alta",
            "documentos_recomendados": ["razao contabil"],
        },
    }


def _annual_payload(findings: list[dict] | None = None, consultivo: dict | None = None) -> dict:
    findings = findings if findings is not None else [_finding("AN-REC-SN-007")]
    return {
        "identificacao": {
            "cliente": "Cliente Anual",
            "cnpj": "12.345.678/0001-90",
            "regime_tributario": "Simples Nacional",
            "exercicio": "2026",
        },
        "risco_anual": {
            "nivel_geral": "medio",
            "pontuacao_total": 42,
            "modalidade_opiniao_sugerida": "com_ressalva",
        },
        "metricas_anual": {
            "receita_servicos_total": {"valor": 400000, "formatado": "R$ 400.000,00"},
            "deducoes_receita_total": {"valor": 10000, "formatado": "R$ 10.000,00"},
            "tributos_registrados_total": {"valor": 24000, "formatado": "R$ 24.000,00"},
            "despesas_operacionais_total": {"valor": 160000, "formatado": "R$ 160.000,00"},
            "servicos_terceiros_total": {"valor": 25000, "formatado": "R$ 25.000,00"},
            "saldo_contas_socios_final": {"valor": 0, "formatado": "R$ 0,00"},
            "cmv_custos_total": {"valor": 90000, "formatado": "R$ 90.000,00"},
            "estoques_final": {"valor": 30000, "formatado": "R$ 30.000,00"},
            "fornecedores_final": {"valor": 15000, "formatado": "R$ 15.000,00"},
            "creditos_fiscais_final": {"valor": 1000, "formatado": "R$ 1.000,00"},
            "rbt12_receita": {"valor": 400000, "formatado": "R$ 400.000,00"},
            "contexto_rbt12": {"base_calculo": "RBT12 consolidado"},
            "adiantamentos_clientes_final": {"valor": 0, "formatado": "R$ 0,00"},
            "lucro_apurado_total": {"valor": 140000, "formatado": "R$ 140.000,00"},
            "indicadores_derivados": {
                "carga_tributaria_efetiva_anual": "6,00%",
                "despesas_sobre_receita_anual": "40,00%",
                "servicos_terceiros_sobre_despesas_anual": "15,62%",
                "cmv_sobre_receita_anual": "22,50%",
            },
        },
        "achados_anuais": findings,
        "resumo_evolucao": {
            "tendencia_risco": "estavel",
            "achados_recorrentes": [{"codigo": "SN-007", "trimestres": 3}],
            "melhor_trimestre_resultado": "T4",
            "pior_trimestre_resultado": "T1",
        },
        "comparativo_trimestral": [
            {
                "trimestre": "T1",
                "periodo": "2026-T1",
                "risco": "medio",
                "achados_codigos": ["SN-007"],
                "metricas": {"receita_servicos": 100000, "lucro_apurado_base": 20000},
            }
        ],
        "meta": {"data_analise": "2026-12-31T10:00:00", "total_trimestres_informados": 1},
        "consultivo": consultivo or {},
    }


class AnnualConsultivoHelpersTest(unittest.TestCase):
    def test_build_annual_consultivo_combines_reading_steps_and_action_plan(self):
        risk = {"nivel_geral": "alto"}
        totals = {
            "receita_servicos_total": {"formatado": "R$ 400.000,00"},
            "lucro_apurado_total": {"formatado": "R$ 120.000,00"},
        }
        quarters = [{"trimestre": "T1"}, {"trimestre": "T2"}]
        findings = [_finding("AN-LUC-001", "alto")]
        evolution = {
            "tendencia_risco": "piora",
            "achados_recorrentes": [{"codigo": "SN-004A", "trimestres": 2}],
        }

        consultivo = annual_consultivo.build_annual_consultivo(risk, totals, quarters, findings, evolution)

        self.assertIn("leitura_cliente", consultivo)
        self.assertIn("priorizar", consultivo["proximos_passos"][0])
        self.assertTrue(any("trimestres ausentes" in step for step in consultivo["proximos_passos"]))
        self.assertEqual(consultivo["plano_acao_anual"][0]["codigo"], "AN-LUC-001")
        self.assertEqual(consultivo["plano_acao_anual"][0]["prioridade"], "alta")

    def test_annual_labels_deadlines_and_orientation_cover_all_branches(self):
        self.assertEqual(annual_consultivo.annual_priority_label("alto"), "alta")
        self.assertEqual(annual_consultivo.annual_priority_label("medio"), "media")
        self.assertEqual(annual_consultivo.annual_priority_label("baixo"), "baixa")
        self.assertEqual(annual_consultivo.annual_priority_label("desconhecido"), "media")

        self.assertIn("imediato", annual_consultivo.annual_deadline("alto"))
        self.assertIn("trimestral", annual_consultivo.annual_deadline("medio"))
        self.assertIn("ciclo anual", annual_consultivo.annual_deadline("baixo"))

        for value in ("sem_ressalva", "com_ressalva", "adversa", "abstencao_opiniao"):
            self.assertNotIn("_", annual_consultivo.annual_orientation(value))
        self.assertEqual(annual_consultivo.annual_orientation("analise_manual"), "analise manual")

    def test_annual_meaning_documents_and_owner_cover_rule_families(self):
        evolution = {"tendencia_risco": "piora"}
        cases = [
            ("AN-REC-SN-007", "trimestre", "JSONs trimestrais", "Cliente + contabilidade"),
            ("AN-SN-001A", "Simples Nacional", "JSONs trimestrais", "Fiscal + contabilidade"),
            ("AN-LUC-001", "lucros", "DRE", "administradores"),
            ("AN-MAR-001", "margem", "JSONs trimestrais", "Cliente + contabilidade"),
            ("AN-DOC-MUTUO-001", "IOF", "contrato", "administradores"),
            ("AN-COM-001", "estoque", "invent", "Cliente/estoque"),
            ("AN-TRIB-001", "DAS", "PGDAS-D", "Fiscal + contabilidade"),
            ("AN-TEND-RIS-001", "piora", "JSONs trimestrais", "Cliente + contabilidade"),
            ("AN-OUTRO-001", "Descricao", "JSONs trimestrais", "Cliente + contabilidade"),
        ]

        with unittest.mock.patch(
            "src.auditoria.annual_consultivo.consultivo_for_code",
            return_value={"matched": False},
        ):
            for code, meaning_token, doc_token, owner_token in cases:
                with self.subTest(code=code):
                    finding = _finding(code)
                    self.assertIn(meaning_token, annual_consultivo.annual_meaning(finding, evolution))
                    docs = annual_consultivo.annual_documents_for_finding({"codigo": code, "nivel": "medio", "evidencia": {}})
                    self.assertTrue(any(doc_token in doc for doc in docs))
                    self.assertIn(owner_token, annual_consultivo.annual_owner({"codigo": code}))

    def test_annual_documents_prefer_evidence_then_consultive_mapping(self):
        self.assertEqual(
            annual_consultivo.annual_documents_for_finding(
                {"codigo": "AN-X", "nivel": "baixo", "evidencia": {"documentos_recomendados": ["doc direto"]}}
            ),
            ["doc direto"],
        )

        with unittest.mock.patch(
            "src.auditoria.annual_consultivo.consultivo_for_code",
            return_value={"matched": True, "documentos_necessarios": ["doc consultivo"]},
        ):
            self.assertEqual(
                annual_consultivo.annual_documents_for_finding({"codigo": "SN-005", "nivel": "alto", "evidencia": {}}),
                ["doc consultivo"],
            )

    def test_annual_item_uses_consultive_mapping_when_available(self):
        finding = _finding("SN-005", "alto")
        finding["evidencia"] = {}
        with unittest.mock.patch(
            "src.auditoria.annual_consultivo.consultivo_for_code",
            return_value={
                "matched": True,
                "o_que_significa": "significado configurado",
                "como_solucionar": "solucao configurada",
                "responsavel_sugerido": "Fiscal",
                "prazo_sugerido": "imediato",
                "documentos_necessarios": ["contrato"],
            },
        ):
            item = annual_consultivo._annual_consultivo_item(finding, {"tendencia_risco": "estavel"})

        self.assertEqual(item["o_que_significa"], "significado configurado")
        self.assertEqual(item["como_solucionar"], "solucao configurada")
        self.assertEqual(item["responsavel_sugerido"], "Fiscal")
        self.assertEqual(item["prazo_sugerido"], "imediato")
        self.assertEqual(item["documentos_necessarios"], ["contrato"])


class AnnualReportRendererTest(unittest.TestCase):
    def test_generate_annual_report_renders_fallback_sections(self):
        report = generate_annual_markdown_report(_annual_payload())

        self.assertIn("Cliente Anual", report)
        self.assertIn("42/100", report)
        self.assertIn("AN-REC-SN-007", report)
        self.assertIn("## 4.", report)
        self.assertIn("T1", report)

    def test_client_guidance_uses_consultivo_with_and_without_steps(self):
        with_steps = _annual_payload(
            consultivo={"leitura_cliente": "Leitura pronta", "proximos_passos": ["Passo 1", "Passo 2"]}
        )
        self.assertIn("Passo 1", _render_annual_client_guidance(with_steps))

        without_steps = _annual_payload(consultivo={"leitura_cliente": "Somente leitura"})
        self.assertEqual(_render_annual_client_guidance(without_steps), "Somente leitura")

    def test_action_plan_uses_consultivo_plan_and_empty_fallback(self):
        payload = _annual_payload(
            consultivo={
                "plano_acao_anual": [
                    {
                        "codigo": "AN-001",
                        "ponto_atencao": "Ponto",
                        "prioridade": "alta",
                        "o_que_significa": "Significado",
                        "como_solucionar": "Solucao",
                        "documentos_necessarios": ["Doc"],
                        "responsavel_sugerido": "Contabilidade",
                        "prazo_sugerido": "Curto prazo",
                    }
                ]
            }
        )
        self.assertIn("AN-001", _render_annual_action_plan(payload))

        empty = _annual_payload(findings=[])
        self.assertIn("Nenhuma", _render_annual_action_plan(empty))
        self.assertIn("Nenhum achado", _render_annual_findings([]))
        self.assertIn("nenhum achado", _render_annual_opinion(empty).lower())

    def test_annual_findings_fallbacks_for_missing_evidence_fields(self):
        finding = _finding("AN-X")
        finding["evidencia"] = {}

        rendered = _render_annual_findings([finding])

        self.assertIn("[VERIFICAR: fonte]", rendered)
        self.assertIn("[VERIFICAR: documentos recomendados]", rendered)

    def test_risk_label_handles_known_and_unknown_values(self):
        self.assertEqual(_risk_label("alto"), "Alto")
        self.assertEqual(_risk_label("baixo"), "Baixo")
        self.assertEqual(_risk_label("critico"), "Critico")


if __name__ == "__main__":
    unittest.main()
