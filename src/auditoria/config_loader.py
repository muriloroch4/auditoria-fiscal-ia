from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config_defaults import (
    build_account_map_defaults,
    build_anexos_defaults,
    build_rules_defaults,
)


_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "rules.json"
_DEFAULT_ANEXOS_PATH = Path(__file__).resolve().parents[2] / "config" / "simples_anexos.json"
_DEFAULT_ACCOUNT_MAP_PATH = Path(__file__).resolve().parents[2] / "config" / "plano_contas_map.json"

_config_cache: dict[str, Any] | None = None
_config_cache_path: Path | None = None
_anexos_cache: dict[str, Any] | None = None
_anexos_cache_path: Path | None = None
_account_map_cache: dict[str, Any] | None = None
_account_map_cache_path: Path | None = None


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    global _config_cache, _config_cache_path
    config_path = Path(path) if path else _DEFAULT_CONFIG_PATH
    config_path = config_path.resolve()

    if _config_cache is not None and _config_cache_path == config_path:
        return _config_cache

    if not config_path.exists():
        _config_cache = build_rules_defaults()
        _config_cache_path = config_path
        return _config_cache

    with open(config_path, encoding="utf-8") as f:
        _config_cache = json.load(f)
    _config_cache_path = config_path
    return _config_cache


def reload_config(path: str | Path | None = None) -> dict[str, Any]:
    global _config_cache, _config_cache_path
    _config_cache = None
    _config_cache_path = None
    return load_config(path)


def get_rule_config(codigo: str) -> dict[str, Any]:
    cfg = load_config()
    return cfg.get(codigo, {})


def load_simples_anexos(path: str | Path | None = None) -> dict[str, Any]:
    global _anexos_cache, _anexos_cache_path
    anexos_path = Path(path) if path else _DEFAULT_ANEXOS_PATH
    anexos_path = anexos_path.resolve()

    if _anexos_cache is not None and _anexos_cache_path == anexos_path:
        return _anexos_cache

    if not anexos_path.exists():
        _anexos_cache = build_anexos_defaults()
        _anexos_cache_path = anexos_path
        return _anexos_cache

    with open(anexos_path, encoding="utf-8") as f:
        _anexos_cache = json.load(f)
    _anexos_cache_path = anexos_path
    return _anexos_cache


def load_account_map(path: str | Path | None = None) -> dict[str, Any]:
    global _account_map_cache, _account_map_cache_path
    account_map_path = Path(path) if path else _DEFAULT_ACCOUNT_MAP_PATH
    account_map_path = account_map_path.resolve()

    if _account_map_cache is not None and _account_map_cache_path == account_map_path:
        return _account_map_cache

    if not account_map_path.exists():
        _account_map_cache = build_account_map_defaults()
        _account_map_cache_path = account_map_path
        return _account_map_cache

    with open(account_map_path, encoding="utf-8") as f:
        _account_map_cache = json.load(f)
    _account_map_cache_path = account_map_path
    return _account_map_cache
