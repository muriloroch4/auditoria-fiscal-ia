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
        "version": "1.4.1",
        "limites_gerais": {
            "simples_anual": 4800000,
            "limite_movimentacao_ativa": 10000,
            "receita_baixa_ratio": 0.05,
        },
        "conjuntos_regras": {
            "simples_servicos": [
                "SN-001", "SN-002", "SN-003", "SN-004", "SN-005", "SN-006", "SN-007",
                "SN-008", "SN-009", "SN-010", "SN-011", "SN-012", "SN-013", "SN-014",
                "SN-021", "SN-022", "SN-023",
                "SN-COMP-01", "SN-COMP-02", "SN-COMP-03",
            ],
            "simples_comercio": [
                "SN-001", "SN-002", "SN-004", "SN-005", "SN-006", "SN-007",
                "SN-008", "SN-009", "SN-010", "SN-011", "SN-012", "SN-013", "SN-014",
                "SN-015", "SN-016", "SN-017", "SN-018", "SN-019",
                "SN-021", "SN-022", "SN-023",
                "SN-COMP-01", "SN-COMP-02", "SN-COMP-03", "SN-COMP-04",
            ],
            "simples_comercio_servicos": [
                "SN-001", "SN-002", "SN-003", "SN-004", "SN-005", "SN-006", "SN-007",
                "SN-008", "SN-009", "SN-010", "SN-011", "SN-012", "SN-013", "SN-014",
                "SN-015", "SN-016", "SN-017", "SN-018", "SN-019", "SN-020",
                "SN-021", "SN-022", "SN-023",
                "SN-COMP-01", "SN-COMP-02", "SN-COMP-03", "SN-COMP-04", "SN-COMP-05",
            ],
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
            "limite_ratio": 0.10,
            "limite_absoluto": 10000,
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
        "SN-015": {
            "limite_absoluto_sem_receita": 10000,
            "limite_medio_ratio": 1.0,
            "pontuacao_medio": 14,
            "limite_alto_ratio": 2.0,
            "pontuacao_alto": 24,
        },
        "SN-016": {
            "limite_absoluto_sem_receita": 10000,
            "limite_medio_ratio": 0.8,
            "pontuacao_medio": 14,
            "limite_alto_ratio": 1.5,
            "pontuacao_alto": 22,
        },
        "SN-017": {
            "limite_absoluto": 5000,
            "limite_ratio": 0.02,
            "pontuacao_medio": 16,
        },
        "SN-018": {
            "receita_minima": 10000,
            "limite_baixo_ratio": 0.30,
            "pontuacao_medio": 14,
            "limite_alto_ratio": 0.95,
            "pontuacao_alto": 24,
        },
        "SN-019": {
            "sublimite_anual": 3600000,
            "pontuacao_medio": 16,
        },
        "SN-020": {
            "tolerancia_receita_nao_segregada": 0.20,
            "pontuacao_medio": 18,
        },
        "SN-021": {
            "referencia_presuncao_servicos": 0.32,
            "limite_baixo_ratio": 0.45,
            "pontuacao_baixo": 6,
            "limite_medio_ratio": 0.64,
            "pontuacao_medio": 12,
        },
        "SN-022": {
            "limite_servicos_absoluto": 3000,
            "limite_servicos_ratio": 0.02,
            "limite_comercio_absoluto": 10000,
            "limite_comercio_ratio": 0.05,
            "multiplicador_alto": 3,
            "pontuacao_medio": 12,
            "pontuacao_alto": 18,
        },
        "SN-023": {
            "receita_minima": 200000,
            "pontuacao_baixo": 6,
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
        "SN-COMP-04": {
            "pontuacao": 15,
        },
        "SN-COMP-05": {
            "pontuacao": 15,
        },
    }
