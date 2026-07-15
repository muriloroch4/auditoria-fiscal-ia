from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import RiskLevel, RuleFinding


@dataclass(frozen=True)
class RiskScore:
    nivel: RiskLevel
    pontuacao_total: int
    pontuacao_bruta: int
    pontuacao_maxima_aplicavel: int
    escala_pontuacao: str = "0 a 100"


def classify_total_risk(findings: list[RuleFinding]) -> tuple[RiskLevel, int]:
    score = sum(f.pontuacao for f in findings)

    if score >= 70 or any(f.nivel == RiskLevel.ALTO for f in findings):
        return RiskLevel.ALTO, score
    if score >= 30 or any(f.nivel == RiskLevel.MEDIO for f in findings):
        return RiskLevel.MEDIO, score
    return RiskLevel.BAIXO, score


def score_findings_0_100(findings: list[RuleFinding], max_applicable_score: int) -> RiskScore:
    raw_score = sum(f.pontuacao for f in findings)
    max_score = max(1, int(max_applicable_score or 0))

    if raw_score <= 0 or not findings:
        normalized = 0
    else:
        normalized = int((raw_score * 100 / max_score) + 0.5)

    if any(f.nivel == RiskLevel.MEDIO for f in findings):
        normalized = max(normalized, 30)
    if any(f.nivel == RiskLevel.ALTO for f in findings):
        normalized = max(normalized, 70)
    if any(f.codigo.startswith("SN-COMP") and f.nivel == RiskLevel.ALTO for f in findings):
        normalized = max(normalized, 75)

    normalized = max(0, min(100, normalized))

    if normalized >= 70:
        level = RiskLevel.ALTO
    elif normalized >= 30:
        level = RiskLevel.MEDIO
    else:
        level = RiskLevel.BAIXO

    return RiskScore(
        nivel=level,
        pontuacao_total=normalized,
        pontuacao_bruta=raw_score,
        pontuacao_maxima_aplicavel=max_score,
    )


def max_score_for_ruleset(config: dict[str, Any], ruleset: str) -> int:
    rule_codes = config.get("conjuntos_regras", {}).get(ruleset) or []
    if not rule_codes:
        rule_codes = [key for key in config if str(key).startswith("SN-")]
    return sum(max_score_for_rule(config.get(code, {})) for code in rule_codes)


def max_score_for_rule(rule_config: dict[str, Any]) -> int:
    if not rule_config:
        return 0
    if "pontuacao" in rule_config:
        return int(rule_config.get("pontuacao") or 0)

    severity_scores = [
        int(rule_config.get(key) or 0)
        for key in ("pontuacao_baixo", "pontuacao_medio", "pontuacao_alto")
        if key in rule_config
    ]
    independent_scores = [
        int(value or 0)
        for key, value in rule_config.items()
        if key.startswith("pontuacao_") and key not in {"pontuacao_baixo", "pontuacao_medio", "pontuacao_alto"}
    ]
    return (max(severity_scores) if severity_scores else 0) + sum(independent_scores)


def suggest_opinion_type(nivel: RiskLevel, findings: list[RuleFinding]) -> str:
    has_high_compound = any(f.codigo.startswith("SN-COMP") and f.nivel == RiskLevel.ALTO for f in findings)
    if nivel == RiskLevel.ALTO or has_high_compound:
        return "adversa"
    if nivel == RiskLevel.MEDIO:
        return "com_ressalva"
    return "sem_ressalva"
