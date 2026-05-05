from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..models import RiskLevel, RuleFinding, TrialBalance
from ..utils import format_brl, format_percent


SIMPLES_ANNUAL_LIMIT = Decimal("4800000")
QUARTERLY_LIMIT_REFERENCE = SIMPLES_ANNUAL_LIMIT / Decimal("4")


@dataclass(frozen=True)
class ProfitBasis:
    value: Decimal
    source: str


def analyze_simples_servicos(balance: TrialBalance) -> list[RuleFinding]:
    revenue = _abs(balance.credito_por_grupo("receita"))
    active_movement = _active_movement(balance)
    tax_balance = _abs(balance.total_por_grupo("tributos"))
    payroll = _abs(balance.debito_por_grupo("folha"))
    expenses = _abs(balance.debito_por_grupo("despesas"))
    partners = _abs(balance.total_por_grupo("socios"))
    profit_distribution = _abs(balance.debito_por_grupo("lucros"))
    profit_basis = calculate_profit_basis(balance, revenue, expenses)
    cash = balance.total_por_grupo("caixa") + balance.total_por_grupo("bancos")

    findings: list[RuleFinding] = []
    findings.extend(_check_low_or_missing_revenue(revenue, active_movement))
    findings.extend(_check_revenue_limit(revenue))
    findings.extend(_check_tax_ratio(revenue, tax_balance))
    findings.extend(_check_payroll_factor(revenue, payroll))
    findings.extend(_check_profit_distribution(revenue, profit_distribution, profit_basis))
    findings.extend(_check_partner_accounts(revenue, partners))
    findings.extend(_check_cash_position(revenue, cash))
    findings.extend(_check_expense_ratio(revenue, expenses))

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

    revenue_value = _abs(balance.credito_por_grupo("receita")) if revenue is None else revenue
    expense_value = _abs(balance.debito_por_grupo("despesas")) if expenses is None else expenses
    return ProfitBasis(
        value=revenue_value - expense_value,
        source="estimativa: receita - despesas",
    )


def _check_low_or_missing_revenue(revenue: Decimal, active_movement: Decimal) -> list[RuleFinding]:
    if active_movement < Decimal("10000"):
        return []

    if revenue <= 0:
        return [
            RuleFinding(
                codigo="SN-008A",
                titulo="Receita inexistente com movimentação ativa",
                nivel=RiskLevel.ALTO,
                pontuacao=20,
                descricao="A empresa apresenta movimentação contábil relevante, mas não possui receita registrada no periodo.",
                evidencia={"receita": _money(revenue), "movimentacao_ativa": _money(active_movement)},
                recomendacao="Verificar emissão de notas fiscais, reconhecimento de receita, classificação de entradas e possível tributação não apurada.",
            )
        ]

    ratio = revenue / active_movement
    if ratio < Decimal("0.05"):
        return [
            RuleFinding(
                codigo="SN-008B",
                titulo="Receita muito baixa com movimentação ativa",
                nivel=RiskLevel.ALTO,
                pontuacao=20,
                descricao="A receita registrada é muito baixa em relação à movimentação contábil ativa do período.",
                evidencia={
                    "receita": _money(revenue),
                    "movimentacao_ativa": _money(active_movement),
                    "percentual": _percent(ratio),
                },
                recomendacao="Investigar operação sem emissão fiscal, receitas classificadas incorretamente ou movimentações que deveriam compor faturamento.",
            )
        ]

    return []


