from __future__ import annotations

from decimal import Decimal

from ..config_loader import get_rule_config
from ..models import LedgerAccount, RiskLevel, RuleFinding
from ..utils import format_brl, format_percent
from .metricas import format_account_trace
from .rulesets import RULESET_COMERCIO

_money = format_brl
_percent = format_percent


def check_receivables(revenue: Decimal, clients: Decimal, client_movement: Decimal) -> list[RuleFinding]:
    if clients <= 0:
        return []

    cfg = get_rule_config("SN-010")

    if client_movement == 0:
        pts = cfg.get("pontuacao_medio", 12)
        return [
            RuleFinding(
                codigo="SN-010A",
                titulo="Clientes e recebíveis sem movimentação",
                nivel=RiskLevel.MEDIO,
                pontuacao=pts,
                descricao="O saldo final de clientes e recebíveis permaneceu sem movimentação no trimestre, exigindo validação da composição e realização do crédito.",
                evidencia={"saldo_final_clientes_recebiveis": _money(clients), "movimentacao_clientes_trimestre": _money(client_movement)},
                recomendacao="Conciliar o saldo com relatório de contas a receber, notas fiscais, recebimentos posteriores e eventuais perdas esperadas.",
                normas_aplicaveis=("NBC TG 1000", "ITG 2000"),
            )
        ]

    if revenue > 0:
        ratio = clients / revenue
        lim_alto = Decimal(str(cfg.get("limite_alto_ratio", 2.0)))
        if ratio > lim_alto:
            pts = cfg.get("pontuacao_alto", 20)
            return [
                RuleFinding(
                    codigo="SN-010C",
                    titulo="Clientes e recebíveis muito elevados (acima de 200% da receita)",
                    nivel=RiskLevel.ALTO,
                    pontuacao=pts,
                    descricao="O saldo final de clientes e recebíveis é excessivamente elevado em relação à receita trimestral, indicando possível prazo médio de recebimento elevado, baixa pendente ou inconsistência de realização.",
                    evidencia={"receita_trimestre": _money(revenue), "saldo_final_clientes_recebiveis": _money(clients), "percentual_sobre_receita_trimestral": _percent(ratio)},
                    recomendacao="Validar aging list, prazo médio de recebimento, liquidação posterior dos títulos, baixa de recebíveis e critérios de reconhecimento de receita.",
                    normas_aplicaveis=("NBC TG 1000", "ITG 2000"),
                )
            ]

        lim_medio = Decimal(str(cfg.get("limite_medio_ratio", 1.0)))
        if ratio > lim_medio:
            pts = cfg.get("pontuacao_medio", 12)
            return [
                RuleFinding(
                    codigo="SN-010B",
                    titulo="Clientes e recebíveis elevados (acima de 100% da receita)",
                    nivel=RiskLevel.MEDIO,
                    pontuacao=pts,
                    descricao="O saldo final de clientes e recebíveis é relevante em relação à receita trimestral, funcionando como alerta de prazo de recebimento, baixa pendente ou composição antiga.",
                    evidencia={"receita_trimestre": _money(revenue), "saldo_final_clientes_recebiveis": _money(clients), "percentual_sobre_receita_trimestral": _percent(ratio)},
                    recomendacao="Validar aging list, prazo médio de recebimento, liquidação posterior dos títulos, baixa de recebíveis e critérios de reconhecimento de receita.",
                    normas_aplicaveis=("NBC TG 1000", "ITG 2000"),
                )
            ]

    return []


def check_zero_receivables(revenue: Decimal, clients: Decimal, client_movement: Decimal) -> list[RuleFinding]:
    cfg = get_rule_config("SN-023")
    min_revenue = Decimal(str(cfg.get("receita_minima", 200000)))
    if revenue < min_revenue or clients != 0 or client_movement != 0:
        return []

    return [
        RuleFinding(
            codigo="SN-023",
            titulo="Clientes e recebíveis zerados com receita relevante",
            nivel=RiskLevel.BAIXO,
            pontuacao=cfg.get("pontuacao_baixo", 6),
            descricao="A empresa apresenta receita relevante no trimestre, mas não possui saldo ou movimentação em clientes e recebíveis.",
            evidencia={
                "receita": _money(revenue),
                "clientes_recebiveis": _money(clients),
                "movimentacao_clientes_trimestre": _money(client_movement),
                "receita_minima": _money(min_revenue),
            },
            recomendacao="Validar se as vendas ou serviços foram recebidos à vista/no mesmo mês, conciliando notas fiscais, meios de pagamento, extratos bancários e baixas de recebíveis.",
            normas_aplicaveis=("NBC TG 1000", "ITG 2000"),
        )
    ]


