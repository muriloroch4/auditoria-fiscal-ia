from __future__ import annotations

from decimal import Decimal

from ..config_loader import get_rule_config
from ..models import LedgerAccount, RiskLevel, RuleFinding
from ..utils import format_brl, format_percent
from .metricas import ProfitBasis, format_account_trace

_money = format_brl
_percent = format_percent


def check_profit_distribution(
    revenue: Decimal,
    profit_distribution: Decimal,
    profit_basis: ProfitBasis,
    profit_distribution_capacity: Decimal,
) -> list[RuleFinding]:
    cfg = get_rule_config("SN-004")
    available_profit = max(profit_basis.value, profit_distribution_capacity, Decimal("0"))

    if profit_distribution > available_profit and profit_distribution > 0:
        return [
            RuleFinding(
                codigo="SN-004A",
                titulo="Distribuição de lucros acima do lucro disponível identificado",
                nivel=RiskLevel.ALTO,
                pontuacao=cfg.get("pontuacao_alto", 32),
                descricao="A distribuição de lucros supera o lucro do período e os saldos de lucros/reservas identificados no balancete trimestral.",
                evidencia={
                    "lucro_apurado": _money(profit_basis.value),
                    "origem_lucro": profit_basis.source,
                    "lucro_disponivel_identificado": _money(available_profit),
                    "lucros_distribuidos": _money(profit_distribution),
                },
                recomendacao="Validar escrituração completa, lucros acumulados, reservas, resultado do período e documentação societária antes de manter distribuição isenta.",
                normas_aplicaveis=("art. 14° LC 123/2006", "NBC TG 1000"),
            )
        ]

    if revenue > 0:
        lim_medio = Decimal(str(cfg.get("limite_medio_ratio", 0.30)))
        if profit_distribution / revenue > lim_medio:
            return [
                RuleFinding(
                    codigo="SN-004B",
                    titulo="Distribuição de lucros acima de 30% da receita",
                    nivel=RiskLevel.MEDIO,
                    pontuacao=cfg.get("pontuacao_medio", 16),
                    descricao="A distribuição de lucros representa parcela relevante da receita do trimestre.",
                    evidencia={"receita_trimestre": _money(revenue), "lucros_distribuidos": _money(profit_distribution), "percentual": _percent(profit_distribution / revenue)},
                    recomendacao="Conferir se há balancete regular, lucro contábil suficiente no período ou lucros acumulados que suportem a distribuição.",
                    normas_aplicaveis=("art. 14° LC 123/2006", "NBC TG 1000"),
                )
            ]

    return []

def check_partner_accounts(revenue: Decimal, partners: Decimal, accounts: list[LedgerAccount]) -> list[RuleFinding]:
    if partners <= 0 or not accounts:
        return []

    cfg = get_rule_config("SN-005")
    lim_ratio = Decimal(str(cfg.get("limite_medio_receita", cfg.get("limite_medio", 0.20))))
    lim_abs = Decimal(str(cfg.get("limite_medio_absoluto", 10000)))
    lim_baixo_abs = Decimal(str(cfg.get("limite_baixo_absoluto", 1000)))
    ratio = partners / revenue if revenue > 0 else None
    material = partners >= lim_abs or (ratio is not None and ratio >= lim_ratio)
    level = RiskLevel.MEDIO if material else RiskLevel.BAIXO
    score = cfg.get("pontuacao_medio", 18) if material else cfg.get("pontuacao_baixo", 6)
    evidence = {
        "receita": _money(revenue),
        "saldo_contas_socios": _money(partners),
        "percentual_receita": _percent(ratio) if ratio is not None else "[VERIFICAR: receita do trimestre]",
        "limite_percentual_relevancia": _percent(lim_ratio),
        "limite_absoluto_relevancia": _money(lim_abs),
        "limite_baixa_materialidade": _money(lim_baixo_abs),
        "classificacao_materialidade": "material" if material else "baixa_materialidade",
        "quantidade_contas_identificadas": str(len(accounts)),
        "contas_identificadas": format_account_trace(accounts),
        "codigos_monitorados": "616 e 627 no ativo; 770 no passivo; demais contas com socio, administrador, pessoa ligada ou mutuo na descricao",
        "contrato_mutuo": "[VERIFICAR: existência, valor, prazo, juros, partes e assinatura do contrato de mútuo ou instrumento equivalente]",
        "iof_recolhido": "[VERIFICAR: cálculo, guia e comprovante de recolhimento do IOF quando a operação caracterizar mútuo/crédito]",
        "criterio_rastreio": "saldo final em contas de socios ou codigos 616/627/770",
        "tipo_achado": "validacao_documental",
    }

    return [
        RuleFinding(
            codigo="SN-005",
            titulo="Saldos em contas de socios exigem validacao de mutuo e IOF",
            nivel=level,
            pontuacao=score,
            descricao=(
                "Foram identificados saldos materiais em contas relacionadas a socios, administradores, pessoas ligadas ou codigos monitorados de mutuo, exigindo validacao documental da natureza da operacao."
                if material
                else "Foram identificados saldos de baixa materialidade em contas relacionadas a socios, administradores, pessoas ligadas ou codigos monitorados de mutuo; o saldo deve ser conciliado e documentado."
            ),
            evidencia=evidence,
            recomendacao="Revisar o razao contabil e os extratos das contas de socios, validar contrato de mutuo ou instrumento equivalente, conferir prazo, juros, movimentacao financeira e comprovar o IOF recolhido quando aplicavel; reclassificar valores que representem adiantamento, distribuicao de lucros, reembolso ou despesa particular.",
            normas_aplicaveis=("ITG 2000", "NBC TG 1000", "RIR/2018", "Decreto 6.306/2007"),
        )
    ]
