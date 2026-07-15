from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from .utils import format_brl, format_percent

SIMPLES_ANNUAL_LIMIT = Decimal("4800000")

def quarter_summary(payload: dict[str, Any]) -> dict[str, Any]:
    if "identificacao_empresa" in payload and "resumo_analise" in payload:
        identificacao = payload.get("identificacao_empresa", {})
        resumo = payload.get("resumo_analise", {})
        conclusao = payload.get("conclusao_tecnica", {})
        achados = payload.get("principais_achados", [])
        metricas = payload.get("metricas", {})
        periodo = str(identificacao.get("periodo_analisado") or "[VERIFICAR: período]")
        trimestre = quarter_label(periodo)

        return {
            "trimestre": trimestre,
            "ordem": quarter_order(trimestre, periodo),
            "periodo": periodo,
            "cliente": resumo.get("empresa", ""),
            "cnpj": identificacao.get("cnpj", ""),
            "regime_tributario": identificacao.get("regime_tributario", ""),
            "risco": resumo.get("risco_geral") or conclusao.get("risco_geral") or "baixo",
            "pontuacao": int(resumo.get("pontuacao_total") or 0),
            "pontuacao_bruta": int(resumo.get("pontuacao_bruta") or resumo.get("pontuacao_total") or 0),
            "pontuacao_maxima_aplicavel": int(resumo.get("pontuacao_maxima_aplicavel") or 100),
            "escala_pontuacao": str(resumo.get("escala_pontuacao") or "0 a 100"),
            "modalidade_opiniao_sugerida": opinion_code(conclusao.get("conclusao_sugerida", "sem ressalva")),
            "metricas": {
                "receita_servicos": metric_value(metricas, "receita_servicos"),
                "deducoes_receita": metric_value(metricas, "deducoes_receita"),
                "tributos_registrados": metric_value(metricas, "tributos_registrados"),
                "tributos_a_recolher": metric_value(metricas, "tributos_a_recolher"),
                "folha_pro_labore": metric_value(metricas, "folha_pro_labore"),
                "despesas_operacionais": metric_value(metricas, "despesas_operacionais"),
                "servicos_terceiros": metric_value(metricas, "servicos_terceiros"),
                "saldo_contas_socios": metric_value(metricas, "saldo_contas_socios"),
                "lucros_distribuidos": metric_value(metricas, "lucros_distribuidos"),
                "lucro_apurado_base": metric_value(metricas, "lucro_apurado_base"),
                "caixa_e_bancos": metric_value(metricas, "caixa_e_bancos"),
                "clientes_recebiveis": metric_value(metricas, "clientes_recebiveis"),
                "adiantamentos": metric_value(metricas, "adiantamentos"),
                "adiantamentos_clientes": metric_value(metricas, "adiantamentos_clientes"),
                "emprestimos": metric_value(metricas, "emprestimos"),
                "fornecedores": metric_value(metricas, "fornecedores"),
                "estoques": metric_value(metricas, "estoques"),
                "cmv_custos": metric_value(metricas, "cmv_custos"),
                "creditos_fiscais": metric_value(metricas, "creditos_fiscais"),
            },
            "achados": achados,
            "achados_codigos": [str(item.get("codigo", "")) for item in achados if item.get("codigo")],
        }

    identificacao = payload.get("identificacao", {})
    metricas = payload.get("metricas", {})
    risco = payload.get("risco", {})
    achados = payload.get("achados", [])
    periodo = str(identificacao.get("periodo") or "[VERIFICAR: período]")
    trimestre = quarter_label(periodo)

    return {
        "trimestre": trimestre,
        "ordem": quarter_order(trimestre, periodo),
        "periodo": periodo,
        "cliente": identificacao.get("cliente", ""),
        "cnpj": identificacao.get("cnpj", ""),
        "regime_tributario": identificacao.get("regime_tributario", ""),
        "risco": risco.get("nivel_geral", "baixo"),
        "pontuacao": int(risco.get("pontuacao_total") or 0),
        "pontuacao_bruta": int(risco.get("pontuacao_bruta") or risco.get("pontuacao_total") or 0),
        "pontuacao_maxima_aplicavel": int(risco.get("pontuacao_maxima_aplicavel") or 100),
        "escala_pontuacao": str(risco.get("escala_pontuacao") or "0 a 100"),
        "modalidade_opiniao_sugerida": risco.get("modalidade_opiniao_sugerida", "sem_ressalva"),
        "metricas": {
            "receita_servicos": metric_value(metricas, "receita_servicos"),
            "deducoes_receita": metric_value(metricas, "deducoes_receita"),
            "tributos_registrados": metric_value(metricas, "tributos_registrados"),
            "tributos_a_recolher": metric_value(metricas, "tributos_a_recolher"),
            "folha_pro_labore": metric_value(metricas, "folha_pro_labore"),
            "despesas_operacionais": metric_value(metricas, "despesas_operacionais"),
            "servicos_terceiros": metric_value(metricas, "servicos_terceiros"),
            "saldo_contas_socios": metric_value(metricas, "saldo_contas_socios"),
            "lucros_distribuidos": metric_value(metricas, "lucros_distribuidos"),
            "lucro_apurado_base": metric_value(metricas, "lucro_apurado_base"),
            "caixa_e_bancos": metric_value(metricas, "caixa_e_bancos"),
            "clientes_recebiveis": metric_value(metricas, "clientes_recebiveis"),
            "adiantamentos": metric_value(metricas, "adiantamentos"),
            "adiantamentos_clientes": metric_value(metricas, "adiantamentos_clientes"),
            "emprestimos": metric_value(metricas, "emprestimos"),
            "fornecedores": metric_value(metricas, "fornecedores"),
            "estoques": metric_value(metricas, "estoques"),
            "cmv_custos": metric_value(metricas, "cmv_custos"),
            "creditos_fiscais": metric_value(metricas, "creditos_fiscais"),
        },
        "achados": achados,
        "achados_codigos": [str(item.get("codigo", "")) for item in achados if item.get("codigo")],
    }