def _check_revenue_limit(revenue: Decimal) -> list[RuleFinding]:
    if revenue >= QUARTERLY_LIMIT_REFERENCE * Decimal("0.90"):
        return [
            RuleFinding(
                codigo="SN-001B",
                titulo="Receita trimestral acima de 90% do limite proporcional do Simples",
                nivel=RiskLevel.ALTO,
                pontuacao=35,
                descricao="A receita do trimestre está próxima ou acima de 90% do limite proporcional anual do Simples Nacional.",
                evidencia={
                    "receita_trimestre": _money(revenue),
                    "referencia_trimestral": _money(QUARTERLY_LIMIT_REFERENCE),
                },
                recomendacao="Projetar a receita dos próximos trimestres e validar risco de sublimite, desenquadramento ou excesso de receita.",
            )
        ]

    if revenue >= QUARTERLY_LIMIT_REFERENCE * Decimal("0.70"):
        return [
            RuleFinding(
                codigo="SN-001A",
                titulo="Receita trimestral acima de 70% do limite proporcional do Simples",
                nivel=RiskLevel.MEDIO,
                pontuacao=18,
                descricao="A receita do trimestre já representa mais de 70% do limite proporcional anual do Simples Nacional.",
                evidencia={
                    "receita_trimestre": _money(revenue),
                    "referencia_trimestral": _money(QUARTERLY_LIMIT_REFERENCE),
                },
                recomendacao="Acompanhar receita acumulada dos últimos 12 meses e simular cenários de crescimento.",
            )
        ]

    return []


def _check_tax_ratio(revenue: Decimal, tax_balance: Decimal) -> list[RuleFinding]:
    if revenue <= 0:
        return []

    ratio = tax_balance / revenue
    if ratio < Decimal("0.03"):
        return [
            RuleFinding(
                codigo="SN-002B",
                titulo="Carga tributária abaixo de 3% da receita",
                nivel=RiskLevel.ALTO,
                pontuacao=20,
                descricao="Os impostos registrados representam menos de 3% da receita do período, indicando possível subapuração ou sonegação.",
                evidencia={"receita": _money(revenue), "tributos": _money(tax_balance), "percentual": _percent(ratio)},
                recomendacao="Conferir apuração do DAS, anexo aplicado, retenções, competência e possíveis lançamentos ausentes.",
            )
        ]

    if ratio < Decimal("0.055"):
        return [
            RuleFinding(
                codigo="SN-002A",
                titulo="Carga tributária abaixo de 5,5% da receita",
                nivel=RiskLevel.MEDIO,
                pontuacao=15,
                descricao="A relação entre tributos registrados e receita está em uma faixa que merece revisão.",
                evidencia={"receita": _money(revenue), "tributos": _money(tax_balance), "percentual": _percent(ratio)},
                recomendacao="Validar se todas as guias do trimestre foram reconhecidas e se houve retenções compensáveis.",
            )
        ]

    return []


def _check_payroll_factor(revenue: Decimal, payroll: Decimal) -> list[RuleFinding]:
    if revenue <= 0:
        return []

    factor = payroll / revenue
    if factor < Decimal("0.08"):
        return [
            RuleFinding(
                codigo="SN-003",
                titulo="Folha e pro-labore baixos para empresa de serviços",
                nivel=RiskLevel.MEDIO,
                pontuacao=14,
                descricao="A folha e o pro-labore representam percentual baixo da receita, o que pode afetar análises de atividade e fator R.",
                evidencia={"receita": _money(revenue), "folha_pro_labore": _money(payroll), "percentual": _percent(factor)},
                recomendacao="Revisar folha, pro-labore dos sócios e enquadramento no anexo aplicável ao serviço prestado.",
            )
        ]

    return []


