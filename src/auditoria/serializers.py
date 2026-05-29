from __future__ import annotations

import datetime
from typing import Any

from .config_loader import load_config
from .models import AuditResult, RuleFinding
from .risk import suggest_opinion_type
from .utils import format_brl


def audit_result_to_dict(result: AuditResult) -> dict[str, Any]:
    cfg = load_config()
    versao_regras = cfg.get("version", "1.0.0")

    findings = result.achados
    n_alto = sum(1 for f in findings if f.nivel.value == "alto")
    n_medio = sum(1 for f in findings if f.nivel.value == "medio")
    n_baixo = sum(1 for f in findings if f.nivel.value == "baixo")
    n_comp = sum(1 for f in findings if f.codigo.startswith("SN-COMP"))

    return {
        "_schema_version": "2.0.0",
        "meta": {
            "versao_schema": "2.0.0",
            "versao_regras": versao_regras,
            "conjunto_regras": _infer_conjunto(result.regime_tributario),
            "data_analise": datetime.datetime.now().isoformat(timespec="seconds"),
            "total_contas_analisadas": result.total_contas_analisadas,
            "total_regras_verificadas": result.total_regras_verificadas,
            "total_regras_acionadas": len(findings),
        },
        "identificacao": {
            "cliente": result.cliente,
            "cnpj": result.cnpj,
            "regime_tributario": result.regime_tributario,
            "periodo": result.periodo,
        },
        "risco": {
            "nivel_geral": result.nivel_geral.value,
            "pontuacao_total": result.pontuacao_total,
            "modalidade_opiniao_sugerida": suggest_opinion_type(result.nivel_geral, findings),
            "classificacao": {
                "achados_alto": n_alto,
                "achados_medio": n_medio,
                "achados_baixo": n_baixo,
                "achados_compostos": n_comp,
            },
            "explicacao_pontuacao": result.explicacao_pontuacao,
        },
        "metricas": _build_metricas_block(result),
        "achados": [_finding_to_dict(f) for f in findings],
        "contexto_regime": result.contexto_regime,
    }


def _build_metricas_block(result: AuditResult) -> dict[str, Any]:
    vals = result.metricas_valores
    fmts = result.resumo_metricas

    def _entry(key_val: str, key_fmt: str) -> dict[str, Any]:
        return {
            "valor": vals.get(key_val, 0.0),
            "formatado": fmts.get(key_fmt, format_brl(0)),
        }

    block: dict[str, Any] = {
        "receita_servicos": _entry("receita_servicos", "receita_servicos"),
        "tributos_a_recolher": _entry("tributos_a_recolher", "tributos"),
        "folha_pro_labore": _entry("folha_pro_labore", "folha_pro_labore"),
        "despesas_operacionais": _entry("despesas_operacionais", "despesas"),
        "lucros_distribuidos": _entry("lucros_distribuidos", "lucros_distribuidos"),
        "lucro_apurado_base": _entry("lucro_apurado_base", "lucro_apurado_base"),
        "caixa_e_bancos": _entry("caixa_e_bancos", "caixa_bancos"),
        "clientes_recebiveis": _entry("clientes_recebiveis", "clientes_recebiveis"),
        "origem_lucro_apurado": vals.get("origem_lucro_apurado", fmts.get("origem_lucro_apurado", "")),
    }

    if "indicadores_derivados" in vals:
        block["indicadores_derivados"] = vals["indicadores_derivados"]

    return block


def _finding_to_dict(finding: RuleFinding) -> dict[str, Any]:
    return {
        "codigo": finding.codigo,
        "titulo": finding.titulo,
        "nivel": finding.nivel.value,
        "pontuacao": finding.pontuacao,
        "descricao": finding.descricao,
        "evidencia": finding.evidencia,
        "recomendacao": finding.recomendacao,
        "normas_aplicaveis": list(finding.normas_aplicaveis),
    }


def _infer_conjunto(regime: str) -> str:
    mapa = {
        "simples nacional": "simples_servicos",
        "lucro presumido": "lucro_presumido",
        "lucro real": "lucro_real",
    }
    return mapa.get(regime.lower(), "simples_servicos")
