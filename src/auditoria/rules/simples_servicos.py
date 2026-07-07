from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from unicodedata import combining, normalize

from ..config_loader import get_rule_config, load_config
from ..models import RiskLevel, RuleFinding, TrialBalance
from ..utils import format_brl, format_percent

_money = format_brl
_percent = format_percent

OPERATING_EXPENSE_GROUPS = frozenset({
    "despesas",
    "custos",
    "despesas_representacao",
    "despesas_veiculos",
    "despesas_tributarias",
    "multas_fiscais",
})
ADVANCE_GROUPS = frozenset({"adiantamentos", "adiantamentos_clientes"})
TAX_EXPENSE_GROUPS = frozenset({"despesas_tributarias"})
TAX_LIABILITY_GROUPS = frozenset({"tributos_a_recolher"})
LEGACY_TAX_GROUP = "tributos"

RULESET_SERVICOS = "simples_servicos"
RULESET_COMERCIO = "simples_comercio"
RULESET_COMERCIO_SERVICOS = "simples_comercio_servicos"

_RULESET_ALIASES = {
    "servico": RULESET_SERVICOS,
    "servicos": RULESET_SERVICOS,
    "serviços": RULESET_SERVICOS,
    "simples_servicos": RULESET_SERVICOS,
    "simples_serviços": RULESET_SERVICOS,
    "comercio": RULESET_COMERCIO,
    "comércio": RULESET_COMERCIO,
    "simples_comercio": RULESET_COMERCIO,
    "simples_comércio": RULESET_COMERCIO,
    "misto": RULESET_COMERCIO_SERVICOS,
    "mista": RULESET_COMERCIO_SERVICOS,
    "comercio_servicos": RULESET_COMERCIO_SERVICOS,
    "comércio_serviços": RULESET_COMERCIO_SERVICOS,
    "comercio e servicos": RULESET_COMERCIO_SERVICOS,
    "comércio e serviços": RULESET_COMERCIO_SERVICOS,
    "simples_comercio_servicos": RULESET_COMERCIO_SERVICOS,
    "simples_comércio_serviços": RULESET_COMERCIO_SERVICOS,
}

_SERVICE_RULESETS = frozenset({RULESET_SERVICOS, RULESET_COMERCIO_SERVICOS})
_COMMERCE_RULESETS = frozenset({RULESET_COMERCIO, RULESET_COMERCIO_SERVICOS})


@dataclass(frozen=True)
class ProfitBasis:
    value: Decimal
    source: str


