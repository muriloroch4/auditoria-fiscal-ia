from __future__ import annotations

from decimal import Decimal
from unicodedata import combining, normalize

from ..config_loader import get_rule_config, load_config
from ..models import LedgerAccount, RiskLevel, RuleFinding, TrialBalance
from ..utils import format_brl, format_percent
from .comercio import analyze_commerce_rules
from .compostas import apply_compound_rules
from .metricas import (
    LEGACY_TAX_GROUP,
    ProfitBasis,
    account_trace_materiality,
    calculate_profit_basis,
    calculate_profit_distribution_capacity,
    collect_simples_metrics,
    format_account_trace,
    TAX_LIABILITY_GROUPS,
)
from .misto import check_mixed_revenue_segregation
from .rulesets import (
    COMMERCE_RULESETS,
    RULESET_COMERCIO,
    RULESET_COMERCIO_SERVICOS,
    RULESET_SERVICOS,
    SERVICE_RULESETS,
    normalize_ruleset,
)
from .servicos import check_payroll_factor

_money = format_brl
_percent = format_percent

DEBIT_NATURE_GROUPS = frozenset({
    "adiantamentos",
    "bancos",
    "caixa",
    "clientes",
    "creditos_fiscais",
    "estoque",
    "estoques",
    "imobilizado",
    "investimentos",
})
CREDIT_NATURE_GROUPS = frozenset({
    "adiantamentos_clientes",
    "emprestimos",
    "fornecedores",
    "patrimonio",
    "patrimonio_liquido",
    "provisoes",
    "tributos_a_recolher",
})

def analyze_simples_servicos(balance: TrialBalance, profit_basis: ProfitBasis | None = None) -> list[RuleFinding]:
    return _analyze_simples_nacional(balance, RULESET_SERVICOS, profit_basis=profit_basis)


def analyze_simples_comercio(balance: TrialBalance, profit_basis: ProfitBasis | None = None) -> list[RuleFinding]:
    return _analyze_simples_nacional(balance, RULESET_COMERCIO, profit_basis=profit_basis)


def analyze_simples_comercio_servicos(balance: TrialBalance, profit_basis: ProfitBasis | None = None) -> list[RuleFinding]:
    return _analyze_simples_nacional(balance, RULESET_COMERCIO_SERVICOS, profit_basis=profit_basis)


def analyze_simples_nacional(
    balance: TrialBalance,
    conjunto_regras: str | None = None,
    profit_basis: ProfitBasis | None = None,
    rbt12_context: dict | None = None,
) -> list[RuleFinding]:
    return _analyze_simples_nacional(
        balance,
        normalize_ruleset(conjunto_regras),
        profit_basis=profit_basis,
        rbt12_context=rbt12_context,
    )


def _analyze_simples_nacional(
    balance: TrialBalance,
    ruleset: str,
    profit_basis: ProfitBasis | None = None,
    rbt12_context: dict | None = None,
) -> list[RuleFinding]:
    metrics = collect_simples_metrics(balance, rbt12_context)

    if profit_basis is None:
        profit_basis = calculate_profit_basis(balance, metrics.revenue, metrics.expenses)
    profit_distribution_capacity = calculate_profit_distribution_capacity(balance, profit_basis)

    findings: list[RuleFinding] = []
    findings.extend(_check_low_or_missing_revenue(metrics.revenue, metrics.active_movement, metrics.operational_movement))
    findings.extend(_check_revenue_limit(metrics.revenue, metrics.rbt12_revenue))
    findings.extend(_check_tax_ratio(metrics.revenue, metrics.tax_expense, ruleset))
    if ruleset in SERVICE_RULESETS:
        findings.extend(check_payroll_factor(metrics.revenue, metrics.payroll, ruleset))
    findings.extend(
        _check_profit_distribution(
            metrics.revenue,
            metrics.profit_distribution,
            profit_basis,
            profit_distribution_capacity,
        )
    )
    findings.extend(_check_partner_accounts(metrics.revenue, metrics.partners, metrics.partner_accounts))
    findings.extend(_check_receivables(metrics.revenue, metrics.clients, metrics.client_movement))
    findings.extend(_check_zero_receivables(metrics.revenue, metrics.clients, metrics.client_movement))
    findings.extend(_check_advances(metrics.revenue, metrics.advances))
    findings.extend(_check_customer_advances(metrics.revenue, balance.contas_por_grupo("adiantamentos_clientes")))
    findings.extend(_check_cash_position(metrics.revenue, metrics.cash))
    findings.extend(_check_physical_cash_position(metrics.revenue, metrics.physical_cash, ruleset))
    findings.extend(_check_expense_ratio(metrics.revenue, metrics.expenses, balance, ruleset))
    findings.extend(
        _check_third_party_services_expense(
            metrics.third_party_services,
            metrics.expenses,
            metrics.third_party_service_accounts,
        )
    )
    findings.extend(_check_accounting_loss(metrics.revenue, profit_basis))
    findings.extend(_check_high_profit_margin(metrics.revenue, profit_basis))
    findings.extend(_check_tax_liability_growth(balance, metrics.revenue))
    findings.extend(_check_missing_provisions(metrics.revenue, metrics.payroll, balance))
    findings.extend(_check_inverse_account_nature(metrics.revenue, balance))
    findings.extend(_check_loans_without_interest_accrual(metrics.revenue, balance))
    if ruleset in COMMERCE_RULESETS:
        findings.extend(
            analyze_commerce_rules(
                metrics.revenue,
                metrics.inventory,
                metrics.suppliers,
                metrics.tax_credits,
                metrics.cogs,
                metrics.rbt12_revenue,
            )
        )
    if ruleset == RULESET_COMERCIO_SERVICOS:
        findings.extend(
            check_mixed_revenue_segregation(
                balance,
                metrics.revenue,
                metrics.payroll,
                metrics.inventory,
                metrics.suppliers,
            )
        )
    findings.extend(apply_compound_rules(findings))

    return findings