def _check_profit_distribution(
    revenue: Decimal,
    profit_distribution: Decimal,
    profit_basis: ProfitBasis,
) -> list[RuleFinding]:
    if profit_distribution > profit_basis.value and profit_distribution > 0:
        return [
            RuleFinding(
                codigo="SN-004A",
                titulo="Distribuição de lucros acima do lucro apurado",
                nivel=RiskLevel.ALTO,
                pontuacao=32,
                descricao="A distribuição de lucros supera o lucro usado como base para a análise do período.",
                evidencia={
                    "lucro_apurado": _money(profit_basis.value),
                    "origem_lucro": profit_basis.source,
                    "lucros_distribuidos": _money(profit_distribution),
                },
                recomendacao="Validar escrituração completa, resultado do período e documentação de suporte antes de manter distribuição isenta.",
            )
        ]

    if revenue > 0 and profit_distribution / revenue > Decimal("0.30"):
        return [
            RuleFinding(
                codigo="SN-004B",
                titulo="Distribuição de lucros acima de 30% da receita",
                nivel=RiskLevel.MEDIO,
                pontuacao=16,
                descricao="A distribuição de lucros representa parcela relevante da receita do trimestre.",
                evidencia={"receita": _money(revenue), "lucros_distribuidos": _money(profit_distribution)},
                recomendacao="Conferir se há balancete regular e lucro contábil suficiente para suportar a distribuição.",
            )
        ]

    return []


def _check_partner_accounts(revenue: Decimal, partners: Decimal) -> list[RuleFinding]:
    if revenue <= 0:
        return []

    ratio = partners / revenue
    if ratio > Decimal("0.20"):
        return [
            RuleFinding(
                codigo="SN-005",
                titulo="Movimentações relevantes em contas de sócios",
                nivel=RiskLevel.MEDIO,
                pontuacao=18,
                descricao="Contas relacionadas a sócios têm saldo relevante em comparação à receita do trimestre.",
                evidencia={"receita": _money(revenue), "saldo_contas_socios": _money(partners), "percentual": _percent(ratio)},
                recomendacao="Classificar a natureza dos valores: mútuo, adiantamento, distribuição, reembolso ou despesa particular.",
            )
        ]

    return []


def _check_cash_position(revenue: Decimal, cash: Decimal) -> list[RuleFinding]:
    if cash < 0:
        return [
            RuleFinding(
                codigo="SN-006A",
                titulo="Saldo de caixa ou bancos negativo",
                nivel=RiskLevel.ALTO,
                pontuacao=28,
                descricao="O saldo combinado de caixa e bancos está negativo, indicando possível inconsistência contábil.",
                evidencia={"caixa_bancos": _money(cash)},
                recomendacao="Reconciliar extratos, lançamentos de caixa, contas de sócios e pagamentos não baixados.",
            )
        ]

    if revenue > 0 and cash / revenue > Decimal("0.60"):
        return [
            RuleFinding(
                codigo="SN-006B",
                titulo="Saldo de caixa e bancos acima de 60% da receita",
                nivel=RiskLevel.MEDIO,
                pontuacao=12,
                descricao="O saldo financeiro está alto em relação à receita trimestral, o que pode exigir conciliação detalhada.",
                evidencia={"receita": _money(revenue), "caixa_bancos": _money(cash), "percentual": _percent(cash / revenue)},
                recomendacao="Conferir conciliação bancária, caixa físico e valores recebidos ainda não classificados.",
            )
        ]

    return []


def _check_expense_ratio(revenue: Decimal, expenses: Decimal) -> list[RuleFinding]:
    if revenue <= 0:
        return []

    ratio = expenses / revenue
    if ratio > Decimal("0.70"):
        return [
            RuleFinding(
                codigo="SN-007",
                titulo="Despesas operacionais elevadas",
                nivel=RiskLevel.MEDIO,
                pontuacao=16,
                descricao="As despesas operacionais representam percentual elevado da receita de serviços.",
                evidencia={"receita": _money(revenue), "despesas": _money(expenses), "percentual": _percent(ratio)},
                recomendacao="Revisar despesas dedutíveis, gastos de sócios, documentos fiscais e coerência com a atividade.",
            )
        ]

    return []


def _abs(value: Decimal) -> Decimal:
    return abs(value)


def _active_movement(balance: TrialBalance) -> Decimal:
    relevant_grupos = {"bancos", "caixa", "clientes"}
    return sum(
        (account.debito + account.credito for account in balance.contas if account.grupo in relevant_grupos),
        Decimal("0"),
    )


_money = format_brl
_percent = format_percent