def normalize_ruleset(value: str | None = None) -> str:
    normalized = _normalize_text(value or RULESET_SERVICOS).replace("-", "_").replace("/", " ")
    normalized = " ".join(normalized.replace("_", " ").split())
    direct_key = normalized.replace(" ", "_")
    return _RULESET_ALIASES.get(normalized) or _RULESET_ALIASES.get(direct_key) or RULESET_SERVICOS


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
    revenue = calculate_revenue(balance)
    active_movement = _active_movement(balance)
    tax_expense = calculate_tax_expense(balance)
    payroll = _abs(balance.debito_por_grupo("folha"))
    expenses = calculate_operating_expenses(balance)
    partners = _abs(balance.total_por_grupo("socios"))
    clients = _abs(balance.total_por_grupo("clientes"))
    client_movement = _group_movement(balance, "clientes")
    advances = calculate_advances(balance)
    profit_distribution = calculate_profit_distribution(balance)
    cash = balance.total_por_grupo("caixa") + balance.total_por_grupo("bancos")
    physical_cash = _abs(balance.total_por_grupo("caixa"))
    suppliers = calculate_suppliers(balance)
    inventory = calculate_inventory(balance)
    tax_credits = calculate_tax_credits(balance)
    cogs = calculate_cost_of_goods(balance)
    rbt12_revenue = _rbt12_decimal(rbt12_context, "receita")

    if profit_basis is None:
        profit_basis = calculate_profit_basis(balance, revenue, expenses)
    profit_distribution_capacity = calculate_profit_distribution_capacity(balance, profit_basis)

    findings: list[RuleFinding] = []
    findings.extend(_check_low_or_missing_revenue(revenue, active_movement, _operational_movement(balance)))
    findings.extend(_check_revenue_limit(revenue, rbt12_revenue))
    findings.extend(_check_tax_ratio(revenue, tax_expense, ruleset))
    if ruleset in _SERVICE_RULESETS:
        findings.extend(_check_payroll_factor(revenue, payroll, ruleset))
    findings.extend(_check_profit_distribution(revenue, profit_distribution, profit_basis, profit_distribution_capacity))
    findings.extend(_check_partner_accounts(revenue, partners))
    findings.extend(_check_receivables(revenue, clients, client_movement))
    findings.extend(_check_zero_receivables(revenue, clients, client_movement))
    findings.extend(_check_advances(revenue, advances))
    findings.extend(_check_cash_position(revenue, cash))
    findings.extend(_check_physical_cash_position(revenue, physical_cash, ruleset))
    findings.extend(_check_expense_ratio(revenue, expenses, balance, ruleset))
    findings.extend(_check_accounting_loss(revenue, profit_basis))
    findings.extend(_check_high_profit_margin(revenue, profit_basis))
    findings.extend(_check_tax_liability_growth(balance, revenue))
    findings.extend(_check_missing_provisions(revenue, payroll, balance))
    if ruleset in _COMMERCE_RULESETS:
        findings.extend(_check_inventory_position(revenue, inventory, cogs))
        findings.extend(_check_supplier_position(revenue, suppliers, inventory))
        findings.extend(_check_tax_credits_simples(revenue, tax_credits))
        findings.extend(_check_cogs_for_commerce(revenue, inventory, suppliers, cogs))
        findings.extend(_check_commerce_sublimit(revenue, rbt12_revenue))
        findings.extend(_check_icms_st_attention(revenue, inventory, suppliers, cogs, tax_credits))
    if ruleset == RULESET_COMERCIO_SERVICOS:
        findings.extend(_check_mixed_revenue_segregation(balance, revenue, payroll, inventory, suppliers))
    findings.extend(_apply_compound_rules(findings))

    return findings


def calculate_profit_basis(
    balance: TrialBalance,
    revenue: Decimal | None = None,
    expenses: Decimal | None = None,
) -> ProfitBasis:
    result_accounts = balance.contas_por_grupo("resultado")
    if result_accounts:
        return ProfitBasis(
            value=sum((account.saldo_atual for account in result_accounts), Decimal("0")),
            source="resultado informado no balancete",
        )

    revenue_value = calculate_revenue(balance) if revenue is None else revenue
    expense_value = calculate_operating_expenses(balance) if expenses is None else expenses
    revenue_deductions = calculate_revenue_deductions(balance)
    return ProfitBasis(
        value=revenue_value - revenue_deductions - expense_value,
        source="estimativa: receita - deduções - custos/despesas",
    )


def calculate_revenue(balance: TrialBalance) -> Decimal:
    credit_revenue = _abs(balance.credito_por_grupo("receita"))
    if credit_revenue > 0:
        return credit_revenue
    return _abs(balance.total_por_grupo("receita"))


def calculate_operating_expenses(balance: TrialBalance) -> Decimal:
    return _abs(_debitos_por_grupos(balance, OPERATING_EXPENSE_GROUPS))


def calculate_revenue_deductions(balance: TrialBalance) -> Decimal:
    saldo_deductions = _abs(_saldos_por_grupos(balance, {"tributos_sobre_receita"}))
    if saldo_deductions > 0:
        return saldo_deductions
    return _abs(_debitos_por_grupos(balance, {"tributos_sobre_receita"}))


