from __future__ import annotations

from decimal import Decimal
from typing import Any

from .annual import build_rbt12_context
from .http_multipart import UploadedFile
from .storage import AuditStorage, infer_year_quarter


def form_text(form: dict[str, str | UploadedFile], field: str, default: str) -> str:
    value = form.get(field)
    return value.strip() if isinstance(value, str) and value.strip() else default


def query_text(query: dict[str, list[str]], field: str) -> str:
    values = query.get(field) or []
    value = values[0] if values else ""
    return str(value or "").strip()


def query_int(query: dict[str, list[str]], field: str) -> int | None:
    value = query_text(query, field)
    if not value:
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"O parâmetro '{field}' deve ser numérico.") from exc


def payload_int(payload: dict[str, Any], field: str) -> int | None:
    value = payload.get(field)
    if value in (None, ""):
        return None
    try:
        return int(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"O campo '{field}' deve ser numérico.") from exc


def saved_rbt12_context(storage: AuditStorage, cnpj: str, periodo: str) -> dict[str, Any]:
    if not cnpj:
        return {}
    ano, _ = infer_year_quarter(periodo)
    sources = storage.annual_sources(cnpj=cnpj, ano=ano)
    return build_rbt12_context(sources)


def json_default(value: Any) -> float:
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")
