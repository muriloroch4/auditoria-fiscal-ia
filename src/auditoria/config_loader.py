from __future__ import annotations

import json
from pathlib import Path
from typing import Any


_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "rules.json"

_config_cache: dict[str, Any] | None = None
_config_cache_path: Path | None = None


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    global _config_cache, _config_cache_path
    config_path = Path(path) if path else _DEFAULT_CONFIG_PATH
    config_path = config_path.resolve()

    if _config_cache is not None and _config_cache_path == config_path:
        return _config_cache

    if not config_path.exists():
        _config_cache = _build_defaults()
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


def _build_defaults() -> dict[str, Any]:
    return {
        "version": "1.3.0",
        "limites_gerais": {
            "simples_anual": 4800000,
            "limite_movimentacao_ativa": 10000,
            "receita_baixa_ratio": 0.05,
        },
        "SN-001": {
            "limite_alto": 0.90,
            "pontuacao_alto": 35,
            "limite_medio": 0.70,
            "pontuacao_medio": 18,
        },
        "SN-002": {
            "limite_alto": 0.03,
            "pontuacao_alto": 20,
            "limite_medio": 0.055,
            "pontuacao_medio": 15,
        },
        "SN-003": {
            "limite_medio": 0.08,
            "pontuacao_medio": 14,
        },
        "SN-004": {
            "pontuacao_alto": 32,
            "limite_medio_ratio": 0.30,
            "pontuacao_medio": 16,
        },
        "SN-005": {
            "limite_medio": 0.20,
            "pontuacao_medio": 18,
        },
        "SN-006": {
            "pontuacao_alto": 28,
            "limite_medio_ratio": 0.60,
            "pontuacao_medio": 12,
        },
        "SN-007": {
            "limite_medio": 0.70,
            "pontuacao_medio": 16,
        },
        "SN-008": {
            "pontuacao_alto": 20,
        },
        "SN-009": {
            "pontuacao_alto": 25,
            "pontuacao_medio": 12,
            "limite_medio_ratio": 0.10,
        },
        "SN-010": {
            "limite_medio_ratio": 1.0,
            "pontuacao_medio": 12,
            "limite_alto_ratio": 2.0,
            "pontuacao_alto": 20,
        },
        "SN-011": {
            "pontuacao_medio": 12,
        },
        "SN-012": {
            "limite_medio": 0.50,
            "pontuacao_medio": 14,
        },
        "SN-013": {
            "limite_representacao": 0.15,
            "pontuacao_representacao": 10,
            "limite_veiculos": 0.10,
            "pontuacao_veiculos": 10,
        },
        "SN-014": {
            "limite_folha_receita": 0.10,
            "pontuacao_medio": 12,
        },
        "SN-COMP-01": {
            "pontuacao": 15,
        },
        "SN-COMP-02": {
            "pontuacao": 15,
        },
        "SN-COMP-03": {
            "pontuacao": 10,
        },
    }