def calculate_tax_expense(balance: TrialBalance) -> Decimal:
    explicit_tax = calculate_revenue_deductions(balance) + _abs(_debitos_por_grupos(balance, TAX_EXPENSE_GROUPS))
    if explicit_tax > 0:
        return explicit_tax
    return _abs(balance.total_por_grupo(LEGACY_TAX_GROUP))


def calculate_tax_liability(balance: TrialBalance) -> Decimal:
    explicit_liability = _abs(_saldos_por_grupos(balance, TAX_LIABILITY_GROUPS))
    if explicit_liability > 0:
        return explicit_liability
    return _abs(balance.total_por_grupo(LEGACY_TAX_GROUP))


def calculate_advances(balance: TrialBalance) -> Decimal:
    return _abs(_saldos_por_grupos(balance, ADVANCE_GROUPS))


def calculate_suppliers(balance: TrialBalance) -> Decimal:
    return _abs(balance.total_por_grupo("fornecedores"))


def calculate_inventory(balance: TrialBalance) -> Decimal:
    return _abs(balance.total_por_grupo("estoques") + balance.total_por_grupo("estoque"))


def calculate_tax_credits(balance: TrialBalance) -> Decimal:
    return _abs(balance.total_por_grupo("creditos_fiscais"))


def calculate_cost_of_goods(balance: TrialBalance) -> Decimal:
    return _abs(balance.debito_por_grupo("custos"))


def calculate_profit_distribution(balance: TrialBalance) -> Decimal:
    total = Decimal("0")
    for account in balance.contas_por_grupo("lucros"):
        if account.debito > 0:
            total += account.debito
            continue
        text = account.conta.lower()
        if any(key in text for key in ("lucro", "dividendo", "jcp", "juros sobre capital")):
            if account.credito > 0:
                total += account.credito
            elif account.saldo_atual != 0:
                total += _abs(account.saldo_atual)
    return _abs(total)


def calculate_profit_distribution_capacity(balance: TrialBalance, profit_basis: ProfitBasis | None = None) -> Decimal:
    capacity = Decimal("0")
    for group in ("patrimonio", "patrimonio_liquido", "resultado"):
        for account in balance.contas_por_grupo(group):
            text = _normalize_text(account.conta)
            is_profit_account = any(key in text for key in ("lucro", "resultado", "reserva"))
            is_loss_account = "preju" in text
            if not is_profit_account and not is_loss_account:
                continue

            value = _abs(account.saldo_atual)
            if is_loss_account:
                capacity -= value
            else:
                capacity += value

    if profit_basis and profit_basis.value > 0:
        capacity = max(capacity, profit_basis.value)
    return max(capacity, Decimal("0"))


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
    annualized_revenue = rbt12_revenue if has_rbt12 else revenue * Decimal("4")
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


def _check_payroll_factor(revenue: Decimal, payroll: Decimal, ruleset: str = RULESET_SERVICOS) -> list[RuleFinding]:
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
                evidencia={"receita_trimestre": _money(revenue), "folha_pro_labore_trimestre": _money(payroll), "fator_r_trimestral_estimado": _percent(factor)},
                recomendacao="Revisar folha, pró-labore dos sócios e apuração do Fator R com base acumulada de 12 meses antes de concluir sobre o anexo aplicável.",
                normas_aplicaveis=("LC 123/2006", "art. 18° LC 123/2006"),
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


