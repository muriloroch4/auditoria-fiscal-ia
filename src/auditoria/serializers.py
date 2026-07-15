from __future__ import annotations

import datetime
from typing import Any

from .config_loader import load_config
from .models import AuditResult
from .risk import suggest_opinion_type
from .schema_validator import validate_payload_against_schema
from .serializer_common import (
    opinion_label,
    orientacao_por_opiniao,
    required,
    severity_counts,
    sorted_findings,
)
from .serializer_consultivo import consultivo_trimestral
from .serializer_sections import (
    finding_to_summary_dict,
    fundamentacao_resumida,
    normas_consolidadas,
    observacoes_tecnicas,
    principais_pontos,
    recomendacoes_tecnicas,
    texto_conclusivo,
)

SCHEMA_VERSION = "3.3.0"


def audit_result_to_dict(result: AuditResult) -> dict[str, Any]:
    cfg = load_config()
    findings = sorted_findings(result.achados)
    counts = severity_counts(findings)
    normas = normas_consolidadas(findings, result.regime_tributario)
    opinion = suggest_opinion_type(result.nivel_geral, findings)

    payload = {
        "identificacao_empresa": {
            "cnpj": required(result.cnpj),
            "regime_tributario": required(result.regime_tributario),
            "periodo_analisado": required(result.periodo),
        },
        "resumo_analise": {
            "empresa": required(result.cliente),
            "base_analise": "JSON de auditoria trimestral",
            "total_regras_verificadas": result.total_regras_verificadas,
            "total_regras_acionadas": len(findings),
            "risco_geral": result.nivel_geral.value,
            "pontuacao_total": result.pontuacao_total,
            "pontuacao_bruta": result.pontuacao_bruta,
            "pontuacao_maxima_aplicavel": result.pontuacao_maxima_aplicavel,
            "escala_pontuacao": result.escala_pontuacao,
            "achados_por_severidade": counts,
            "principais_pontos": principais_pontos(result, findings),
        },
        "classificacao_contas": result.classificacao_contas or {},
        "principais_achados": [finding_to_summary_dict(finding) for finding in findings],
        "fundamentacao_tecnica_resumida": {
            "normas_aplicaveis": normas,
            "texto_resumido": fundamentacao_resumida(result, normas),
            "observacoes_tecnicas": observacoes_tecnicas(result),
        },
        "conclusao_tecnica": {
            "risco_geral": result.nivel_geral.value,
            "conclusao_sugerida": opinion_label(opinion),
            "orientacao_consultiva": orientacao_por_opiniao(opinion),
            "ressalva_base_json": True,
            "necessita_validacao_documental": True,
            "texto_conclusivo": texto_conclusivo(result, opinion, findings),
        },
        "recomendacoes_tecnicas": recomendacoes_tecnicas(findings),
        "consultivo": consultivo_trimestral(result, findings, counts, opinion),
        "metadados": {
            "data_analise": datetime.datetime.now().isoformat(timespec="seconds"),
            "versao_schema": SCHEMA_VERSION,
            "versao_regras": cfg.get("version", "1.0.0"),
            "conjunto_regras": result.conjunto_regras,
        },
    }
    validate_payload_against_schema(payload, "trimestral")
    return payload