def check_advances(revenue: Decimal, advances: Decimal) -> list[RuleFinding]:
    if revenue <= 0 or advances <= 0:
        return []

    cfg = get_rule_config("SN-011")
    pts = cfg.get("pontuacao_medio", 12)
    absolute_limit = Decimal(str(cfg.get("limite_absoluto", 10000)))
    ratio_limit = Decimal(str(cfg.get("limite_ratio", 0.10)))
    ratio_reference = revenue * ratio_limit
    reference = max(absolute_limit, ratio_reference)
    if advances > reference:
        return [
            RuleFinding(
                codigo="SN-011A",
                titulo="Adiantamentos relevantes sem validação documental",
                nivel=RiskLevel.MEDIO,
                pontuacao=pts,
                descricao="Foram identificados saldos de adiantamentos acima da maior referência entre valor absoluto e percentual da receita trimestral.",
                evidencia={
                    "adiantamentos": _money(advances),
                    "limite_absoluto": _money(absolute_limit),
                    "limite_percentual_relevancia": _percent(ratio_limit),
                    "limite_calculado_percentual_receita": _money(ratio_reference),
                    "referencia_aplicada": _money(reference),
                },
                recomendacao="Revisar adiantamentos a fornecedores, clientes, empregados e terceiros, documentando a origem, a contraprestação e a baixa esperada.",
                normas_aplicaveis=("NBC TG 1000", "ITG 2000"),
            )
        ]

    return []


def check_customer_advances(revenue: Decimal, accounts: list[LedgerAccount]) -> list[RuleFinding]:
    customer_advances = sum((abs(account.saldo_atual) for account in accounts), Decimal("0"))
    if customer_advances <= 0:
        return []

    cfg = get_rule_config("SN-026")
    absolute_limit = Decimal(str(cfg.get("limite_medio_absoluto", 10000)))
    ratio_limit = Decimal(str(cfg.get("limite_medio_receita", 0.05)))
    ratio = customer_advances / revenue if revenue > 0 else None
    material = customer_advances >= absolute_limit or (ratio is not None and ratio >= ratio_limit)
    level = RiskLevel.MEDIO if material else RiskLevel.BAIXO
    score = cfg.get("pontuacao_medio", 14) if material else cfg.get("pontuacao_baixo", 6)

    return [
        RuleFinding(
            codigo="SN-026",
            titulo="Adiantamento de clientes no passivo exige validacao fiscal e documental",
            nivel=level,
            pontuacao=score,
            descricao=(
                "Foi identificado saldo em conta passiva de adiantamento de clientes. O saldo pode representar "
                "receita antecipada legitima, mas tambem pode indicar risco fiscal quando houver receita ja "
                "liquidada sem baixa, emissao fiscal ou reconhecimento contabil adequado."
            ),
            evidencia={
                "receita": _money(revenue),
                "adiantamentos_clientes": _money(customer_advances),
                "percentual_sobre_receita": _percent(ratio) if ratio is not None else "[VERIFICAR: receita trimestral]",
                "limite_absoluto_relevancia": _money(absolute_limit),
                "limite_percentual_relevancia": _percent(ratio_limit),
                "classificacao_materialidade": "material" if material else "baixa_materialidade",
                "contas_identificadas": format_account_trace(accounts),
                "baixa_liquidacao": "[VERIFICAR: se os adiantamentos ja foram liquidados, faturados, baixados ou convertidos em receita]",
                "validacao_documental": "[VERIFICAR: contratos, pedidos, notas fiscais, extratos, recibos e razao contabil]",
                "tipo_achado": "validacao_documental_fiscal",
            },
            recomendacao=(
                "Validar a composicao dos adiantamentos de clientes, confrontando contratos, pedidos, notas fiscais, "
                "extratos bancarios, recibos e razao contabil; verificar se os valores ja foram liquidados, faturados "
                "ou baixados e regularizar eventual receita nao reconhecida."
            ),
            normas_aplicaveis=("LC 123/2006", "NBC TG 1000", "ITG 2000"),
        )
    ]