def annual_totals(quarters: list[dict[str, Any]], rbt12_context: dict[str, Any] | None = None) -> dict[str, Any]:
    last = quarters[-1]

    def sum_metric(key: str) -> Decimal:
        return sum((q["metricas"][key] for q in quarters), Decimal("0"))

    revenue = sum_metric("receita_servicos")
    deductions = sum_metric("deducoes_receita")
    taxes = sum_metric("tributos_registrados")
    expenses = sum_metric("despesas_operacionais")
    third_party_services = sum_metric("servicos_terceiros")
    payroll = sum_metric("folha_pro_labore")
    profit = sum_metric("lucro_apurado_base")
    profit_distribution = sum_metric("lucros_distribuidos")
    cogs = sum_metric("cmv_custos")
    partner_accounts = last["metricas"]["saldo_contas_socios"]
    debt = last["metricas"]["emprestimos"]
    tax_liability = last["metricas"]["tributos_a_recolher"]
    suppliers = last["metricas"]["fornecedores"]
    inventory = last["metricas"]["estoques"]
    tax_credits = last["metricas"]["creditos_fiscais"]

    result = {
        "receita_servicos_total": metric_entry(revenue),
        "deducoes_receita_total": metric_entry(deductions),
        "tributos_registrados_total": metric_entry(taxes),
        "folha_pro_labore_total": metric_entry(payroll),
        "despesas_operacionais_total": metric_entry(expenses),
        "servicos_terceiros_total": metric_entry(third_party_services),
        "saldo_contas_socios_final": metric_entry(partner_accounts),
        "lucro_apurado_total": metric_entry(profit),
        "lucros_distribuidos_total": metric_entry(profit_distribution),
        "tributos_a_recolher_final": metric_entry(tax_liability),
        "emprestimos_final": metric_entry(debt),
        "fornecedores_final": metric_entry(suppliers),
        "estoques_final": metric_entry(inventory),
        "cmv_custos_total": metric_entry(cogs),
        "creditos_fiscais_final": metric_entry(tax_credits),
        "rbt12_receita": metric_entry(Decimal(str((rbt12_context or {}).get("receita") or revenue))),
        "rbt12_folha": metric_entry(Decimal(str((rbt12_context or {}).get("folha") or payroll))),
        "contexto_rbt12": {
            "dados_suficientes": bool((rbt12_context or {}).get("dados_suficientes")),
            "origem": str((rbt12_context or {}).get("origem") or ""),
            "base_calculo": str((rbt12_context or {}).get("base_calculo") or ""),
            "trimestres_considerados": list((rbt12_context or {}).get("trimestres_considerados") or []),
            "fator_r_rbt12": str((rbt12_context or {}).get("fator_r_formatado") or "0,0%"),
        },
        "caixa_e_bancos_final": metric_entry(last["metricas"]["caixa_e_bancos"]),
        "clientes_recebiveis_final": metric_entry(last["metricas"]["clientes_recebiveis"]),
        "adiantamentos_final": metric_entry(last["metricas"]["adiantamentos"]),
        "adiantamentos_clientes_final": metric_entry(last["metricas"]["adiantamentos_clientes"]),
        "indicadores_derivados": {
            "carga_tributaria_efetiva_anual": safe_percent(taxes, revenue),
            "deducoes_sobre_receita_anual": safe_percent(deductions, revenue),
            "despesas_sobre_receita_anual": safe_percent(expenses, revenue),
            "servicos_terceiros_sobre_despesas_anual": safe_percent(third_party_services, expenses),
            "folha_sobre_receita_anual": safe_percent(payroll, revenue),
            "lucro_sobre_receita_anual": safe_percent(profit, revenue),
            "cmv_sobre_receita_anual": safe_percent(cogs, revenue),
            "estoques_finais_sobre_receita_anual": safe_percent(inventory, revenue),
            "fornecedores_finais_sobre_receita_anual": safe_percent(suppliers, revenue),
            "creditos_fiscais_finais_sobre_receita_anual": safe_percent(tax_credits, revenue),
            "distribuicao_lucros_sobre_lucro": safe_percent(profit_distribution, profit),
            "receita_sobre_limite_simples": safe_percent(revenue, SIMPLES_ANNUAL_LIMIT),
            "endividamento_sobre_receita": safe_percent(debt, revenue),
            "adiantamentos_clientes_sobre_receita": safe_percent(last["metricas"]["adiantamentos_clientes"], revenue),
        },
    }
    return result


