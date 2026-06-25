from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

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


@dataclass(frozen=True)
class ProfitBasis:
    value: Decimal
    source: str


def analyze_simples_servicos(balance: TrialBalance, profit_basis: ProfitBasis | None = None) -> list[RuleFinding]:
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

    if profit_basis is None:
        profit_basis = calculate_profit_basis(balance, revenue, expenses)

    findings: list[RuleFinding] = []
    findings.extend(_check_low_or_missing_revenue(revenue, active_movement, _operational_movement(balance)))
    findings.extend(_check_revenue_limit(revenue))
    findings.extend(_check_tax_ratio(revenue, tax_expense))
    findings.extend(_check_payroll_factor(revenue, payroll))
    findings.extend(_check_profit_distribution(revenue, profit_distribution, profit_basis))
    findings.extend(_check_partner_accounts(revenue, partners))
    findings.extend(_check_receivables(revenue, clients, client_movement))
    findings.extend(_check_advances(revenue, advances))
    findings.extend(_check_cash_position(revenue, cash))
    findings.extend(_check_expense_ratio(revenue, expenses, balance))
    findings.extend(_check_accounting_loss(revenue, profit_basis))
    findings.extend(_check_tax_liability_growth(balance, revenue))
    findings.extend(_check_missing_provisions(revenue, payroll, balance))
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


def _check_revenue_limit(revenue: Decimal) -> list[RuleFinding]:
    cfg = get_rule_config("SN-001")
    anual = Decimal(str(load_config().get("limites_gerais", {}).get("simples_anual", 4800000)))
    quart_ref = anual / Decimal("4")

    lim_alto = Decimal(str(cfg.get("limite_alto", 0.90)))
    if revenue >= quart_ref * lim_alto:
        return [
            RuleFinding(
                codigo="SN-001B",
                titulo="Receita trimestral acima de 90% do limite proporcional do Simples",
                nivel=RiskLevel.ALTO,
                pontuacao=cfg.get("pontuacao_alto", 35),
                descricao="A receita do trimestre está próxima ou acima de 90% do limite proporcional anual do Simples Nacional.",
                evidencia={
                    "receita_trimestre": _money(revenue),
                    "referencia_trimestral": _money(quart_ref),
                },
                recomendacao="Projetar a receita dos próximos trimestres e validar risco de sublimite, desenquadramento ou excesso de receita.",
                normas_aplicaveis=("LC 123/2006", "art. 3° LC 123/2006", "LC 155/2016"),
            )
        ]

    lim_medio = Decimal(str(cfg.get("limite_medio", 0.70)))
    if revenue >= quart_ref * lim_medio:
        return [
            RuleFinding(
                codigo="SN-001A",
                titulo="Receita trimestral acima de 70% do limite proporcional do Simples",
                nivel=RiskLevel.MEDIO,
                pontuacao=cfg.get("pontuacao_medio", 18),
                descricao="A receita do trimestre já representa mais de 70% do limite proporcional anual do Simples Nacional.",
                evidencia={
                    "receita_trimestre": _money(revenue),
                    "referencia_trimestral": _money(quart_ref),
                },
                recomendacao="Acompanhar receita acumulada dos últimos 12 meses e simular cenários de crescimento.",
                normas_aplicaveis=("LC 123/2006", "art. 3° LC 123/2006", "LC 155/2016"),
            )
        ]

    return []


def _check_tax_ratio(revenue: Decimal, tax_expense: Decimal) -> list[RuleFinding]:
    if revenue <= 0:
        return []

    cfg = get_rule_config("SN-002")
    ratio = tax_expense / revenue

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
                normas_aplicaveis=("LC 123/2006", "Anexo III da LC 123/2006"),
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
                normas_aplicaveis=("LC 123/2006", "Anexo III da LC 123/2006"),
            )
        ]

    return []


