from __future__ import annotations

from typing import Any

from .models import AuditResult


def audit_result_to_annual_source(result: AuditResult) -> dict[str, Any]:
    return {
        "identificacao": {
            "cliente": result.cliente,
            "cnpj": result.cnpj,
            "regime_tributario": result.regime_tributario,
            "periodo": result.periodo,
        },
        "risco": {
            "nivel_geral": result.nivel_geral.value,
            "pontuacao_total": result.pontuacao_total,
            "pontuacao_bruta": result.pontuacao_bruta,
            "pontuacao_maxima_aplicavel": result.pontuacao_maxima_aplicavel,
            "escala_pontuacao": result.escala_pontuacao,
            "modalidade_opiniao_sugerida": "com_ressalva" if result.achados else "sem_ressalva",
        },
        "metricas": _annual_metric_entries(result),
        "achados": [
            {
                "codigo": finding.codigo,
                "titulo": finding.titulo,
                "nivel": finding.nivel.value,
                "pontuacao": finding.pontuacao,
                "descricao": finding.descricao,
                "evidencia": finding.evidencia,
                "recomendacao": finding.recomendacao,
                "normas_aplicaveis": list(finding.normas_aplicaveis),
            }
            for finding in result.achados
        ],
    }


def audit_result_to_dashboard_payload(result: AuditResult, summary_payload: dict[str, Any]) -> dict[str, Any]:
    """Return the formal quarterly JSON plus UI-only data for the local dashboard."""
    payload = dict(summary_payload)
    metricas = _annual_metric_entries(result)
    indicadores = result.metricas_valores.get("indicadores_derivados")
    if isinstance(indicadores, dict):
        metricas["indicadores_derivados"] = indicadores

    payload["dashboard"] = {
        "metricas": metricas,
        "contexto_regime": result.contexto_regime,
        "resumo_metricas": result.resumo_metricas,
        "meta": {
            "total_contas_analisadas": result.total_contas_analisadas,
            "total_regras_verificadas": result.total_regras_verificadas,
            "total_regras_acionadas": len(result.achados),
        },
    }
    return payload


def _annual_metric_entries(result: AuditResult) -> dict[str, dict[str, Any]]:
    metricas: dict[str, dict[str, Any]] = {}
    for key, value in result.metricas_valores.items():
        if key == "indicadores_derivados" or not isinstance(value, (int, float)):
            continue
        metricas[key] = {
            "valor": value,
            "formatado": result.resumo_metricas.get(key, str(value)),
        }
    return metricas
