from __future__ import annotations

import unittest
from unittest.mock import patch

from src.auditoria import report_consultivo_helpers as helpers


class ReportConsultivoHelpersTest(unittest.TestCase):
    def test_client_safe_text_softens_accusatory_terms(self):
        text = helpers._client_safe_text(
            "Possível sinal de sonegação fiscal, omissão de receita e fraude documental."
        )

        self.assertIn("Risco de receita não reconhecida", text)
        self.assertIn("receita possivelmente não reconhecida", text)
        self.assertIn("irregularidade documental", text)
        self.assertNotIn("sonegação fiscal", text.lower())
        self.assertNotIn("fraude", text.lower())

    def test_conclusion_guidance_maps_formal_opinion_to_consultive_action(self):
        cases = [
            ("adversa", "regularizar os achados relevantes"),
            ("com ressalva", "corrigir, documentar e validar"),
            ("abstenção de opinião", "obter documentação complementar"),
            ("não modificada", "manter a documentação suporte"),
        ]

        for value, expected in cases:
            with self.subTest(value=value):
                self.assertIn(expected, helpers._orientacao_consultiva_de_conclusao(value))

    def test_recommendation_for_finding_prefers_matching_code_then_position_then_impact(self):
        recommendations = [
            {"descricao": "Validar SN-010 com relatório de clientes."},
            {"descricao": "Revisar documentos fiscais."},
        ]

        self.assertEqual(
            helpers._recommendation_for_finding(recommendations, {"codigo": "SN-010"}, 1),
            "Validar SN-010 com relatório de clientes.",
        )
        self.assertEqual(
            helpers._recommendation_for_finding(recommendations, {"codigo": "SN-999"}, 1),
            "Revisar documentos fiscais.",
        )
        self.assertEqual(
            helpers._recommendation_for_finding([], {"codigo": "SN-999", "impacto_tecnico": "Conciliar saldo."}, 0),
            "Conciliar saldo.",
        )

    def test_configured_consultive_entries_are_used_when_available(self):
        achado = {"codigo": "SN-005", "impacto_tecnico": "impacto alternativo"}

        self.assertIn("Saldos com socios", helpers._consultative_meaning(achado))
        self.assertIn("Conferir razao", helpers._consultative_solution(achado, "fallback"))
        self.assertIn("contrato de mutuo", ", ".join(helpers._documents_for_finding(achado)))
        self.assertIn("socios/administradores", helpers._suggested_owner(achado))

    def test_fallback_meanings_are_specific_by_rule_family(self):
        empty_consultive = {"matched": False}
        cases = [
            ("SN-004X", "lastro contábil"),
            ("SN-005X", "Saldos com sócios"),
            ("SN-006X", "saldo de caixa ou bancos"),
            ("SN-008X", "movimentação financeira"),
            ("SN-010X", "recebíveis"),
            ("SN-015X", "Estoque"),
            ("SN-025X", "Serviços de terceiros"),
            ("SN-026X", "Adiantamentos de clientes"),
        ]

        with patch.object(helpers, "consultivo_for_code", return_value=empty_consultive):
            for code, expected in cases:
                with self.subTest(code=code):
                    text = helpers._consultative_meaning({"codigo": code})
                    self.assertIn(expected, text)

            default_text = helpers._consultative_meaning(
                {"codigo": "SN-999", "impacto_tecnico": "possível sinal de sonegação fiscal"}
            )
            self.assertIn("risco de receita não reconhecida", default_text)

    def test_fallback_solutions_are_specific_by_rule_family(self):
        empty_consultive = {"matched": False}
        cases = [
            ("SN-004X", "Reconciliar resultado"),
            ("SN-005X", "formalizar contrato de mútuo"),
            ("SN-006X", "Conciliar extratos"),
            ("SN-008X", "Comparar notas fiscais"),
            ("SN-010X", "Validar relatório de clientes"),
            ("SN-015X", "Confrontar inventário"),
            ("SN-025X", "Conferir a conta 325"),
            ("SN-026X", "Validar contrato"),
        ]

        with patch.object(helpers, "consultivo_for_code", return_value=empty_consultive):
            for code, expected in cases:
                with self.subTest(code=code):
                    text = helpers._consultative_solution({"codigo": code}, "recomendação fallback")
                    self.assertIn(expected, text)

            default_text = helpers._consultative_solution({"codigo": "SN-999"}, "validar possível fraude")
            self.assertIn("validar possível irregularidade", default_text)

    def test_documents_fallback_prefers_evidence_then_rule_specific_then_generic(self):
        with patch.object(helpers, "consultivo_for_code", return_value={"matched": False}):
            self.assertEqual(
                helpers._documents_for_finding({"codigo": "SN-999", "evidencia": {"documentos_recomendados": ["extrato"]}}),
                ["extrato"],
            )
            self.assertIn("DRE", helpers._documents_for_finding({"codigo": "SN-004X"}))
            self.assertIn("contrato de mútuo", ", ".join(helpers._documents_for_finding({"codigo": "SN-005X"})))
            self.assertIn("razão da conta 325", helpers._documents_for_finding({"codigo": "SN-025X"}))
            self.assertIn("baixas posteriores", ", ".join(helpers._documents_for_finding({"codigo": "SN-026X"})))
            self.assertIn("documentos fiscais", helpers._documents_for_finding({"codigo": "SN-999"}))

    def test_suggested_owner_and_labels_have_consultive_defaults(self):
        with patch.object(helpers, "consultivo_for_code", return_value={"matched": False}):
            self.assertEqual(helpers._suggested_owner({"codigo": "SN-003X"}), "Departamento pessoal + contabilidade")
            self.assertEqual(helpers._suggested_owner({"codigo": "SN-004X"}), "Sócios/administradores + contabilidade")
            self.assertEqual(helpers._suggested_owner({"codigo": "SN-001X"}), "Fiscal + contabilidade")
            self.assertEqual(helpers._suggested_owner({"codigo": "SN-015X"}), "Cliente/estoque/financeiro + contabilidade")
            self.assertEqual(helpers._suggested_owner({"codigo": "SN-999"}), "Cliente + contabilidade")

        self.assertEqual(helpers._level_label("medio"), "Médio")
        self.assertEqual(helpers._level_label("alta"), "Alta")
        self.assertEqual(helpers._escape_table("linha | com\nquebra"), "linha \\| com quebra")


if __name__ == "__main__":
    unittest.main()