def _check_low_or_missing_revenue(revenue: Decimal, active_movement: Decimal, operational_movement: Decimal) -> list[RuleFinding]:
    cfg = load_config()
    lim_mov = Decimal(str(cfg.get("limites_gerais", {}).get("limite_movimentacao_ativa", 10000)))
    if active_movement < lim_mov:
        return []

    cfg008 = get_rule_config("SN-008")
    pts = cfg008.get("pontuacao_alto", 20)

    if revenue <= 0:
        return [
            RuleFinding(
                codigo="SN-008A",
                titulo="Receita inexistente com movimentação ativa",
                nivel=RiskLevel.ALTO,
                pontuacao=pts,
                descricao="A empresa apresenta movimentação contábil relevante, mas não possui receita registrada no período.",
                evidencia={"receita": _money(revenue), "movimentacao_ativa": _money(active_movement)},
                recomendacao="Verificar emissão de notas fiscais, reconhecimento de receita, classificação de entradas e possível tributação não apurada.",
                normas_aplicaveis=("LC 123/2006", "art. 3° LC 123/2006"),
            )
        ]

    if operational_movement <= 0:
        return []

    ratio_lim = Decimal(str(cfg.get("limites_gerais", {}).get("receita_baixa_ratio", 0.05)))
    if revenue / operational_movement < ratio_lim:
        return [
            RuleFinding(
                codigo="SN-008B",
                titulo="Receita muito baixa com movimentação ativa",
                nivel=RiskLevel.ALTO,
                pontuacao=pts,
                descricao="A receita registrada é muito baixa em relação à movimentação contábil ativa do período.",
                evidencia={
                    "receita": _money(revenue),
                    "movimentacao_ativa": _money(operational_movement),
                    "percentual": _percent(revenue / operational_movement),
                },
                recomendacao="Investigar operação sem emissão fiscal, receitas classificadas incorretamente ou movimentações que deveriam compor faturamento.",
                normas_aplicaveis=("LC 123/2006", "art. 3° LC 123/2006"),
            )
        ]

    return []


def _check_revenue_limit(revenue: Decimal, rbt12_revenue: Decimal | None = None) -> list[RuleFinding]:
    cfg = get_rule_config("SN-001")
    anual = Decimal(str(load_config().get("limites_gerais", {}).get("simples_anual", 4800000)))
    has_rbt12 = rbt12_revenue is not None and rbt12_revenue > 0
    annualized_revenue = (rbt12_revenue or Decimal("0")) if has_rbt12 else revenue * Decimal("4")
    ratio = annualized_revenue / anual if anual > 0 else Decimal("0")
    base_calculo_limite = "RBT12 consolidado pelo historico" if has_rbt12 else "receita trimestral anualizada (receita x 4)"

    lim_alto = Decimal(str(cfg.get("limite_alto", 0.90)))
    if ratio >= lim_alto:
        return [
            RuleFinding(
                codigo="SN-001B",
                titulo="Receita trimestral anualizada acima de 90% do limite do Simples",
                nivel=RiskLevel.ALTO,
                pontuacao=cfg.get("pontuacao_alto", 35),
                descricao="A receita do trimestre, quando anualizada para fins de alerta, fica próxima do limite anual do Simples Nacional.",
                evidencia={
                    "receita_trimestre": _money(revenue),
                    "receita_anualizada_estimativa": _money(annualized_revenue),
                    "limite_anual_simples": _money(anual),
                    "percentual_limite_anual": _percent(ratio),
                    "base_calculo_limite": base_calculo_limite,
                },
                recomendacao="Validar a receita bruta acumulada dos últimos 12 meses (RBT12), projetar os próximos trimestres e avaliar risco de sublimite, desenquadramento ou excesso de receita.",
                normas_aplicaveis=("LC 123/2006", "art. 3° LC 123/2006", "LC 155/2016"),
            )
        ]

    lim_medio = Decimal(str(cfg.get("limite_medio", 0.70)))
    if ratio >= lim_medio:
        return [
            RuleFinding(
                codigo="SN-001A",
                titulo="Receita trimestral anualizada acima de 70% do limite do Simples",
                nivel=RiskLevel.MEDIO,
                pontuacao=cfg.get("pontuacao_medio", 18),
                descricao="A receita do trimestre, quando anualizada para fins de alerta, representa mais de 70% do limite anual do Simples Nacional.",
                evidencia={
                    "receita_trimestre": _money(revenue),
                    "receita_anualizada_estimativa": _money(annualized_revenue),
                    "limite_anual_simples": _money(anual),
                    "percentual_limite_anual": _percent(ratio),
                    "base_calculo_limite": base_calculo_limite,
                },
                recomendacao="Acompanhar receita acumulada dos últimos 12 meses (RBT12) e simular cenários de crescimento para os próximos trimestres.",
                normas_aplicaveis=("LC 123/2006", "art. 3° LC 123/2006", "LC 155/2016"),
            )
        ]

    return []


