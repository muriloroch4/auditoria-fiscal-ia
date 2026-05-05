from __future__ import annotations

from .models import AuditResult, RuleFinding


def audit_result_to_dict(result: AuditResult, report_markdown: str | None = None) -> dict:
    payload = {
        "cliente": result.cliente,
        "periodo": result.periodo,
        "nivel_geral": result.nivel_geral.value,
        "pontuacao_total": result.pontuacao_total,
        "explicacao_pontuacao": result.explicacao_pontuacao,
        "resumo_metricas": result.resumo_metricas,
        "achados": [_finding_to_dict(finding) for finding in result.achados],
    }

    if report_markdown is not None:
        payload["relatorio_markdown"] = report_markdown

    return payload


def _finding_to_dict(finding: RuleFinding) -> dict:
    return {
        "codigo": finding.codigo,
        "titulo": finding.titulo,
        "nivel": finding.nivel.value,
        "pontuacao": finding.pontuacao,
        "descricao": finding.descricao,
        "evidencia": finding.evidencia,
        "recomendacao": finding.recomendacao,
    }
