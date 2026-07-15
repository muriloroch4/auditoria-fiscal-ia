from __future__ import annotations

from ..models import RuleFinding, TrialBalance
from .comercio import analyze_commerce_rules
from .compostas import apply_compound_rules
from .metricas import (
    ProfitBasis,
    calculate_profit_basis,
    calculate_profit_distribution_capacity,
    collect_simples_metrics,
)
from .fiscal import (
    check_low_or_missing_revenue,
    check_revenue_limit,
    check_tax_liability_growth,
    check_tax_ratio,
)
from .financeiro import (
    check_advances,
    check_cash_position,
    check_customer_advances,
    check_physical_cash_position,
    check_receivables,
    check_zero_receivables,
)
from .misto import check_mixed_revenue_segregation
from .patrimonial import check_inverse_account_nature, check_loans_without_interest_accrual
from .resultado import (
    check_accounting_loss,
    check_expense_ratio,
    check_high_profit_margin,
    check_missing_provisions,
    check_third_party_services_expense,
)
from .rulesets import (
    COMMERCE_RULESETS,
    RULESET_COMERCIO,
    RULESET_COMERCIO_SERVICOS,
    RULESET_SERVICOS,
    SERVICE_RULESETS,
    normalize_ruleset,
)
from .servicos import check_payroll_factor
from .societario import check_partner_accounts, check_profit_distribution

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
    findings.extend(check_low_or_missing_revenue(metrics.revenue, metrics.active_movement, metrics.operational_movement))
    findings.extend(check_revenue_limit(metrics.revenue, metrics.rbt12_revenue))
    findings.extend(check_tax_ratio(metrics.revenue, metrics.tax_expense, ruleset))
    if ruleset in SERVICE_RULESETS:
        findings.extend(check_payroll_factor(metrics.revenue, metrics.payroll, ruleset))
    findings.extend(
        check_profit_distribution(
            metrics.revenue,
            metrics.profit_distribution,
            profit_basis,
            profit_distribution_capacity,
        )
    )
    findings.extend(check_partner_accounts(metrics.revenue, metrics.partners, metrics.partner_accounts))
    findings.extend(check_receivables(metrics.revenue, metrics.clients, metrics.client_movement))
    findings.extend(check_zero_receivables(metrics.revenue, metrics.clients, metrics.client_movement))
    findings.extend(check_advances(metrics.revenue, metrics.advances))
    findings.extend(check_customer_advances(metrics.revenue, balance.contas_por_grupo("adiantamentos_clientes")))
    findings.extend(check_cash_position(metrics.revenue, metrics.cash))
    findings.extend(check_physical_cash_position(metrics.revenue, metrics.physical_cash, ruleset))
    findings.extend(check_expense_ratio(metrics.revenue, metrics.expenses, balance, ruleset))
    findings.extend(
        check_third_party_services_expense(
            metrics.third_party_services,
            metrics.expenses,
            metrics.third_party_service_accounts,
        )
    )
    findings.extend(check_accounting_loss(metrics.revenue, profit_basis))
    findings.extend(check_high_profit_margin(metrics.revenue, profit_basis))
    findings.extend(check_tax_liability_growth(balance, metrics.revenue))
    findings.extend(check_missing_provisions(metrics.revenue, metrics.payroll, balance))
    findings.extend(check_inverse_account_nature(metrics.revenue, balance))
    findings.extend(check_loans_without_interest_accrual(metrics.revenue, balance))
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
