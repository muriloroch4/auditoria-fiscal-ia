from __future__ import annotations

from unicodedata import combining, normalize


RULESET_SERVICOS = "simples_servicos"
RULESET_COMERCIO = "simples_comercio"
RULESET_COMERCIO_SERVICOS = "simples_comercio_servicos"

SERVICE_RULESETS = frozenset({RULESET_SERVICOS, RULESET_COMERCIO_SERVICOS})
COMMERCE_RULESETS = frozenset({RULESET_COMERCIO, RULESET_COMERCIO_SERVICOS})

_RULESET_ALIASES = {
    "servico": RULESET_SERVICOS,
    "servicos": RULESET_SERVICOS,
    "serviços": RULESET_SERVICOS,
    "simples_servicos": RULESET_SERVICOS,
    "simples_serviços": RULESET_SERVICOS,
    "comercio": RULESET_COMERCIO,
    "comércio": RULESET_COMERCIO,
    "simples_comercio": RULESET_COMERCIO,
    "simples_comércio": RULESET_COMERCIO,
    "misto": RULESET_COMERCIO_SERVICOS,
    "mista": RULESET_COMERCIO_SERVICOS,
    "comercio_servicos": RULESET_COMERCIO_SERVICOS,
    "comércio_serviços": RULESET_COMERCIO_SERVICOS,
    "comercio e servicos": RULESET_COMERCIO_SERVICOS,
    "comércio e serviços": RULESET_COMERCIO_SERVICOS,
    "simples_comercio_servicos": RULESET_COMERCIO_SERVICOS,
    "simples_comércio_serviços": RULESET_COMERCIO_SERVICOS,
}


def normalize_ruleset(value: str | None = None) -> str:
    normalized = _normalize_text(value or RULESET_SERVICOS).replace("-", "_").replace("/", " ")
    normalized = " ".join(normalized.replace("_", " ").split())
    direct_key = normalized.replace(" ", "_")
    return _RULESET_ALIASES.get(normalized) or _RULESET_ALIASES.get(direct_key) or RULESET_SERVICOS


def _normalize_text(value: str) -> str:
    normalized = normalize("NFKD", value or "")
    return "".join(char for char in normalized if not combining(char)).lower()
