from __future__ import annotations

import datetime
import re
from collections import Counter
from decimal import Decimal
from typing import Any

from .annual_consultivo import build_annual_consultivo
from .annual_findings import annual_findings, annual_score_explanation
from .annual_metrics import (
    annual_totals,
    missing_quarters,
    quarter_summary,
    rbt12_context as build_quarter_rbt12_context,
    safe_percent,
)
from .annual_report import generate_annual_markdown_report
from .schema_validator import SchemaValidationError, validate_payload_against_schema

ANNUAL_SCHEMA_VERSION = "annual-1.1.0"


def build_annual_comparison(quarterly_payloads: list[dict[str, Any]]) -> dict[str, Any]:
    if not quarterly_payloads:
        raise ValueError("Informe ao menos um JSON trimestral para consolidar o parecer anual.")
    _validate_formal_quarterly_payloads(quarterly_payloads)

    quarters = sorted((quarter_summary(payload) for payload in quarterly_payloads), key=lambda item: item["ordem"])
    rbt12 = build_quarter_rbt12_context(quarters)
    totals = annual_totals(quarters, rbt12)
    findings = annual_findings(quarters, totals)
    risk = _annual_risk(quarters, findings)
    identificacao = _annual_identification(quarters)
    evolution = _evolution_summary(quarters, totals, findings)

    payload = {
        "_schema_version": ANNUAL_SCHEMA_VERSION,
        "meta": {
            "versao_schema": ANNUAL_SCHEMA_VERSION,
            "data_analise": datetime.datetime.now().isoformat(timespec="seconds"),
            "total_trimestres_informados": len(quarters),
            "trimestres_ausentes": missing_quarters(quarters),
            "fontes": [q["periodo"] for q in quarters],
        },
        "identificacao": identificacao,
        "risco_anual": risk,
        "metricas_anual": totals,
        "comparativo_trimestral": quarters,
        "achados_anuais": findings,
        "resumo_evolucao": evolution,
        "consultivo": build_annual_consultivo(risk, totals, quarters, findings, evolution),
    }
    validate_payload_against_schema(payload, "anual")
    return payload


def _validate_formal_quarterly_payloads(quarterly_payloads: list[dict[str, Any]]) -> None:
    for index, payload in enumerate(quarterly_payloads, start=1):
        if not _is_formal_quarterly_payload(payload):
            continue
        formal_payload = _formal_quarterly_payload(payload)
        try:
            validate_payload_against_schema(formal_payload, "trimestral")
        except SchemaValidationError as exc:
            raise ValueError(f"JSON trimestral #{index} inválido para consolidação anual: {exc}") from exc


def _is_formal_quarterly_payload(payload: dict[str, Any]) -> bool:
    return "identificacao_empresa" in payload and "resumo_analise" in payload


def _formal_quarterly_payload(payload: dict[str, Any]) -> dict[str, Any]:
    keys = {
        "identificacao_empresa",
        "resumo_analise",
        "classificacao_contas",
        "principais_achados",
        "fundamentacao_tecnica_resumida",
        "conclusao_tecnica",
        "consultivo",
        "recomendacoes_tecnicas",
        "metadados",
    }
    return {key: payload[key] for key in keys if key in payload}


def build_rbt12_context(quarterly_payloads: list[dict[str, Any]]) -> dict[str, Any]:
    if not quarterly_payloads:
        return {}
    quarters = sorted((quarter_summary(payload) for payload in quarterly_payloads), key=lambda item: item["ordem"])
    return build_quarter_rbt12_context(quarters)




def _annual_risk(quarters: list[dict[str, Any]], findings: list[dict[str, Any]]) -> dict[str, Any]:
    score = sum(int(f["pontuacao"]) for f in findings) + max((q["pontuacao"] for q in quarters), default=0)
    has_high_quarter = any(q["risco"] == "alto" for q in quarters)
    has_high_finding = any(f["nivel"] == "alto" for f in findings)

    if has_high_finding or has_high_quarter or score >= 70:
        level = "alto"
        opinion = "adversa"
    elif findings or any(q["risco"] == "medio" for q in quarters) or score >= 30:
        level = "medio"
        opinion = "com_ressalva"
    else:
        level = "baixo"
        opinion = "sem_ressalva"

    return {
        "nivel_geral": level,
        "pontuacao_total": score,
        "modalidade_opiniao_sugerida": opinion,
        "explicacao_pontuacao": annual_score_explanation(quarters, findings, level, score),
        "classificacao": {
            "achados_alto": sum(1 for f in findings if f["nivel"] == "alto"),
            "achados_medio": sum(1 for f in findings if f["nivel"] == "medio"),
            "achados_baixo": sum(1 for f in findings if f["nivel"] == "baixo"),
        },
    }