def _check_partner_accounts(revenue: Decimal, partners: Decimal) -> list[RuleFinding]:
    if revenue <= 0:
        return []

    cfg = get_rule_config("SN-005")
    lim = Decimal(str(cfg.get("limite_medio", 0.20)))
    ratio = partners / revenue
    if ratio > lim:
        return [
            RuleFinding(
                codigo="SN-005",
                titulo="Movimentações relevantes em contas de sócios",
                nivel=RiskLevel.MEDIO,
                pontuacao=cfg.get("pontuacao_medio", 18),
                descricao="Contas relacionadas a sócios têm saldo relevante em comparação à receita do trimestre.",
                evidencia={"receita": _money(revenue), "saldo_contas_socios": _money(partners), "percentual": _percent(ratio)},
                recomendacao="Classificar a natureza dos valores: mútuo, adiantamento, distribuição, reembolso ou despesa particular.",
                normas_aplicaveis=("LC 123/2006", "RIR/2018"),
            )
        ]

    return []


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
                    "limite_percentual_receita": _money(ratio_reference),
                    "referencia_aplicada": _money(reference),
                },
                recomendacao="Revisar adiantamentos a fornecedores, clientes, empregados e terceiros, documentando a origem, a contraprestação e a baixa esperada.",
                normas_aplicaveis=("NBC TG 1000", "ITG 2000"),
            )
        ]

    return []


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


def _check_inventory_position(revenue: Decimal, inventory: Decimal, cogs: Decimal) -> list[RuleFinding]:
    if inventory <= 0:
        return []

    cfg = get_rule_config("SN-015")
    absolute_limit = Decimal(str(cfg.get("limite_absoluto_sem_receita", 10000)))

    if revenue <= 0 and inventory > absolute_limit:
        return [
            RuleFinding(
                codigo="SN-015A",
                titulo="Estoque relevante sem receita registrada",
                nivel=RiskLevel.ALTO,
                pontuacao=cfg.get("pontuacao_alto", 24),
                descricao="A empresa apresenta saldo relevante de estoques sem receita registrada no trimestre.",
                evidencia={
                    "receita": _money(revenue),
                    "estoques": _money(inventory),
                    "limite_absoluto": _money(absolute_limit),
                },
                recomendacao="Validar inventario, notas fiscais de entrada e saida, baixas por venda, perdas e eventual receita nao reconhecida.",
                normas_aplicaveis=("LC 123/2006", "CPC 16 R1", "ITG 2000"),
            )
        ]

    if revenue <= 0:
        return []

    ratio = inventory / revenue
    lim_alto = Decimal(str(cfg.get("limite_alto_ratio", 2.0)))
    if ratio > lim_alto:
        return [
            RuleFinding(
                codigo="SN-015C",
                titulo="Estoque muito elevado em relacao a receita trimestral",
                nivel=RiskLevel.ALTO,
                pontuacao=cfg.get("pontuacao_alto", 24),
                descricao="O saldo de estoques supera parametro elevado em relacao a receita trimestral, indicando risco de inventario sem giro, baixa pendente ou classificacao inadequada.",
                evidencia={
                    "receita": _money(revenue),
                    "estoques": _money(inventory),
                    "cmv_custos": _money(cogs),
                    "percentual_sobre_receita": _percent(ratio),
                },
                recomendacao="Conciliar estoque contabil com inventario fisico, compras, notas fiscais de venda, perdas, devolucoes e criterios de avaliacao.",
                normas_aplicaveis=("LC 123/2006", "CPC 16 R1", "ITG 2000"),
            )
        ]

    lim_medio = Decimal(str(cfg.get("limite_medio_ratio", 1.0)))
    if ratio > lim_medio:
        return [
            RuleFinding(
                codigo="SN-015B",
                titulo="Estoque elevado em relacao a receita trimestral",
                nivel=RiskLevel.MEDIO,
                pontuacao=cfg.get("pontuacao_medio", 14),
                descricao="O saldo de estoques esta relevante em relacao a receita do trimestre e deve ser confrontado com o giro operacional.",
                evidencia={
                    "receita": _money(revenue),
                    "estoques": _money(inventory),
                    "cmv_custos": _money(cogs),
                    "percentual_sobre_receita": _percent(ratio),
                },
                recomendacao="Revisar inventario, compras do periodo, baixas por venda e composicao de itens sem giro.",
                normas_aplicaveis=("CPC 16 R1", "ITG 2000"),
            )
        ]

    return []


