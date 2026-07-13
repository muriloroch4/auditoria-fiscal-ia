from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from unicodedata import combining, normalize

from ..models import LedgerAccount, TrialBalance
from ..utils import format_brl

OPERATING_EXPENSE_GROUPS = frozenset({
    "despesas",
    "custos",
    "despesas_representacao",
    "despesas_veiculos",
    "despesas_tributarias",
    "multas_fiscais",
})
ADVANCE_GROUPS = frozenset({"adiantamentos"})
TAX_EXPENSE_GROUPS = frozenset({"despesas_tributarias"})
TAX_LIABILITY_GROUPS = frozenset({"tributos_a_recolher"})
LEGACY_TAX_GROUP = "tributos"


@dataclass(frozen=True)
class ProfitBasis:
    value: Decimal
    source: str


@dataclass(frozen=True)
class SimplesMetrics:
    revenue: Decimal
    active_movement: Decimal
    operational_movement: Decimal
    tax_expense: Decimal
    payroll: Decimal
    expenses: Decimal
    third_party_service_accounts: list[LedgerAccount]
    third_party_services: Decimal
    partner_accounts: list[LedgerAccount]
    partners: Decimal
    clients: Decimal
    client_movement: Decimal
    advances: Decimal
    profit_distribution: Decimal
    cash: Decimal
    physical_cash: Decimal
    suppliers: Decimal
    inventory: Decimal
    tax_credits: Decimal
    cogs: Decimal
    rbt12_revenue: Decimal | None


def collect_simples_metrics(balance: TrialBalance, rbt12_context: dict | None = None) -> SimplesMetrics:
    third_party_service_accounts = third_party_services_accounts(balance)
    third_party_services = sum(
        (_third_party_services_amount(account) for account in third_party_service_accounts),
        Decimal("0"),
    )
    partner_accounts = partner_related_accounts(balance)
    partners = sum((_partner_account_amount(account) for account in partner_accounts), Decimal("0"))

    return SimplesMetrics(
        revenue=calculate_revenue(balance),
        active_movement=_active_movement(balance),
        operational_movement=_operational_movement(balance),
        tax_expense=calculate_tax_expense(balance),
        payroll=_abs(balance.debito_por_grupo("folha")),
        expenses=calculate_operating_expenses(balance),
        third_party_service_accounts=third_party_service_accounts,
        third_party_services=third_party_services,
        partner_accounts=partner_accounts,
        partners=partners,
        clients=_abs(balance.total_por_grupo("clientes")),
        client_movement=_group_movement(balance, "clientes"),
        advances=calculate_advances(balance),
        profit_distribution=calculate_profit_distribution(balance),
        cash=balance.total_por_grupo("caixa") + balance.total_por_grupo("bancos"),
        physical_cash=_abs(balance.total_por_grupo("caixa")),
        suppliers=calculate_suppliers(balance),
        inventory=calculate_inventory(balance),
        tax_credits=calculate_tax_credits(balance),
        cogs=calculate_cost_of_goods(balance),
        rbt12_revenue=_rbt12_decimal(rbt12_context, "receita"),
    )


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


def calculate_third_party_services_expense(balance: TrialBalance) -> Decimal:
    return sum((_third_party_services_amount(account) for account in third_party_services_accounts(balance)), Decimal("0"))


def calculate_partner_accounts_balance(balance: TrialBalance) -> Decimal:
    return sum((_partner_account_amount(account) for account in partner_related_accounts(balance)), Decimal("0"))


def third_party_services_accounts(balance: TrialBalance) -> list[LedgerAccount]:
    return [
        account
        for account in balance.contas
        if _is_third_party_services_account(account.codigo, account.conta)
    ]


def partner_related_accounts(balance: TrialBalance) -> list[LedgerAccount]:
    return [
        account
        for account in balance.contas
        if _partner_account_amount(account) > 0 and _is_partner_related_account(account)
    ]


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


def calculate_customer_advances(balance: TrialBalance) -> Decimal:
    return _abs(_saldos_por_grupos(balance, {"adiantamentos_clientes"}))


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


def format_account_trace(accounts: list[LedgerAccount], limit: int = 6) -> str:
    if not accounts:
        return "Nenhuma conta individual identificada"

    items = [
        (
            f"{account.codigo} - {account.conta} "
            f"(grupo {account.grupo}; debito {format_brl(account.debito)}; "
            f"credito {format_brl(account.credito)}; saldo {format_brl(account.saldo_atual)})"
        )
        for account in accounts[:limit]
    ]
    if len(accounts) > limit:
        items.append(f"... mais {len(accounts) - limit} conta(s)")
    return " | ".join(items)


def revenue_by_nature(balance: TrialBalance, nature: str) -> Decimal:
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


def _third_party_services_amount(account: LedgerAccount) -> Decimal:
    amount = account.debito
    if amount <= 0 and account.saldo_atual != 0:
        amount = _abs(account.saldo_atual)
    elif amount <= 0 and account.credito > 0:
        amount = account.credito
    return _abs(amount)


def _partner_account_amount(account: LedgerAccount) -> Decimal:
    return _abs(account.saldo_atual)


def _is_partner_related_account(account: LedgerAccount) -> bool:
    code = str(account.codigo or "").strip()
    code_parts = "".join(char if char.isdigit() else " " for char in code).split()
    text = _normalize_text(account.conta)
    monitored_codes = {"616", "627", "770"}
    partner_keywords = (
        "socio",
        "socios",
        "administrador",
        "administradores",
        "pessoa ligada",
        "mutuo",
        "conta corrente socio",
        "emprestimo de socio",
        "adiantamento a socio",
    )
    return (
        account.grupo == "socios"
        or any(part.lstrip("0") in monitored_codes for part in code_parts)
        or any(keyword in text for keyword in partner_keywords)
    )


def _is_third_party_services_account(code: str, name: str) -> bool:
    text = _normalize_text(name)
    code_parts = "".join(char if char.isdigit() else " " for char in str(code or "")).split()
    code_matches = "325" in code_parts or str(code or "").strip() == "325"
    keywords = (
        "servicos prestados por terceiros",
        "servico prestado por terceiro",
        "servicos de terceiros",
        "servico de terceiro",
        "servicos terceiros",
        "terceirizacao",
        "terceirizados",
    )
    return code_matches or any(keyword in text for keyword in keywords)


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


def _abs(value: Decimal) -> Decimal:
    return abs(value)


def _normalize_text(value: str) -> str:
    normalized = normalize("NFKD", value or "")
    return "".join(char for char in normalized if not combining(char)).lower()
