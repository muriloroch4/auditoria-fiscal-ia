from __future__ import annotations

from ..config_loader import get_rule_config
from ..models import RiskLevel, RuleFinding


def apply_compound_rules(findings: list[RuleFinding]) -> list[RuleFinding]:
    compound: list[RuleFinding] = []
    codes = {finding.codigo for finding in findings}

    if any(code.startswith("SN-008") for code in codes) and "SN-007" in codes:
        cfg = get_rule_config("SN-COMP-01")
        compound.append(
            RuleFinding(
                codigo="SN-COMP-01",
                titulo="Omissão de receita combinada com despesas operacionais elevadas",
                nivel=RiskLevel.ALTO,
                pontuacao=cfg.get("pontuacao", 15),
                descricao="A empresa apresenta indicadores de omissão de receita (SN-008) e despesas operacionais elevadas (SN-007), sugerindo possível operação informal.",
                evidencia={},
                recomendacao="Realizar cruzamento entre entradas financeiras, notas fiscais emitidas e despesas contabilizadas para identificar divergências.",
                normas_aplicaveis=("LC 123/2006", "NBC TG 1000"),
            )
        )

    if "SN-009B" in codes and "SN-006A" in codes:
        cfg = get_rule_config("SN-COMP-02")
        compound.append(
            RuleFinding(
                codigo="SN-COMP-02",
                titulo="Prejuízo contábil significativo com saldo financeiro negativo",
                nivel=RiskLevel.ALTO,
                pontuacao=cfg.get("pontuacao", 15),
                descricao="A combinação de prejuízo contábil significativo (SN-009) com saldo de caixa/bancos negativo (SN-006) indica grave desequilíbrio financeiro.",
                evidencia={},
                recomendacao="Avaliar urgente a necessidade de aporte de capital, renegociação de passivos e revisão do modelo de negócio.",
                normas_aplicaveis=("NBC TG 1000", "ITG 2000"),
            )
        )

    if ("SN-010B" in codes or "SN-010C" in codes) and "SN-011A" in codes:
        cfg = get_rule_config("SN-COMP-03")
        compound.append(
            RuleFinding(
                codigo="SN-COMP-03",
                titulo="Concentração de recebíveis e adiantamentos sem contrapartida",
                nivel=RiskLevel.MEDIO,
                pontuacao=cfg.get("pontuacao", 10),
                descricao="A empresa apresenta simultaneamente saldos elevados em clientes/recebíveis (SN-010) e adiantamentos (SN-011), exigindo validação da liquidez e realização dos créditos.",
                evidencia={},
                recomendacao="Conciliar posições de recebíveis e adiantamentos com contratos, notas fiscais e projeção de fluxo de caixa.",
                normas_aplicaveis=("NBC TG 1000", "ITG 2000"),
            )
        )

    if any(code.startswith("SN-015") for code in codes) and any(code.startswith("SN-018") for code in codes):
        cfg = get_rule_config("SN-COMP-04")
        compound.append(
            RuleFinding(
                codigo="SN-COMP-04",
                titulo="Estoque incompatível combinado com inconsistência de CMV",
                nivel=RiskLevel.ALTO,
                pontuacao=cfg.get("pontuacao", 15),
                descricao="A empresa apresenta simultaneamente estoque relevante/incompatível e inconsistência no custo de mercadorias, aumentando o risco de distorção no resultado.",
                evidencia={},
                recomendacao="Reconciliar inventário, compras, notas fiscais de saída, devoluções, perdas e baixas de estoque antes do fechamento trimestral.",
                normas_aplicaveis=("CPC 16 R1", "NBC TG 1000", "ITG 2000"),
            )
        )

    if "SN-020" in codes and any(code.startswith("SN-002") for code in codes):
        cfg = get_rule_config("SN-COMP-05")
        compound.append(
            RuleFinding(
                codigo="SN-COMP-05",
                titulo="Receita mista sem segregação combinada com carga tributária baixa",
                nivel=RiskLevel.ALTO,
                pontuacao=cfg.get("pontuacao", 15),
                descricao="A ausência de segregação suficiente entre comércio e serviços aparece junto de carga tributária baixa, elevando o risco de anexo ou apuração incorreta.",
                evidencia={},
                recomendacao="Reprocessar a apuração do DAS com receitas segregadas por natureza, validando anexos, Fator R, ISS, ICMS e eventuais sublimites.",
                normas_aplicaveis=("LC 123/2006", "Anexos I e III/V da LC 123/2006"),
            )
        )

    return compound