def _check_tax_ratio(revenue: Decimal, tax_expense: Decimal, ruleset: str = RULESET_SERVICOS) -> list[RuleFinding]:
    if revenue <= 0:
        return []

    cfg = get_rule_config("SN-002")
    ratio = tax_expense / revenue
    tax_norm = _tax_annex_norm(ruleset)

    lim_alto = Decimal(str(cfg.get("limite_alto", 0.03)))
    if ratio < lim_alto:
        return [
            RuleFinding(
                codigo="SN-002B",
                titulo="Carga tributária abaixo de 3% da receita",
                nivel=RiskLevel.ALTO,
                pontuacao=cfg.get("pontuacao_alto", 20),
                descricao="Os impostos registrados representam menos de 3% da receita do período, indicando possível subapuração ou divergência fiscal a validar.",
                evidencia={"receita": _money(revenue), "tributos_registrados": _money(tax_expense), "percentual": _percent(ratio)},
                recomendacao="Conferir apuração do DAS, anexo aplicado, retenções, competência e possíveis lançamentos ausentes.",
                normas_aplicaveis=("LC 123/2006", tax_norm),
            )
        ]

    lim_medio = Decimal(str(cfg.get("limite_medio", 0.055)))
    if ratio < lim_medio:
        return [
            RuleFinding(
                codigo="SN-002A",
                titulo="Carga tributária abaixo de 5,5% da receita",
                nivel=RiskLevel.MEDIO,
                pontuacao=cfg.get("pontuacao_medio", 15),
                descricao="A relação entre tributos registrados e receita está em uma faixa que merece revisão.",
                evidencia={"receita": _money(revenue), "tributos_registrados": _money(tax_expense), "percentual": _percent(ratio)},
                recomendacao="Validar se todas as guias do trimestre foram reconhecidas e se houve retenções compensáveis.",
                normas_aplicaveis=("LC 123/2006", tax_norm),
            )
        ]

    return []


