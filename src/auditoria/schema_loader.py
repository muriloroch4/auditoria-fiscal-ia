from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SCHEMA_DIR = _PROJECT_ROOT / "schemas"

_SCHEMA_FILES = {
    "trimestral": "auditoria_trimestral.v3.schema.json",
    "quarterly": "auditoria_trimestral.v3.schema.json",
    "anual": "auditoria_anual.v1.schema.json",
    "annual": "auditoria_anual.v1.schema.json",
}


def load_json_schema(name: str) -> dict[str, Any]:
    filename = _SCHEMA_FILES.get(name)
    if filename is None:
        raise ValueError(f"Schema desconhecido: {name}")

    path = _SCHEMA_DIR / filename
    return json.loads(path.read_text(encoding="utf-8"))


def available_json_schemas() -> dict[str, str]:
    return {
        "trimestral": str(_SCHEMA_DIR / _SCHEMA_FILES["trimestral"]),
        "anual": str(_SCHEMA_DIR / _SCHEMA_FILES["anual"]),
    }
