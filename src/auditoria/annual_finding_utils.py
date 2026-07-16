from __future__ import annotations

from decimal import Decimal
from typing import Any

from .evidence import structured_evidence
from .utils import format_brl, format_percent


def trend_findings(quarters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(quarters) < 2:
        return []

    findings: list[dict[str, Any]] = []
    first = quarters[0]
    last = quarters[-1]
    first_score = Decimal(str(first.get("pontuacao") or 0))
    last_score = Decimal(str(last.get("pontuacao") or 0))
    first_revenue = first["metricas"]["receita_servicos"]
    last_revenue = last["metricas"]["receita_servicos"]
    risk_rank = {"baixo": 1, "medio": 2, "alto": 3}
    first_risk = risk_rank.get(str(first.get("risco")).lower(), 1)
    last_risk = risk_rank.get(str(last.get("risco")).lower(), 1)

    if last_risk > first_risk or (first_score > 0 and last_score >= first_score * Decimal("1.50")):
        findings.append(
            annual_finding(
                "AN-TEND-RIS-001",
                "Tendencia de piora no risco ao longo do ano",
                "medio",
                10,
                "O risco ou a pontuacao do ultimo trimestre piorou em relacao ao inicio do exercicio.",
                {
                    "risco_inicial": str(first.get("risco") or ""),
                    "risco_final": str(last.get("risco") or ""),
                    "pontuacao_inicial": str(int(first_score)),
                    "pontuacao_final": str(int(last_score)),
                },
                "Investigar causas da piora, priorizar achados recorrentes e acompanhar plano de acao no trimestre seguinte.",
            )
        )

    if first_revenue > 0 and last_revenue < first_revenue * Decimal("0.70"):
        findings.append(
            annual_finding(
                "AN-TEND-REC-001",
                "Queda relevante de receita entre o primeiro e o ultimo trimestre",
                "medio",
                10,
                "A receita do ultimo trimestre caiu mais de 30% em relacao ao primeiro trimestre informado.",
                {
                    "receita_inicial": format_brl(first_revenue),
                    "receita_final": format_brl(last_revenue),
                    "variacao": format_percent((last_revenue - first_revenue) / first_revenue),
                },
                "Validar sazonalidade, contratos, notas fiscais, cancelamentos e continuidade operacional antes da conclusao anual.",
            )
        )

    return findings

def annual_finding(
    code: str,
    title: str,
    level: str,
    score: int,
    description: str,
    evidence: dict[str, str],
    recommendation: str,
) -> dict[str, Any]:
    return {
        "codigo": code,
        "titulo": title,
        "nivel": level,
        "pontuacao": score,
        "descricao": description,
        "evidencia": structured_evidence(code, evidence, severity=level, source="json_trimestral_consolidado"),
        "recomendacao": recommendation,
        "normas_aplicaveis": [
            "NBC PG 100 (R1) de 2018",
            "NBC TA 700 (R1)",
            "NBC TG 26 (R3) = CPC 26 R1",
        ],
    }

def annual_score_explanation(
    quarters: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    level: str,
    score: int,
    raw_score: int,
    max_score: int,
) -> list[str]:
    explanations = [
        f"Nível anual {level} com pontuação consolidada de {score}/100.",
        f"Base anual bruta de {raw_score} ponto(s) sobre {max_score} ponto(s) máximos aplicáveis à escala anual.",
    ]
    if any(q["risco"] == "alto" for q in quarters):
        explanations.append("Ao menos um trimestre apresentou risco alto.")
    recurring = [f for f in findings if f["codigo"].startswith("AN-REC-")]
    if recurring:
        explanations.append(f"Foram identificados {len(recurring)} achado(s) recorrente(s).")
    if not findings:
        explanations.append("Não houve achados anuais adicionais além dos pareceres trimestrais.")
    return explanations
