from __future__ import annotations

from decimal import Decimal
from unicodedata import combining, normalize

from ..config_loader import get_rule_config
from ..models import LedgerAccount, RiskLevel, RuleFinding, TrialBalance
from ..utils import format_brl, format_percent
from .metricas import account_trace_materiality, format_account_trace

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


def check_inverse_account_nature(revenue: Decimal, balance: TrialBalance) -> list[RuleFinding]:
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


def check_loans_without_interest_accrual(revenue: Decimal, balance: TrialBalance) -> list[RuleFinding]:
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