def _annual_identification(quarters: list[dict[str, Any]]) -> dict[str, Any]:
    years = [year for q in quarters for year in re.findall(r"(?:19|20)\d{2}", q["periodo"])]
    year = Counter(years).most_common(1)[0][0] if years else "[VERIFICAR: exercício]"
    return {
        "cliente": _first_non_empty(q["cliente"] for q in quarters),
        "cnpj": _first_non_empty(q["cnpj"] for q in quarters),
        "regime_tributario": _first_non_empty(q["regime_tributario"] for q in quarters),
        "exercicio": year,
        "periodos_analisados": [q["periodo"] for q in quarters],
    }


def _evolution_summary(quarters: list[dict[str, Any]], totals: dict[str, Any], findings: list[dict[str, Any]]) -> dict[str, Any]:
    by_code = Counter(code for q in quarters for code in q["achados_codigos"])
    first_revenue = quarters[0]["metricas"]["receita_servicos"]
    last_revenue = quarters[-1]["metricas"]["receita_servicos"]
    best = max(quarters, key=lambda q: q["metricas"]["lucro_apurado_base"])
    worst = min(quarters, key=lambda q: q["metricas"]["lucro_apurado_base"])

    return {
        "variacao_receita_primeiro_ultimo": safe_percent(last_revenue - first_revenue, first_revenue),
        "variacao_pontuacao_primeiro_ultimo": safe_percent(
            Decimal(str(quarters[-1]["pontuacao"] - quarters[0]["pontuacao"])),
            Decimal(str(quarters[0]["pontuacao"] or 1)),
        ),
        "tendencia_risco": _risk_trend(quarters),
        "recorrencia_por_severidade": _recurrence_by_severity(quarters),
        "melhor_trimestre_resultado": best["trimestre"],
        "pior_trimestre_resultado": worst["trimestre"],
        "achados_recorrentes": [{"codigo": code, "trimestres": count} for code, count in sorted(by_code.items()) if count >= 2],
        "total_achados_anuais": len(findings),
        "receita_anual_formatada": totals["receita_servicos_total"]["formatado"],
        "resultado_anual_formatado": totals["lucro_apurado_total"]["formatado"],
    }


def _risk_trend(quarters: list[dict[str, Any]]) -> str:
    if len(quarters) < 2:
        return "insuficiente"
    rank = {"baixo": 1, "medio": 2, "alto": 3}
    first = rank.get(str(quarters[0].get("risco")).lower(), 1)
    last = rank.get(str(quarters[-1].get("risco")).lower(), 1)
    if last > first:
        return "piora"
    if last < first:
        return "melhora"
    return "estavel"


def _recurrence_by_severity(quarters: list[dict[str, Any]]) -> dict[str, int]:
    recurrent_codes = {
        code
        for code, count in Counter(code for q in quarters for code in q["achados_codigos"]).items()
        if count >= 2
    }
    result = {"alta": 0, "media": 0, "baixa": 0}
    for code in recurrent_codes:
        severity = _severity_for_code(quarters, code)
        if severity in result:
            result[severity] += 1
    return result


def _severity_for_code(quarters: list[dict[str, Any]], code: str) -> str:
    rank = {"alta": 3, "alto": 3, "media": 2, "medio": 2, "baixa": 1, "baixo": 1}
    best_label = "baixa"
    best_rank = 1
    for quarter in quarters:
        for finding in quarter.get("achados") or []:
            if str(finding.get("codigo") or "") != code:
                continue
            raw = str(finding.get("severidade") or finding.get("nivel") or "baixa").lower()
            current_rank = rank.get(raw, 1)
            if current_rank > best_rank:
                best_rank = current_rank
                best_label = "alta" if current_rank == 3 else "media" if current_rank == 2 else "baixa"
    return best_label





def _first_non_empty(values: Any) -> str:
    for value in values:
        if value:
            return str(value)
    return ""
