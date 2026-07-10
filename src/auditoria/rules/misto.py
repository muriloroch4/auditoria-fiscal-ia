from __future__ import annotations

from decimal import Decimal

from ..config_loader import get_rule_config
from ..models import RiskLevel, RuleFinding, TrialBalance
from ..utils import format_brl, format_percent
from .metricas import revenue_by_nature


def check_mixed_revenue_segregation(
    balance: TrialBalance,
    revenue: Decimal,
    payroll: Decimal,
    inventory: Decimal,
    suppliers: Decimal,
) -> list[RuleFinding]:
    if revenue <= 0:
        return []

    commerce_signal = inventory > 0 or suppliers > 0
    service_signal = payroll > 0 or revenue_by_nature(balance, "servicos") > 0
    if not commerce_signal or not service_signal:
        return []

    service_revenue = revenue_by_nature(balance, "servicos")
    commerce_revenue = revenue_by_nature(balance, "comercio")
    identified_revenue = service_revenue + commerce_revenue

    cfg = get_rule_config("SN-020")
    tolerance = Decimal(str(cfg.get("tolerancia_receita_nao_segregada", 0.20)))
    missing_split = service_revenue <= 0 or commerce_revenue <= 0
    unsegregated_ratio = (revenue - identified_revenue) / revenue if revenue > identified_revenue else Decimal("0")

    if not missing_split and unsegregated_ratio <= tolerance:
        return []

    return [
        RuleFinding(
            codigo="SN-020",
            titulo="Receitas de comercio e servicos sem segregacao suficiente",
            nivel=RiskLevel.MEDIO,
            pontuacao=cfg.get("pontuacao_medio", 18),
            descricao="A empresa apresenta sinais de atividade comercial e de servicos, mas a receita contabil nao esta suficientemente segregada por natureza.",
            evidencia={
                "receita_total": format_brl(revenue),
                "receita_comercio_identificada": format_brl(commerce_revenue),
                "receita_servicos_identificada": format_brl(service_revenue),
                "receita_nao_segregada_estimativa": format_percent(unsegregated_ratio),
                "estoques": format_brl(inventory),
                "fornecedores": format_brl(suppliers),
                "folha_pro_labore": format_brl(payroll),
            },
            recomendacao="Segregar receitas de comercio e servicos por conta contabil e documento fiscal, validando anexos, fator R, ISS/ICMS e calculo do DAS.",
            normas_aplicaveis=("LC 123/2006", "Anexos I e III/V da LC 123/2006", "ITG 2000"),
        )
    ]
