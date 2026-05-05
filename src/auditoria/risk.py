from __future__ import annotations

from .models import RiskLevel, RuleFinding


def classify_total_risk(findings: list[RuleFinding]) -> tuple[RiskLevel, int]:
    score = sum(f.pontuacao for f in findings)

    if score >= 70 or any(f.nivel == RiskLevel.ALTO for f in findings):
        return RiskLevel.ALTO, score
    if score >= 30 or any(f.nivel == RiskLevel.MEDIO for f in findings):
        return RiskLevel.MEDIO, score
    return RiskLevel.BAIXO, score
