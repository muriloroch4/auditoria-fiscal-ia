from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CONFIG_PATH = _PROJECT_ROOT / "config" / "consultivo_por_regra.json"

_SEVERITY_TO_PRIORITY = {
    "alto": "alta",
    "alta": "alta",
    "medio": "media",
    "media": "media",
    "baixo": "baixa",
    "baixa": "baixa",
}


@lru_cache(maxsize=1)
def load_consultivo_config() -> dict[str, Any]:
    return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))


def consultivo_for_code(code: str, *, severity: str | None = None) -> dict[str, Any]:
    config = load_consultivo_config()
    defaults = config.get("defaults") or {}
    entry = _entry_for_code(code, config.get("por_prefixo") or [])
    priority = _priority_from_severity(severity)

    return {
        "prefixo": str(entry.get("prefixo") or ""),
        "matched": bool(entry),
        "documentos_necessarios": _as_list(
            entry.get("documentos_necessarios")
            or defaults.get("documentos_necessarios")
            or []
        ),
        "o_que_significa": str(
            entry.get("o_que_significa")
            or defaults.get("o_que_significa")
            or ""
        ),
        "como_solucionar": str(
            entry.get("como_solucionar")
            or defaults.get("como_solucionar")
            or ""
        ),
        "responsavel_sugerido": str(
            entry.get("responsavel_sugerido")
            or defaults.get("responsavel_sugerido")
            or ""
        ),
        "prazo_sugerido": str(
            entry.get("prazo_sugerido")
            or _deadline_from_defaults(defaults, priority)
        ),
    }


def documents_for_code(code: str) -> tuple[str, ...]:
    return tuple(consultivo_for_code(code).get("documentos_necessarios") or ())


def _entry_for_code(code: str, entries: list[dict[str, Any]]) -> dict[str, Any]:
    normalized_code = str(code or "")
    matches = [
        entry
        for entry in entries
        if normalized_code.startswith(str(entry.get("prefixo") or ""))
    ]
    return max(matches, key=lambda entry: len(str(entry.get("prefixo") or "")), default={})


def _priority_from_severity(severity: str | None) -> str:
    return _SEVERITY_TO_PRIORITY.get(str(severity or "").strip().lower(), "media")


def _deadline_from_defaults(defaults: dict[str, Any], priority: str) -> str:
    deadlines = defaults.get("prazo_por_severidade") or {}
    return str(deadlines.get(priority) or defaults.get("prazo_sugerido") or "")


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, tuple):
        return [str(item) for item in value]
    if value:
        return [str(value)]
    return []