def check_cash_position(revenue: Decimal, cash: Decimal) -> list[RuleFinding]:
    cfg = get_rule_config("SN-006")

    if cash < 0:
        return [
            RuleFinding(
                codigo="SN-006A",
                titulo="Saldo de caixa ou bancos negativo",
                nivel=RiskLevel.ALTO,
                pontuacao=cfg.get("pontuacao_alto", 28),
                descricao="O saldo combinado de caixa e bancos está negativo, indicando possível inconsistência contábil.",
                evidencia={"caixa_bancos": _money(cash)},
                recomendacao="Reconciliar extratos, lançamentos de caixa, contas de sócios e pagamentos não baixados.",
                normas_aplicaveis=("NBC TG 1000", "ITG 2000"),
            )
        ]

    if revenue > 0:
        lim = Decimal(str(cfg.get("limite_medio_ratio", 0.60)))
        if cash / revenue > lim:
            return [
                RuleFinding(
                    codigo="SN-006B",
                    titulo="Saldo de caixa e bancos acima de 60% da receita",
                    nivel=RiskLevel.MEDIO,
                    pontuacao=cfg.get("pontuacao_medio", 12),
                    descricao="O saldo financeiro está alto em relação à receita trimestral, o que pode exigir conciliação detalhada.",
                    evidencia={"receita": _money(revenue), "caixa_bancos": _money(cash), "percentual": _percent(cash / revenue)},
                    recomendacao="Conferir conciliação bancária, caixa físico e valores recebidos ainda não classificados.",
                    normas_aplicaveis=("NBC TG 1000", "ITG 2000"),
                )
            ]

    return []


def check_physical_cash_position(
    revenue: Decimal,
    physical_cash: Decimal,
    ruleset: str,
) -> list[RuleFinding]:
    if revenue <= 0 or physical_cash <= 0:
        return []

    cfg = get_rule_config("SN-022")
    if ruleset == RULESET_COMERCIO:
        absolute_limit = Decimal(str(cfg.get("limite_comercio_absoluto", 10000)))
        ratio_limit = Decimal(str(cfg.get("limite_comercio_ratio", 0.05)))
    else:
        absolute_limit = Decimal(str(cfg.get("limite_servicos_absoluto", 3000)))
        ratio_limit = Decimal(str(cfg.get("limite_servicos_ratio", 0.02)))

    reference = max(absolute_limit, revenue * ratio_limit)
    high_multiplier = Decimal(str(cfg.get("multiplicador_alto", 3)))
    high_reference = reference * high_multiplier

    if physical_cash > high_reference:
        return [
            RuleFinding(
                codigo="SN-022B",
                titulo="Caixa físico muito elevado para o porte e atividade",
                nivel=RiskLevel.ALTO,
                pontuacao=cfg.get("pontuacao_alto", 18),
                descricao="O saldo de caixa físico é muito superior ao parâmetro esperado para a atividade e o porte da empresa.",
                evidencia={
                    "receita": _money(revenue),
                    "caixa_fisico": _money(physical_cash),
                    "limite_caixa": _money(reference),
                    "limite_alto_caixa": _money(high_reference),
                },
                recomendacao="Reconciliar caixa físico, extratos bancários, recebimentos em dinheiro, pagamentos sem suporte bancário e eventual uso indevido de conta caixa.",
                normas_aplicaveis=("NBC TG 1000", "ITG 2000"),
            )
        ]

    if physical_cash > reference:
        return [
            RuleFinding(
                codigo="SN-022A",
                titulo="Caixa físico acima do parâmetro esperado",
                nivel=RiskLevel.MEDIO,
                pontuacao=cfg.get("pontuacao_medio", 12),
                descricao="O saldo de caixa físico está acima do parâmetro esperado para a atividade e deve ser conciliado com os documentos de suporte.",
                evidencia={
                    "receita": _money(revenue),
                    "caixa_fisico": _money(physical_cash),
                    "limite_caixa": _money(reference),
                },
                recomendacao="Validar se o saldo representa numerário real, recebimentos pendentes de depósito, pagamentos em espécie ou lançamentos que deveriam estar em bancos/sócios.",
                normas_aplicaveis=("NBC TG 1000", "ITG 2000"),
            )
        ]

    return []