def _check_profit_distribution(
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


def _check_partner_accounts(revenue: Decimal, partners: Decimal, accounts: list[LedgerAccount]) -> list[RuleFinding]:
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


def _check_receivables(revenue: Decimal, clients: Decimal, client_movement: Decimal) -> list[RuleFinding]:
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


def _check_zero_receivables(revenue: Decimal, clients: Decimal, client_movement: Decimal) -> list[RuleFinding]:
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


def _check_advances(revenue: Decimal, advances: Decimal) -> list[RuleFinding]:
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


def _check_customer_advances(revenue: Decimal, accounts: list[LedgerAccount]) -> list[RuleFinding]:
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


def _check_inverse_account_nature(revenue: Decimal, balance: TrialBalance) -> list[RuleFinding]:
    inverse_accounts = [
        (account, issue)
        for account in balance.contas
        if (issue := _inverse_nature_issue(account))
    ]
    if not inverse_accounts:
        return []

    cfg = get_rule_config("SN-027")
    low_limit = Decimal(str(cfg.get("limite_baixo_absoluto", 1000)))
    total = sum((abs(account.saldo_atual) for account, _ in inverse_accounts), Decimal("0"))
    if total < low_limit:
        return []

    absolute_limit = Decimal(str(cfg.get("limite_medio_absoluto", 10000)))
    ratio_limit = Decimal(str(cfg.get("limite_medio_receita", 0.05)))
    ratio = total / revenue if revenue > 0 else None
    material = total >= absolute_limit or (ratio is not None and ratio >= ratio_limit)
    level = RiskLevel.MEDIO if material else RiskLevel.BAIXO
    score = cfg.get("pontuacao_medio", 14) if material else cfg.get("pontuacao_baixo", 6)

    return [
        RuleFinding(
            codigo="SN-027",
            titulo="Contas patrimoniais com saldo em natureza inversa",
            nivel=level,
            pontuacao=score,
            descricao=(
                "Foram identificadas contas patrimoniais com saldo em natureza inversa ao grupo contábil esperado, "
                "como ativo com saldo credor ou passivo com saldo devedor, sem indicação automática de conta redutora."
            ),
            evidencia={
                "receita": _money(revenue),
                "saldo_total_natureza_inversa": _money(total),
                "percentual_sobre_receita": _percent(ratio) if ratio is not None else "[VERIFICAR: receita trimestral]",
                "limite_absoluto_relevancia": _money(absolute_limit),
                "limite_percentual_relevancia": _percent(ratio_limit),
                "classificacao_materialidade": "material" if material else "baixa_materialidade",
                "quantidade_contas_identificadas": str(len(inverse_accounts)),
                "contas_identificadas": _format_inverse_nature_trace(inverse_accounts),
                "criterio_analise": "ativo/grupos de natureza devedora com saldo negativo; passivo/grupos de natureza credora com sinal oposto ao layout identificado",
                "excecoes_consideradas": "contas redutoras por descricao, como depreciacao acumulada, amortizacao acumulada, PCLD e perdas estimadas",
                "tipo_achado": "validacao_classificacao_contabil",
            },
            recomendacao=(
                "Revisar o razão das contas com natureza inversa, validar se são contas redutoras legítimas, "
                "conferir lançamentos, conciliações e reclassificar saldos que estejam em grupo contábil inadequado."
            ),
            normas_aplicaveis=("ITG 2000", "NBC TG 1000", "NBC TG 26 (R3) = CPC 26 R1"),
        )
    ]


def _check_loans_without_interest_accrual(revenue: Decimal, balance: TrialBalance) -> list[RuleFinding]:
    loan_accounts = _loan_accounts(balance)
    if not loan_accounts:
        return []

    loan_balance = sum((_account_exposure(account) for account in loan_accounts), Decimal("0"))
    loan_movement = sum((account.debito + account.credito for account in loan_accounts), Decimal("0"))
    cfg = get_rule_config("SN-028")
    low_limit = Decimal(str(cfg.get("limite_baixo_absoluto", 1000)))
    exposure = max(loan_balance, loan_movement)
    if exposure < low_limit:
        return []

    interest_accounts = _interest_or_financial_charge_accounts(balance)
    if interest_accounts:
        return []

    absolute_limit = Decimal(str(cfg.get("limite_medio_absoluto", 10000)))
    ratio_limit = Decimal(str(cfg.get("limite_medio_receita", 0.05)))
    ratio = exposure / revenue if revenue > 0 else None
    material = exposure >= absolute_limit or (ratio is not None and ratio >= ratio_limit)
    level = RiskLevel.MEDIO if material else RiskLevel.BAIXO
    score = cfg.get("pontuacao_medio", 14) if material else cfg.get("pontuacao_baixo", 6)

    return [
        RuleFinding(
            codigo="SN-028",
            titulo="Empréstimos sem evidência de juros ou encargos por competência",
            nivel=level,
            pontuacao=score,
            descricao=(
                "Foram identificados saldos ou movimentações em contas de empréstimos/financiamentos, "
                "mas o balancete não apresentou contas de juros, encargos financeiros, juros a transcorrer "
                "ou despesas financeiras relacionadas."
            ),
            evidencia={
                "receita": _money(revenue),
                "saldo_emprestimos": _money(loan_balance),
                "movimentacao_emprestimos": _money(loan_movement),
                "exposicao_considerada": _money(exposure),
                "percentual_sobre_receita": _percent(ratio) if ratio is not None else "[VERIFICAR: receita trimestral]",
                "limite_absoluto_relevancia": _money(absolute_limit),
                "limite_percentual_relevancia": _percent(ratio_limit),
                "classificacao_materialidade": "material" if material else "baixa_materialidade",
                "contas_emprestimos": format_account_trace(loan_accounts),
                "contas_juros_encargos_identificadas": "Nenhuma conta de juros, encargos financeiros, juros a transcorrer ou despesas financeiras foi identificada no balancete.",
                "validacao_documental": "[VERIFICAR: contratos de empréstimo, cronograma de amortização, taxa de juros, IOF, extratos e memória de cálculo dos encargos]",
                "tipo_achado": "validacao_competencia_juros",
            },
            recomendacao=(
                "Validar contratos de empréstimo e financiamento, cronogramas de amortização, taxas pactuadas, "
                "IOF, extratos bancários e memória de cálculo; apropriar juros e encargos por competência ou "
                "documentar formalmente a ausência de encargos no período."
            ),
            normas_aplicaveis=("ITG 2000", "NBC TG 1000", "NBC TG 26 (R3) = CPC 26 R1"),
        )
    ]


def _check_cash_position(revenue: Decimal, cash: Decimal) -> list[RuleFinding]:
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


def _check_physical_cash_position(
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


def _check_expense_ratio(
    revenue: Decimal,
    expenses: Decimal,
    balance: TrialBalance,
    ruleset: str = RULESET_SERVICOS,
) -> list[RuleFinding]:
    if revenue <= 0:
        return []

    findings: list[RuleFinding] = []

    cfg = get_rule_config("SN-007")
    lim = Decimal(str(cfg.get("limite_medio", 0.70)))
    ratio = expenses / revenue
    activity_label = _activity_label(ruleset)
    if ratio > lim:
        findings.append(
            RuleFinding(
                codigo="SN-007",
                titulo="Despesas operacionais elevadas",
                nivel=RiskLevel.MEDIO,
                pontuacao=cfg.get("pontuacao_medio", 16),
                descricao=f"As despesas operacionais representam percentual elevado da receita de {activity_label}.",
                evidencia={"receita": _money(revenue), "despesas": _money(expenses), "percentual": _percent(ratio)},
                recomendacao="Revisar despesas dedutíveis, gastos de sócios, documentos fiscais e coerência com a atividade.",
                normas_aplicaveis=("LC 123/2006", "RIR/2018"),
            )
        )

    cfg13 = get_rule_config("SN-013")
    rep_expenses = _abs(balance.debito_por_grupo("despesas_representacao"))
    if rep_expenses > 0:
        rep_ratio = rep_expenses / expenses
        lim_rep = Decimal(str(cfg13.get("limite_representacao", 0.15)))
        if rep_ratio > lim_rep:
            findings.append(
                RuleFinding(
                    codigo="SN-013A",
                    titulo="Despesas de representação elevadas",
                    nivel=RiskLevel.MEDIO,
                    pontuacao=cfg13.get("pontuacao_representacao", 10),
                    descricao=f"As despesas de representação representam {_percent(rep_ratio)} do total de despesas, percentual que pode indicar gastos particulares lançados na empresa.",
                    evidencia={
                        "despesas_representacao": _money(rep_expenses),
                        "total_despesas": _money(expenses),
                        "percentual": _percent(rep_ratio),
                    },
                    recomendacao="Revisar a natureza dos gastos de representação, exigindo comprovantes fiscais e documentação de suporte.",
                    normas_aplicaveis=("RIR/2018", "art. 47° LC 123/2006"),
                )
            )

    veh_expenses = _abs(balance.debito_por_grupo("despesas_veiculos"))
    if veh_expenses > 0:
        veh_ratio = veh_expenses / expenses
        lim_veh = Decimal(str(cfg13.get("limite_veiculos", 0.10)))
        if veh_ratio > lim_veh:
            findings.append(
                RuleFinding(
                    codigo="SN-013B",
                    titulo="Despesas de veículos elevadas",
                    nivel=RiskLevel.MEDIO,
                    pontuacao=cfg13.get("pontuacao_veiculos", 10),
                    descricao=f"As despesas com veículos representam {_percent(veh_ratio)} do total de despesas, percentual que merece validação quanto à atividade da empresa.",
                    evidencia={
                        "despesas_veiculos": _money(veh_expenses),
                        "total_despesas": _money(expenses),
                        "percentual": _percent(veh_ratio),
                    },
                    recomendacao="Confrontar despesas de veículos com a quantidade de veículos, contratos de leasing/combustível e efetiva necessidade operacional.",
                    normas_aplicaveis=("RIR/2018", "art. 47° LC 123/2006"),
                )
            )

    return findings


def _check_third_party_services_expense(
    third_party_services: Decimal,
    expenses: Decimal,
    accounts: list[LedgerAccount],
) -> list[RuleFinding]:
    if third_party_services <= 0 or expenses <= 0:
        return []

    cfg = get_rule_config("SN-025")
    absolute_limit = Decimal(str(cfg.get("limite_absoluto", 10000)))
    ratio_limit = Decimal(str(cfg.get("limite_ratio_despesas", 0.20)))
    ratio = third_party_services / expenses

    if third_party_services < absolute_limit or ratio < ratio_limit:
        return []

    return [
        RuleFinding(
            codigo="SN-025",
            titulo="Servicos prestados por terceiros relevantes nas despesas",
            nivel=RiskLevel.MEDIO,
            pontuacao=cfg.get("pontuacao_medio", 12),
            descricao="A conta 325/servicos prestados por terceiros representa percentual relevante das despesas do trimestre, indicando necessidade de validacao documental dos lancamentos.",
            evidencia={
                "conta_referencia": "325 - Servicos prestados por terceiros",
                "servicos_terceiros": _money(third_party_services),
                "total_despesas": _money(expenses),
                "percentual_sobre_despesas": _percent(ratio),
                "limite_percentual_despesas": _percent(ratio_limit),
                "limite_absoluto": _money(absolute_limit),
                "quantidade_contas_identificadas": str(len(accounts)),
                "contas_identificadas": format_account_trace(accounts),
                "criterio_rastreio": "codigo 325, prefixo configurado ou descricao de servicos prestados por terceiros",
                "tipo_achado": "validacao_documental",
            },
            recomendacao="Verificar e validar os lancamentos da conta 325, confrontando pagamentos, contratos, notas fiscais, comprovantes bancarios, retencoes aplicaveis e suporte documental antes de manter a despesa.",
            normas_aplicaveis=("ITG 2000", "NBC TG 1000"),
        )
    ]


def _check_accounting_loss(revenue: Decimal, profit_basis: ProfitBasis) -> list[RuleFinding]:
    cfg = get_rule_config("SN-009")

    if profit_basis.value >= 0:
        return []

    if revenue <= 0:
        return [
            RuleFinding(
                codigo="SN-009A",
                titulo="Prejuízo contábil sem receita declarada",
                nivel=RiskLevel.ALTO,
                pontuacao=cfg.get("pontuacao_alto", 25),
                descricao="A empresa apresenta prejuízo contábil e nenhuma receita declarada, indicando risco de continuidade operacional.",
                evidencia={
                    "lucro_apurado": _money(profit_basis.value),
                    "origem_lucro": profit_basis.source,
                },
                recomendacao="Avaliar viabilidade operacional, verificar passivos acumulados e documentar o enquadramento fiscal aplicável.",
                normas_aplicaveis=("NBC TG 1000", "ITG 2000"),
            )
        ]

    loss_ratio = abs(profit_basis.value) / revenue
    lim = Decimal(str(cfg.get("limite_medio_ratio", 0.10)))
    if loss_ratio > lim:
        return [
            RuleFinding(
                codigo="SN-009B",
                titulo=f"Prejuízo contábil significativo ({_percent(abs(profit_basis.value) / revenue)} da receita)",
                nivel=RiskLevel.ALTO,
                pontuacao=cfg.get("pontuacao_alto", 25),
                descricao=f"O prejuízo apurado representa {_percent(loss_ratio)} da receita, indicando desequilíbrio entre custos e receitas.",
                evidencia={
                    "lucro_apurado": _money(profit_basis.value),
                    "receita": _money(revenue),
                    "percentual_prejuizo": _percent(loss_ratio),
                },
                recomendacao="Revisar estrutura de custos, margem de contribuição, viabilidade do modelo de negócio e efeitos tributários aplicáveis.",
                normas_aplicaveis=("NBC TG 1000", "ITG 2000"),
            )
        ]

    return [
        RuleFinding(
            codigo="SN-009C",
            titulo="Prejuízo contábil leve",
            nivel=RiskLevel.MEDIO,
            pontuacao=cfg.get("pontuacao_medio", 12),
            descricao="A empresa apurou prejuízo contábil no período, mesmo que em proporção reduzida.",
            evidencia={
                "lucro_apurado": _money(profit_basis.value),
                "receita": _money(revenue),
            },
            recomendacao="Acompanhar evolução do resultado nos próximos trimestres e identificar causas do déficit.",
            normas_aplicaveis=("NBC TG 1000", "ITG 2000"),
        )
    ]


def _check_high_profit_margin(revenue: Decimal, profit_basis: ProfitBasis) -> list[RuleFinding]:
    if revenue <= 0 or profit_basis.value <= 0:
        return []

    cfg = get_rule_config("SN-021")
    margin = profit_basis.value / revenue
    reference = Decimal(str(cfg.get("referencia_presuncao_servicos", 0.32)))

    high_limit = Decimal(str(cfg.get("limite_medio_ratio", 0.64)))
    if margin > high_limit:
        return [
            RuleFinding(
                codigo="SN-021B",
                titulo="Margem de lucro contábil muito elevada",
                nivel=RiskLevel.MEDIO,
                pontuacao=cfg.get("pontuacao_medio", 12),
                descricao="O lucro contábil representa percentual muito elevado da receita, sugerindo possível ausência de despesas, custos ou lançamentos de competência.",
                evidencia={
                    "receita": _money(revenue),
                    "lucro_apurado": _money(profit_basis.value),
                    "origem_lucro": profit_basis.source,
                    "margem_lucro": _percent(margin),
                    "referencia_presuncao": _percent(reference),
                },
                recomendacao="Revisar se todas as despesas, custos, folha, pró-labore, fornecedores, serviços tomados e encargos foram reconhecidos pelo regime de competência.",
                normas_aplicaveis=("NBC TG 1000", "ITG 2000"),
            )
        ]

    attention_limit = Decimal(str(cfg.get("limite_baixo_ratio", 0.45)))
    if margin > attention_limit:
        return [
            RuleFinding(
                codigo="SN-021A",
                titulo="Margem de lucro contábil acima da referência esperada",
                nivel=RiskLevel.BAIXO,
                pontuacao=cfg.get("pontuacao_baixo", 6),
                descricao="O lucro contábil está acima da referência gerencial usada como alerta, exigindo validação das despesas e custos do período.",
                evidencia={
                    "receita": _money(revenue),
                    "lucro_apurado": _money(profit_basis.value),
                    "origem_lucro": profit_basis.source,
                    "margem_lucro": _percent(margin),
                    "referencia_presuncao": _percent(reference),
                },
                recomendacao="Conferir despesas, custos e apropriações de competência para confirmar se a margem elevada representa a realidade operacional.",
                normas_aplicaveis=("NBC TG 1000", "ITG 2000"),
            )
        ]

    return []


def _check_tax_liability_growth(balance: TrialBalance, revenue: Decimal) -> list[RuleFinding]:
    if revenue <= 0:
        return []

    cfg = get_rule_config("SN-012")
    pts = cfg.get("pontuacao_medio", 14)

    tax_accounts = []
    for group in TAX_LIABILITY_GROUPS:
        tax_accounts.extend(balance.contas_por_grupo(group))
    if not tax_accounts:
        tax_accounts = balance.contas_por_grupo(LEGACY_TAX_GROUP)
    if not tax_accounts:
        return []

    previous_tax = _abs(sum((account.saldo_anterior for account in tax_accounts), Decimal("0")))
    current_tax = _abs(sum((account.saldo_atual for account in tax_accounts), Decimal("0")))

    if previous_tax >= current_tax or previous_tax <= 0:
        return []

    growth_ratio = (current_tax - previous_tax) / previous_tax
    lim = Decimal(str(cfg.get("limite_medio", 0.50)))
    if growth_ratio > lim:
        return [
            RuleFinding(
                codigo="SN-012",
                titulo="Passivo tributário com crescimento relevante",
                nivel=RiskLevel.MEDIO,
                pontuacao=pts,
                descricao=f"O saldo de tributos a recolher cresceu {_percent(growth_ratio)} em relação ao período anterior, indicando possível acúmulo de débitos fiscais.",
                evidencia={
                    "saldo_anterior_tributos": _money(previous_tax),
                    "saldo_atual_tributos": _money(current_tax),
                    "crescimento": _percent(growth_ratio),
                },
                recomendacao="Conferir apuração do DAS dos períodos, regularidade fiscal e possíveis parcelamentos em aberto.",
                normas_aplicaveis=("LC 123/2006", "art. 47° LC 123/2006"),
            )
        ]

    return []


def _check_missing_provisions(revenue: Decimal, payroll: Decimal, balance: TrialBalance) -> list[RuleFinding]:
    if revenue <= 0 or payroll <= 0:
        return []

    cfg = get_rule_config("SN-014")
    payroll_ratio = payroll / revenue
    lim_folha = Decimal(str(cfg.get("limite_folha_receita", 0.10)))

    if payroll_ratio < lim_folha:
        return []

    provisions = _abs(balance.total_por_grupo("provisoes"))
    if provisions > 0:
        return []

    return [
        RuleFinding(
            codigo="SN-014",
            titulo="Ausência de provisões trabalhistas com folha significativa",
            nivel=RiskLevel.MEDIO,
            pontuacao=cfg.get("pontuacao_medio", 12),
            descricao=f"A folha de pagamento representa {_percent(payroll_ratio)} da receita, mas não foram identificadas provisões para férias, 13º salário ou encargos no balancete.",
            evidencia={
                "receita": _money(revenue),
                "folha_pro_labore": _money(payroll),
                "percentual_folha": _percent(payroll_ratio),
                "provisoes": _money(provisions),
            },
            recomendacao="Constituir provisões trabalhistas (férias, 13º, FGTS, INSS) conforme regime de competência e ITG 2000.",
            normas_aplicaveis=("ITG 2000", "CLT", "art. 47° LC 123/2006"),
        )
    ]


def _inverse_nature_issue(account: LedgerAccount) -> str:
    if account.saldo_atual == 0 or _is_reducer_account(account):
        return ""

    code = str(account.codigo or "").strip()
    if _is_debit_nature_account(account, code):
        return "ativo_ou_conta_devedora_com_saldo_credor" if account.saldo_atual < 0 else ""
    if _is_credit_nature_account(account, code):
        if _uses_dominio_credit_sign(account):
            return "passivo_ou_conta_credora_com_saldo_devedor" if account.saldo_atual > 0 else ""
        return "passivo_ou_conta_credora_com_saldo_devedor" if account.saldo_atual < 0 else ""
    return ""


def _is_debit_nature_account(account: LedgerAccount, code: str) -> bool:
    return code.startswith("1.") or account.grupo in DEBIT_NATURE_GROUPS


def _is_credit_nature_account(account: LedgerAccount, code: str) -> bool:
    return code.startswith("2.") or account.grupo in CREDIT_NATURE_GROUPS


def _uses_dominio_credit_sign(account: LedgerAccount) -> bool:
    origin = (account.classificacao_origem or "").lower()
    observation = (account.classificacao_observacao or "").lower()
    return "dominio" in origin or "dominio" in observation


def _is_reducer_account(account: LedgerAccount) -> bool:
    text = _normalize_rule_text(account.conta)
    reducer_keywords = (
        "(-)",
        "amortizacao acumulada",
        "ajuste a valor recuperavel",
        "depreciacao acumulada",
        "duplicatas descontadas",
        "exaustao acumulada",
        "perda estimada",
        "perdas estimadas",
        "pcld",
        "provisao para perda",
        "provisao para perdas",
        "redutora",
        "retificadora",
    )
    return any(keyword in text for keyword in reducer_keywords)


def _format_inverse_nature_trace(accounts: list[tuple[LedgerAccount, str]], limit: int = 6) -> str:
    if not accounts:
        return "Nenhuma conta individual identificada"

    sorted_accounts = sorted(
        accounts,
        key=lambda item: account_trace_materiality(item[0]),
        reverse=True,
    )
    items = [
        (
            f"{account.codigo} - {account.conta} "
            f"({issue}; grupo {account.grupo}; debito {_money(account.debito)}; "
            f"credito {_money(account.credito)}; saldo {_money(account.saldo_atual)})"
        )
        for account, issue in sorted_accounts[:limit]
    ]
    if len(sorted_accounts) > limit:
        items.append(f"... mais {len(sorted_accounts) - limit} conta(s)")
    return " | ".join(items)


def _loan_accounts(balance: TrialBalance) -> list[LedgerAccount]:
    return [
        account
        for account in balance.contas
        if _is_loan_account(account) and _account_exposure(account) > 0
    ]


def _is_loan_account(account: LedgerAccount) -> bool:
    text = _normalize_rule_text(account.conta)
    if account.grupo == "socios" or any(keyword in text for keyword in ("socio", "socios", "administrador", "pessoa ligada", "mutuo")):
        return False
    if account.grupo == "emprestimos":
        return True
    loan_keywords = (
        "emprestimo",
        "emprestimos",
        "financiamento",
        "financiamentos",
        "capital de giro",
        "parcelamento bancario",
        "banco conta emprestimo",
    )
    return any(keyword in text for keyword in loan_keywords) and not _is_interest_or_financial_charge_account(account)


def _interest_or_financial_charge_accounts(balance: TrialBalance) -> list[LedgerAccount]:
    return [
        account
        for account in balance.contas
        if _is_interest_or_financial_charge_account(account) and _account_exposure(account) > 0
    ]


def _is_interest_or_financial_charge_account(account: LedgerAccount) -> bool:
    text = _normalize_rule_text(account.conta)
    if "juros sobre capital" in text or "jcp" in text:
        return False
    keywords = (
        "a apropriar",
        "a incorrer",
        "a transcorrer",
        "despesa financeira",
        "despesas financeiras",
        "encargo financeiro",
        "encargos financeiros",
        "iof sobre emprestimo",
        "juros",
        "variacao monetaria",
    )
    return any(keyword in text for keyword in keywords)


def _account_exposure(account: LedgerAccount) -> Decimal:
    if account.saldo_atual != 0:
        return abs(account.saldo_atual)
    return abs(account.debito) + abs(account.credito)


def _normalize_rule_text(value: str) -> str:
    normalized = normalize("NFKD", value or "")
    return "".join(char for char in normalized if not combining(char)).lower()


def _abs(value: Decimal) -> Decimal:
    return abs(value)


def _activity_label(ruleset: str) -> str:
    if ruleset == RULESET_COMERCIO:
        return "comercio"
    if ruleset == RULESET_COMERCIO_SERVICOS:
        return "comercio e servicos"
    return "servicos"


def _tax_annex_norm(ruleset: str) -> str:
    if ruleset == RULESET_COMERCIO:
        return "Anexo I da LC 123/2006"
    if ruleset == RULESET_COMERCIO_SERVICOS:
        return "Anexos I e III/V da LC 123/2006"
    return "Anexo III da LC 123/2006"