def rbt12_context(quarters: list[dict[str, Any]]) -> dict[str, Any]:
    revenue = sum((q["metricas"]["receita_servicos"] for q in quarters), Decimal("0"))
    payroll = sum((q["metricas"]["folha_pro_labore"] for q in quarters), Decimal("0"))
    missing = missing_quarters(quarters)
    considered = [q["trimestre"] for q in quarters]
    sufficient = len(quarters) >= 4 and not missing
    fator_r = payroll / revenue if revenue > 0 else Decimal("0")

    return {
        "receita": float(revenue),
        "folha": float(payroll),
        "origem": "soma dos quatro trimestres informados" if sufficient else "soma parcial dos trimestres informados",
        "base_calculo": "RBT12 anual consolidado pelos quatro trimestres" if sufficient else "base anual parcial; exige completar os quatro trimestres",
        "trimestres_considerados": considered,
        "trimestres_ausentes": missing,
        "dados_suficientes": sufficient,
        "fator_r": float(fator_r),
        "fator_r_formatado": format_percent(fator_r),
    }

def metric_value(metricas: dict[str, Any], key: str) -> Decimal:
    value = metricas.get(key, {})
    if isinstance(value, dict):
        return Decimal(str(value.get("valor") or 0))
    return Decimal("0")

def metric_entry(value: Decimal) -> dict[str, Any]:
    return {"valor": float(value), "formatado": format_brl(value)}

def entry_value(metricas: dict[str, Any], key: str) -> Decimal:
    return Decimal(str(metricas.get(key, {}).get("valor") or 0))

def safe_percent(numerator: Decimal, denominator: Decimal) -> str:
    if denominator == 0:
        return "0,0%"
    return format_percent(numerator / denominator)

def missing_quarters(quarters: list[dict[str, Any]]) -> list[str]:
    found = {q["trimestre"] for q in quarters if q["trimestre"] in {"T1", "T2", "T3", "T4"}}
    return [q for q in ("T1", "T2", "T3", "T4") if q not in found]

def quarter_label(period: str) -> str:
    normalized = period.upper()
    match = re.search(r"\bT([1-4])\b", normalized)
    if match:
        return "T" + match.group(1)

    dates = re.findall(r"(\d{2})/(\d{2})/((?:19|20)\d{2})", period)
    if dates:
        month = int(dates[-1][1])
        return "T" + str(((month - 1) // 3) + 1)
    return "[VERIFICAR: trimestre]"

def quarter_order(label: str, period: str) -> int:
    if label in {"T1", "T2", "T3", "T4"}:
        return int(label[1])
    dates = re.findall(r"(\d{2})/(\d{2})/((?:19|20)\d{2})", period)
    if dates:
        return int(dates[-1][1])
    return 99


def opinion_code(value: str) -> str:
    text = str(value or "").strip().lower().replace("_", " ")
    if text in ("adversa", "opini?o adversa", "opiniao adversa"):
        return "adversa"
    if text in ("com ressalva", "ressalva"):
        return "com_ressalva"
    if text in ("absten??o de opini?o", "abstencao de opiniao"):
        return "abstencao_opiniao"
    return "sem_ressalva"
