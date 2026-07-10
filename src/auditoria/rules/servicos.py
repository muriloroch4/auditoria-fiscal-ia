from __future__ import annotations

from decimal import Decimal

from ..config_loader import get_rule_config
from ..models import RiskLevel, RuleFinding
from ..utils import format_brl, format_percent
from .rulesets import RULESET_SERVICOS


def check_payroll_factor(revenue: Decimal, payroll: Decimal, ruleset: str = RULESET_SERVICOS) -> list[RuleFinding]:
    if revenue <= 0:
        return []

    cfg = get_rule_config("SN-003")
    lim = Decimal(str(cfg.get("limite_medio", 0.08)))
    factor = payroll / revenue
    title_activity = "empresa de serviços" if ruleset == RULESET_SERVICOS else "atividade de serviços em empresa mista"
    if factor < lim:
        return [
            RuleFinding(
                codigo="SN-003",
                titulo=f"Folha e pró-labore trimestrais baixos para {title_activity}",
                nivel=RiskLevel.MEDIO,
                pontuacao=cfg.get("pontuacao_medio", 14),
                descricao="A folha e o pró-labore do trimestre representam percentual baixo da receita trimestral, funcionando como indicador preliminar para validação do Fator R.",
                evidencia={
                    "receita_trimestre": format_brl(revenue),
                    "folha_pro_labore_trimestre": format_brl(payroll),
                    "fator_r_trimestral_estimado": format_percent(factor),
                },
                recomendacao="Revisar folha, pró-labore dos sócios e apuração do Fator R com base acumulada de 12 meses antes de concluir sobre o anexo aplicável.",
                normas_aplicaveis=("LC 123/2006", "art. 18° LC 123/2006"),
            )
        ]

    return []