def _check_supplier_position(revenue: Decimal, suppliers: Decimal, inventory: Decimal) -> list[RuleFinding]:
    if suppliers <= 0:
        return []

    cfg = get_rule_config("SN-016")
    absolute_limit = Decimal(str(cfg.get("limite_absoluto_sem_receita", 10000)))

    if revenue <= 0 and suppliers > absolute_limit:
        return [
            RuleFinding(
                codigo="SN-016A",
                titulo="Fornecedores relevantes sem receita registrada",
                nivel=RiskLevel.MEDIO,
                pontuacao=cfg.get("pontuacao_medio", 14),
                descricao="Ha saldo relevante de fornecedores sem receita registrada no trimestre, exigindo conciliacao entre compras, estoques e operacao.",
                evidencia={
                    "receita": _money(revenue),
                    "fornecedores": _money(suppliers),
                    "estoques": _money(inventory),
                },
                recomendacao="Conciliar contas a pagar, notas fiscais de compra, estoque e eventual faturamento posterior.",
                normas_aplicaveis=("LC 123/2006", "ITG 2000"),
            )
        ]

    if revenue <= 0:
        return []

    ratio = suppliers / revenue
    lim_alto = Decimal(str(cfg.get("limite_alto_ratio", 1.5)))
    if ratio > lim_alto:
        return [
            RuleFinding(
                codigo="SN-016C",
                titulo="Fornecedores muito elevados em relacao a receita",
                nivel=RiskLevel.ALTO,
                pontuacao=cfg.get("pontuacao_alto", 22),
                descricao="O saldo de fornecedores e muito elevado em relacao a receita trimestral, podendo indicar passivo comercial sem baixa, compras sem giro ou erro de classificacao.",
                evidencia={
                    "receita": _money(revenue),
                    "fornecedores": _money(suppliers),
                    "estoques": _money(inventory),
                    "percentual_sobre_receita": _percent(ratio),
                },
                recomendacao="Conferir aging de fornecedores, documentos fiscais de compra, pagamentos posteriores e vinculo com estoque/CMV.",
                normas_aplicaveis=("NBC TG 1000", "ITG 2000"),
            )
        ]

    lim_medio = Decimal(str(cfg.get("limite_medio_ratio", 0.8)))
    if ratio > lim_medio:
        return [
            RuleFinding(
                codigo="SN-016B",
                titulo="Fornecedores elevados em relacao a receita",
                nivel=RiskLevel.MEDIO,
                pontuacao=cfg.get("pontuacao_medio", 14),
                descricao="O saldo de fornecedores esta relevante em relacao a receita trimestral e deve ser conciliado com compras e pagamentos.",
                evidencia={
                    "receita": _money(revenue),
                    "fornecedores": _money(suppliers),
                    "estoques": _money(inventory),
                    "percentual_sobre_receita": _percent(ratio),
                },
                recomendacao="Revisar composicao de fornecedores, notas fiscais, duplicatas pagas e mercadorias recebidas.",
                normas_aplicaveis=("NBC TG 1000", "ITG 2000"),
            )
        ]

    return []


def _check_tax_credits_simples(revenue: Decimal, tax_credits: Decimal) -> list[RuleFinding]:
    if tax_credits <= 0:
        return []

    cfg = get_rule_config("SN-017")
    absolute_limit = Decimal(str(cfg.get("limite_absoluto", 5000)))
    ratio_limit = Decimal(str(cfg.get("limite_ratio", 0.02)))
    ratio_reference = revenue * ratio_limit if revenue > 0 else Decimal("0")
    reference = max(absolute_limit, ratio_reference)

    if tax_credits <= reference:
        return []

    ratio = tax_credits / revenue if revenue > 0 else Decimal("0")
    return [
        RuleFinding(
            codigo="SN-017",
            titulo="Creditos fiscais relevantes em empresa do Simples Nacional",
            nivel=RiskLevel.MEDIO,
            pontuacao=cfg.get("pontuacao_medio", 16),
            descricao="Foram identificados creditos fiscais relevantes em empresa optante pelo Simples Nacional, exigindo validacao da natureza e recuperabilidade.",
            evidencia={
                "receita": _money(revenue),
                "creditos_fiscais": _money(tax_credits),
                "referencia_aplicada": _money(reference),
                "percentual_sobre_receita": _percent(ratio) if revenue > 0 else "0,0%",
            },
            recomendacao="Validar se os creditos decorrem de retencoes, ICMS-ST, ressarcimentos ou saldos recuperaveis documentados, evitando manter ativo fiscal sem suporte.",
            normas_aplicaveis=("LC 123/2006", "NBC TG 1000", "ITG 2000"),
        )
    ]


