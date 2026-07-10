from __future__ import annotations

from collections import Counter
from typing import Any

from .models import LedgerAccount, TrialBalance


REVIEW_CONFIDENCE = {"baixa"}
REPORT_ACCOUNT_LIMIT = 50


def build_account_classification_report(balance: TrialBalance) -> dict[str, Any]:
    accounts = balance.contas
    by_group = Counter(account.grupo or "outros" for account in accounts)
    by_origin = Counter(account.classificacao_origem or "nao_informado" for account in accounts)
    by_confidence = Counter(account.classificacao_confianca or "nao_informada" for account in accounts)
    review_accounts = [account for account in accounts if _needs_review(account)]

    return {
        "total_contas": len(accounts),
        "grupos_identificados": dict(sorted(by_group.items())),
        "classificacoes_por_origem": dict(sorted(by_origin.items())),
        "classificacoes_por_confianca": dict(sorted(by_confidence.items())),
        "total_contas_revisao": len(review_accounts),
        "limite_exibicao_contas": REPORT_ACCOUNT_LIMIT,
        "contas_revisao": [_account_to_dict(account) for account in review_accounts[:REPORT_ACCOUNT_LIMIT]],
        "amostra_classificacoes": [_account_to_dict(account) for account in accounts[:REPORT_ACCOUNT_LIMIT]],
    }


def _needs_review(account: LedgerAccount) -> bool:
    confidence = account.classificacao_confianca or ""
    observation = account.classificacao_observacao.lower()
    return (
        account.grupo == "outros"
        or confidence in REVIEW_CONFIDENCE
        or "sugeriu" in observation
        or "revisar" in observation
    )


def _account_to_dict(account: LedgerAccount) -> dict[str, str]:
    return {
        "codigo": account.codigo,
        "conta": account.conta,
        "grupo_atribuido": account.grupo,
        "grupo_original": account.grupo_original,
        "origem_classificacao": account.classificacao_origem or "nao_informado",
        "confianca": account.classificacao_confianca or "nao_informada",
        "observacao": account.classificacao_observacao,
    }
