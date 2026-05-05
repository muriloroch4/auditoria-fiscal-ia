from __future__ import annotations

import json
import os
import ssl
from http.client import HTTPSConnection
from pathlib import Path
from typing import Any


_DEFAULT_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"
_DEFAULT_MAX_TOKENS = 2048
_API_HOST = "openrouter.ai"
_API_URL = "/api/v1/chat/completions"

_ENV_LOADED = False


def _load_env_file() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return

    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        _ENV_LOADED = True
        return

    try:
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key and key not in os.environ:
                        os.environ[key] = value
    except Exception:
        pass

    _ENV_LOADED = True


def call_openrouter(
    messages: list[dict[str, str]],
    *,
    api_key: str | None = None,
    model: str | None = None,
    max_tokens: int | None = None,
    timeout: int = 60,
) -> str:
    _load_env_file()

    key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        raise ValueError("OPENROUTER_API_KEY nao configurada.")

    model_name = model or os.environ.get("OPENROUTER_MODEL", _DEFAULT_MODEL)
    max_tok = max_tokens or int(os.environ.get("OPENROUTER_MAX_TOKENS", _DEFAULT_MAX_TOKENS))

    payload = {
        "model": model_name,
        "messages": messages,
        "max_tokens": max_tok,
        "temperature": 0.3,
    }

    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json; charset=utf-8",
        "Host": _API_HOST,
        "Content-Length": str(len(body)),
    }

    context = ssl.create_default_context()
    conn = HTTPSConnection(_API_HOST, timeout=timeout, context=context)
    try:
        conn.request("POST", _API_URL, body=body, headers=headers)
        response = conn.getresponse()
        raw = response.read().decode("utf-8")

        if response.status != 200:
            raise _api_error(raw, response.status)

        data = json.loads(raw)
        return _extract_content(data)
    finally:
        conn.close()


def _extract_content(response: dict[str, Any]) -> str:
    choices = response.get("choices")
    if not choices:
        raise ValueError("Resposta do OpenRouter sem choices.")

    message = choices[0].get("message", {})
    content = message.get("content", "")
    if not content:
        raise ValueError("Resposta do OpenRouter sem conteudo.")

    return content


def _api_error(raw: str, status: int) -> Exception:
    try:
        data = json.loads(raw)
        error_info = data.get("error", {})
        msg = error_info.get("message", raw)
        error_type = error_info.get("type", "api_error")
    except (json.JSONDecodeError, KeyError):
        msg = raw
        error_type = "unknown"

    return ConnectionError(f"OpenRouter API [{status}] ({error_type}): {msg}")


def is_api_key_configured(api_key: str | None = None) -> bool:
    _load_env_file()
    return bool((api_key or "").strip() or os.environ.get("OPENROUTER_API_KEY", "").strip())