def _check_cogs_for_commerce(
    revenue: Decimal,
    inventory: Decimal,
    suppliers: Decimal,
    cogs: Decimal,
) -> list[RuleFinding]:
    if revenue <= 0:
        return []

    cfg = get_rule_config("SN-018")
    commerce_signal = inventory > 0 or suppliers > 0
    min_revenue = Decimal(str(cfg.get("receita_minima", 10000)))

    if commerce_signal and cogs <= 0 and revenue > min_revenue:
        return [
            RuleFinding(
                codigo="SN-018A",
                titulo="Receita de comercio sem CMV ou custo de mercadorias identificado",
                nivel=RiskLevel.ALTO,
                pontuacao=cfg.get("pontuacao_alto", 24),
                descricao="Ha receita e indicadores comerciais, mas nao foi identificado custo de mercadorias vendidas ou baixa equivalente no balancete.",
                evidencia={
                    "receita": _money(revenue),
                    "estoques": _money(inventory),
                    "fornecedores": _money(suppliers),
                    "cmv_custos": _money(cogs),
                },
                recomendacao="Verificar se as baixas de estoque/CMV foram contabilizadas por competencia e se as contas de custo foram classificadas corretamente.",
                normas_aplicaveis=("CPC 16 R1", "NBC TG 1000", "ITG 2000"),
            )
        ]

    if cogs <= 0:
        return []

    ratio = cogs / revenue
    lim_alto = Decimal(str(cfg.get("limite_alto_ratio", 0.95)))
    if ratio > lim_alto:
        return [
            RuleFinding(
                codigo="SN-018C",
                titulo="CMV muito elevado em relacao a receita",
                nivel=RiskLevel.ALTO,
                pontuacao=cfg.get("pontuacao_alto", 24),
                descricao="O custo de mercadorias representa percentual muito elevado da receita, indicando margem bruta insuficiente ou possivel classificacao indevida.",
                evidencia={
                    "receita": _money(revenue),
                    "cmv_custos": _money(cogs),
                    "percentual_cmv_receita": _percent(ratio),
                },
                recomendacao="Revisar precificacao, devolucoes, descontos, compras, criterio de custeio e classificacao entre custo e despesa.",
                normas_aplicaveis=("CPC 16 R1", "NBC TG 1000"),
            )
        ]

    lim_baixo = Decimal(str(cfg.get("limite_baixo_ratio", 0.30)))
    if commerce_signal and ratio < lim_baixo:
        return [
            RuleFinding(
                codigo="SN-018B",
                titulo="CMV baixo para operacao comercial com estoque ou fornecedores",
                nivel=RiskLevel.MEDIO,
                pontuacao=cfg.get("pontuacao_medio", 14),
                descricao="O custo de mercadorias esta baixo em relacao a receita diante de sinais de operacao comercial, exigindo validacao das baixas de estoque.",
                evidencia={
                    "receita": _money(revenue),
                    "cmv_custos": _money(cogs),
                    "estoques": _money(inventory),
                    "fornecedores": _money(suppliers),
                    "percentual_cmv_receita": _percent(ratio),
                },
                recomendacao="Conferir baixas de estoque, notas fiscais de saida, custo medio e eventual classificacao de custos em outras contas.",
                normas_aplicaveis=("CPC 16 R1", "ITG 2000"),
            )
        ]

    return []


