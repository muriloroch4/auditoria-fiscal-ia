from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from .models import AuditResult
from .report_local import generate_local_report
from .report_payload import build_prompt_data, normalize_cnpj

_logger = logging.getLogger(__name__)
_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"


def generate_markdown_report(
    result: AuditResult,
    *,
    use_ai: bool = True,
    api_key: str | None = None,
    cnpj: str | None = None,
) -> str:
    cnpj = normalize_cnpj(cnpj or result.cnpj)
    if use_ai:
        try:
            return _generate_ai_report(result, api_key=api_key, cnpj=cnpj)
        except Exception:
            _logger.warning(
                "Falha ao gerar relatório via IA. Usando relatório padrão.",
                exc_info=True,
            )
    return generate_local_report(result, cnpj=cnpj)


def _generate_ai_report(
    result: AuditResult,
    *,
    api_key: str | None = None,
    cnpj: str | None = None,
) -> str:
    from .ai_client import call_openrouter

    prompt_data = build_prompt_data(result, cnpj=cnpj)
    user_message = _format_user_message(prompt_data)
    messages = [
        {"role": "system", "content": _system_prompt()},
        {"role": "user", "content": user_message},
    ]
    return call_openrouter(messages, api_key=api_key)


def _format_user_message(data: dict[str, Any]) -> str:
    return (
        "Redija o relatório consultivo trimestral seguindo exatamente o system prompt. "
        "Use exclusivamente o JSON abaixo como entrada.\n\n"
        "```json\n"
        f"{json.dumps(data, ensure_ascii=False, indent=2)}\n"
        "```"
    )


def _system_prompt() -> str:
    return _load_prompt("relatorio_trimestral.md")


@lru_cache(maxsize=None)
def _load_prompt(filename: str) -> str:
    return (_PROMPTS_DIR / filename).read_text(encoding="utf-8").strip()
