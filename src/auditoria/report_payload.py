from __future__ import annotations

from typing import Any

from .models import AuditResult

_VERIFY_CNPJ = ""


def normalize_cnpj(cnpj: str | None) -> str:
    value = (cnpj or "").strip()
    return value or _VERIFY_CNPJ


def build_prompt_data(result: AuditResult, cnpj: str | None = None) -> dict[str, Any]:
    from .serializers import audit_result_to_dict

    payload = audit_result_to_dict(result)
    payload["identificacao_empresa"]["cnpj"] = normalize_cnpj(cnpj or result.cnpj)
    return payload