def _check_commerce_sublimit(revenue: Decimal, rbt12_revenue: Decimal | None = None) -> list[RuleFinding]:
    if revenue <= 0:
        return []

    cfg = get_rule_config("SN-019")
    has_rbt12 = rbt12_revenue is not None and rbt12_revenue > 0
    annualized_revenue = rbt12_revenue if has_rbt12 else revenue * Decimal("4")
    base_calculo_limite = "RBT12 consolidado pelo historico" if has_rbt12 else "receita trimestral anualizada (receita x 4)"
    sublimite = Decimal(str(cfg.get("sublimite_anual", 3600000)))
    if annualized_revenue <= sublimite:
        return []

    return [
        RuleFinding(
            codigo="SN-019",
            titulo="Receita anualizada acima do sublimite de ICMS",
            nivel=RiskLevel.MEDIO,
            pontuacao=cfg.get("pontuacao_medio", 16),
            descricao="A receita trimestral anualizada supera o sublimite usado como alerta para ICMS fora do DAS em empresas comerciais.",
            evidencia={
                "receita_trimestre": _money(revenue),
                "receita_anualizada_estimativa": _money(annualized_revenue),
                "sublimite_anual": _money(sublimite),
                "base_calculo_limite": base_calculo_limite,
            },
            recomendacao="Validar a RBT12, sublimite estadual aplicavel, segregacao de receitas e eventual recolhimento de ICMS fora do DAS.",
            normas_aplicaveis=("LC 123/2006", "art. 20 LC 123/2006"),
        )
    ]


def _check_icms_st_attention(
    revenue: Decimal,
    inventory: Decimal,
    suppliers: Decimal,
    cogs: Decimal,
    tax_credits: Decimal,
) -> list[RuleFinding]:
    cfg = get_rule_config("SN-024")
    min_revenue = Decimal(str(cfg.get("receita_minima", 10000)))
    if revenue <= min_revenue:
        return []

    credit_ratio_limit = Decimal(str(cfg.get("limite_creditos_ratio", 0.01)))
    credit_ratio = tax_credits / revenue if revenue > 0 else Decimal("0")
    commercial_signal = inventory > 0 or suppliers > 0 or cogs > 0
    has_relevant_tax_credits = tax_credits > 0 and credit_ratio >= credit_ratio_limit

    if not commercial_signal or not has_relevant_tax_credits:
        return []

    return [
        RuleFinding(
            codigo="SN-024",
            titulo="Validacao de ICMS-ST e creditos fiscais em operacao comercial",
            nivel=RiskLevel.BAIXO,
            pontuacao=cfg.get("pontuacao_baixo", 6),
            descricao="Foram identificados creditos fiscais em contexto comercial, exigindo validacao documental de ICMS-ST, retencoes, ressarcimentos ou saldos recuperaveis.",
            evidencia={
                "receita": _money(revenue),
                "creditos_fiscais": _money(tax_credits),
                "percentual_sobre_receita": _percent(credit_ratio),
                "estoques": _money(inventory),
                "fornecedores": _money(suppliers),
                "cmv_custos": _money(cogs),
                "tipo_achado": "validacao_documental",
                "limitacao_dados": "Balancete nao contem NCM, CFOP, CST ou item fiscal; exige confronto com notas fiscais e PGDAS-D.",
            },
            recomendacao="Validar NCM, CFOP, mercadorias sujeitas a substituicao tributaria, documentos de compra/venda, ressarcimentos e suporte dos creditos fiscais antes de concluir sobre margem e DAS.",
            normas_aplicaveis=("LC 123/2006", "art. 20 LC 123/2006", "ITG 2000"),
        )
    ]