def _check_payroll_factor(revenue: Decimal, payroll: Decimal) -> list[RuleFinding]:
    if revenue <= 0:
        return []

    cfg = get_rule_config("SN-003")
    lim = Decimal(str(cfg.get("limite_medio", 0.08)))
    factor = payroll / revenue
    if factor < lim:
        return [
            RuleFinding(
                codigo="SN-003",
                titulo="Folha e pro-labore baixos para empresa de serviços",
                nivel=RiskLevel.MEDIO,
                pontuacao=cfg.get("pontuacao_medio", 14),
                descricao="A folha e o pro-labore representam percentual baixo da receita, o que pode afetar análises de atividade e fator R.",
                evidencia={"receita": _money(revenue), "folha_pro_labore": _money(payroll), "percentual": _percent(factor)},
                recomendacao="Revisar folha, pro-labore dos sócios e enquadramento no anexo aplicável ao serviço prestado.",
                normas_aplicaveis=("LC 123/2006", "art. 18° LC 123/2006"),
            )
        ]

    return []


def _check_profit_distribution(
    revenue: Decimal,
    profit_distribution: Decimal,
    profit_basis: ProfitBasis,
) -> list[RuleFinding]:
    cfg = get_rule_config("SN-004")

    if profit_distribution > profit_basis.value and profit_distribution > 0:
        return [
            RuleFinding(
                codigo="SN-004A",
                titulo="Distribuição de lucros acima do lucro apurado",
                nivel=RiskLevel.ALTO,
                pontuacao=cfg.get("pontuacao_alto", 32),
                descricao="A distribuição de lucros supera o lucro usado como base para a análise do período.",
                evidencia={
                    "lucro_apurado": _money(profit_basis.value),
                    "origem_lucro": profit_basis.source,
                    "lucros_distribuidos": _money(profit_distribution),
                },
                recomendacao="Validar escrituração completa, resultado do período e documentação de suporte antes de manter distribuição isenta.",
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
                    evidencia={"receita": _money(revenue), "lucros_distribuidos": _money(profit_distribution)},
                    recomendacao="Conferir se há balancete regular e lucro contábil suficiente para suportar a distribuição.",
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
                descricao="O saldo de clientes e recebíveis permanece sem movimentação no período analisado, exigindo validação da composição e realização do crédito.",
                evidencia={"clientes_recebiveis": _money(clients), "movimentacao_clientes": _money(client_movement)},
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
                    descricao="O saldo de clientes e recebíveis é excessivamente elevado em relação à receita do período.",
                    evidencia={"receita": _money(revenue), "clientes_recebiveis": _money(clients), "percentual": _percent(ratio)},
                    recomendacao="Validar aging list, liquidação posterior dos títulos, baixa de recebíveis e critérios de reconhecimento de receita.",
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
                    descricao="O saldo de clientes e recebíveis é relevante em relação à receita do período.",
                    evidencia={"receita": _money(revenue), "clientes_recebiveis": _money(clients), "percentual": _percent(ratio)},
                    recomendacao="Validar aging list, liquidação posterior dos títulos, baixa de recebíveis e critérios de reconhecimento de receita.",
                    normas_aplicaveis=("NBC TG 1000", "ITG 2000"),
                )
            ]

    return []


def _check_advances(revenue: Decimal, advances: Decimal) -> list[RuleFinding]:
    if revenue <= 0 or advances <= 0:
        return []

    cfg = get_rule_config("SN-011")
    pts = cfg.get("pontuacao_medio", 12)
    reference = max(Decimal("10000"), revenue * Decimal("0.10"))
    if advances > reference:
        return [
            RuleFinding(
                codigo="SN-011A",
                titulo="Adiantamentos relevantes sem validação documental",
                nivel=RiskLevel.MEDIO,
                pontuacao=pts,
                descricao="Foram identificados saldos relevantes em adiantamentos, cuja permanência deve ser confrontada com contratos, notas fiscais e baixas posteriores.",
                evidencia={"adiantamentos": _money(advances), "referencia": _money(reference)},
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


def _check_expense_ratio(revenue: Decimal, expenses: Decimal, balance: TrialBalance) -> list[RuleFinding]:
    if revenue <= 0:
        return []

    findings: list[RuleFinding] = []

    cfg = get_rule_config("SN-007")
    lim = Decimal(str(cfg.get("limite_medio", 0.70)))
    ratio = expenses / revenue
    if ratio > lim:
        findings.append(
            RuleFinding(
                codigo="SN-007",
                titulo="Despesas operacionais elevadas",
                nivel=RiskLevel.MEDIO,
                pontuacao=cfg.get("pontuacao_medio", 16),
                descricao="As despesas operacionais representam percentual elevado da receita de serviços.",
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

    return compound


def _abs(value: Decimal) -> Decimal:
    return abs(value)


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