def _check_mixed_revenue_segregation(
    balance: TrialBalance,
    revenue: Decimal,
    payroll: Decimal,
    inventory: Decimal,
    suppliers: Decimal,
) -> list[RuleFinding]:
    if revenue <= 0:
        return []

    commerce_signal = inventory > 0 or suppliers > 0
    service_signal = payroll > 0 or _revenue_by_nature(balance, "servicos") > 0
    if not commerce_signal or not service_signal:
        return []

    service_revenue = _revenue_by_nature(balance, "servicos")
    commerce_revenue = _revenue_by_nature(balance, "comercio")
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
                "receita_total": _money(revenue),
                "receita_comercio_identificada": _money(commerce_revenue),
                "receita_servicos_identificada": _money(service_revenue),
                "receita_nao_segregada_estimativa": _percent(unsegregated_ratio),
                "estoques": _money(inventory),
                "fornecedores": _money(suppliers),
                "folha_pro_labore": _money(payroll),
            },
            recomendacao="Segregar receitas de comercio e servicos por conta contabil e documento fiscal, validando anexos, fator R, ISS/ICMS e calculo do DAS.",
            normas_aplicaveis=("LC 123/2006", "Anexos I e III/V da LC 123/2006", "ITG 2000"),
        )
    ]


def _apply_compound_rules(findings: list[RuleFinding]) -> list[RuleFinding]:
    compound: list[RuleFinding] = []
    codes = {f.codigo for f in findings}

    if any(c.startswith("SN-008") for c in codes) and "SN-007" in codes:
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

    if any(c.startswith("SN-015") for c in codes) and any(c.startswith("SN-018") for c in codes):
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

    if "SN-020" in codes and any(c.startswith("SN-002") for c in codes):
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


def _abs(value: Decimal) -> Decimal:
    return abs(value)


def _rbt12_decimal(context: dict | None, key: str) -> Decimal | None:
    if not context:
        return None
    value = context.get(key)
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _active_movement(balance: TrialBalance) -> Decimal:
    relevant_grupos = {"bancos", "caixa"}
    return sum(
        (account.debito + account.credito for account in balance.contas if account.grupo in relevant_grupos),
        Decimal("0"),
    )


def _operational_movement(balance: TrialBalance) -> Decimal:
    relevant_grupos = {"bancos", "caixa", "clientes"}
    return sum(
        (account.debito + account.credito for account in balance.contas if account.grupo in relevant_grupos),
        Decimal("0"),
    )


def _group_movement(balance: TrialBalance, group: str) -> Decimal:
    return sum(
        (account.debito + account.credito for account in balance.contas if account.grupo == group),
        Decimal("0"),
    )


def _debitos_por_grupos(balance: TrialBalance, groups: frozenset[str] | set[str]) -> Decimal:
    return sum((account.debito for account in balance.contas if account.grupo in groups), Decimal("0"))


def _saldos_por_grupos(balance: TrialBalance, groups: frozenset[str] | set[str]) -> Decimal:
    return sum((account.saldo_atual for account in balance.contas if account.grupo in groups), Decimal("0"))


def _revenue_by_nature(balance: TrialBalance, nature: str) -> Decimal:
    keywords = {
        "servicos": ("servico", "servicos", "prestacao", "honorario", "consultoria"),
        "comercio": ("venda", "mercadoria", "mercadorias", "produto", "produtos", "revenda"),
    }.get(nature, ())
    if not keywords:
        return Decimal("0")

    total = Decimal("0")
    for account in balance.contas_por_grupo("receita"):
        text = _normalize_text(account.conta)
        if not any(keyword in text for keyword in keywords):
            continue
        value = _abs(account.credito) if account.credito != 0 else _abs(account.saldo_atual)
        total += value
    return total


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


def _normalize_text(value: str) -> str:
    normalized = normalize("NFKD", value or "")
    return "".join(char for char in normalized if not combining(char)).lower()
