from __future__ import annotations

import datetime
import re
from collections import Counter, defaultdict
from decimal import Decimal
from typing import Any

from .utils import format_brl, format_percent

ANNUAL_SCHEMA_VERSION = "annual-1.0.0"
SIMPLES_ANNUAL_LIMIT = Decimal("4800000")


def build_annual_comparison(quarterly_payloads: list[dict[str, Any]]) -> dict[str, Any]:
    if not quarterly_payloads:
        raise ValueError("Informe ao menos um JSON trimestral para consolidar o parecer anual.")

    quarters = sorted((_quarter_summary(payload) for payload in quarterly_payloads), key=lambda item: item["ordem"])
    totals = _annual_totals(quarters)
    findings = _annual_findings(quarters, totals)
    risk = _annual_risk(quarters, findings)
    identificacao = _annual_identification(quarters)

    return {
        "_schema_version": ANNUAL_SCHEMA_VERSION,
        "meta": {
            "versao_schema": ANNUAL_SCHEMA_VERSION,
            "data_analise": datetime.datetime.now().isoformat(timespec="seconds"),
            "total_trimestres_informados": len(quarters),
            "trimestres_ausentes": _missing_quarters(quarters),
            "fontes": [q["periodo"] for q in quarters],
        },
        "identificacao": identificacao,
        "risco_anual": risk,
        "metricas_anual": totals,
        "comparativo_trimestral": quarters,
        "achados_anuais": findings,
        "resumo_evolucao": _evolution_summary(quarters, totals, findings),
    }


def generate_annual_markdown_report(payload: dict[str, Any]) -> str:
    identificacao = payload["identificacao"]
    risco = payload["risco_anual"]
    metricas = payload["metricas_anual"]
    findings = payload["achados_anuais"]
    evolution = payload["resumo_evolucao"]
    meta = payload["meta"]

    return "\n\n".join(
        [
            "PARECER TÉCNICO CONTÁBIL — CONSULTIVO ANUAL COMPARATIVO\n"
            "[espaço para numeração manual]\n\n"
            f"Cliente:  {identificacao.get('cliente', '')}\n"
            f"CNPJ:     {identificacao.get('cnpj', '')}\n"
            f"Regime:   {identificacao.get('regime_tributario', '')}\n"
            f"Exercício:{identificacao.get('exercicio', '')}\n"
            f"Emissão:  {str(meta['data_analise']).split('T', 1)[0]}",
            "## 1. RESUMO EXECUTIVO\n\n" + _render_annual_summary(payload),
            "## 2. COMPARATIVO TRIMESTRAL\n\n" + _render_quarter_table(payload),
            "## 3. ACHADOS ANUAIS E RECORRÊNCIAS\n\n" + _render_annual_findings(findings),
            "## 4. INDICADORES CONSOLIDADOS\n\n" + _render_annual_metrics(metricas, evolution),
            "## 5. OPINIÃO TÉCNICA ANUAL\n\n" + _render_annual_opinion(payload),
            "## 6. ASSINATURA\n\n"
            "Local e data: _________________________, _____ de ______________ de _______\n\n"
            "Nome:  ________________________________________________________________\n\n"
            "CRC:   ________________________________________________________________\n\n"
            "Assinatura: ____________________________________________________________",
        ]
    )


def _quarter_summary(payload: dict[str, Any]) -> dict[str, Any]:
    identificacao = payload.get("identificacao", {})
    metricas = payload.get("metricas", {})
    risco = payload.get("risco", {})
    achados = payload.get("achados", [])
    periodo = str(identificacao.get("periodo") or "[VERIFICAR: período]")
    trimestre = _quarter_label(periodo)

    return {
        "trimestre": trimestre,
        "ordem": _quarter_order(trimestre, periodo),
        "periodo": periodo,
        "cliente": identificacao.get("cliente", ""),
        "cnpj": identificacao.get("cnpj", ""),
        "regime_tributario": identificacao.get("regime_tributario", ""),
        "risco": risco.get("nivel_geral", "baixo"),
        "pontuacao": int(risco.get("pontuacao_total") or 0),
        "modalidade_opiniao_sugerida": risco.get("modalidade_opiniao_sugerida", "sem_ressalva"),
        "metricas": {
            "receita_servicos": _metric(metricas, "receita_servicos"),
            "deducoes_receita": _metric(metricas, "deducoes_receita"),
            "tributos_registrados": _metric(metricas, "tributos_registrados"),
            "tributos_a_recolher": _metric(metricas, "tributos_a_recolher"),
            "folha_pro_labore": _metric(metricas, "folha_pro_labore"),
            "despesas_operacionais": _metric(metricas, "despesas_operacionais"),
            "lucros_distribuidos": _metric(metricas, "lucros_distribuidos"),
            "lucro_apurado_base": _metric(metricas, "lucro_apurado_base"),
            "caixa_e_bancos": _metric(metricas, "caixa_e_bancos"),
            "clientes_recebiveis": _metric(metricas, "clientes_recebiveis"),
            "adiantamentos": _metric(metricas, "adiantamentos"),
            "emprestimos": _metric(metricas, "emprestimos"),
        },
        "achados": achados,
        "achados_codigos": [str(item.get("codigo", "")) for item in achados if item.get("codigo")],
    }


def _annual_totals(quarters: list[dict[str, Any]]) -> dict[str, Any]:
    last = quarters[-1]

    def sum_metric(key: str) -> Decimal:
        return sum((q["metricas"][key] for q in quarters), Decimal("0"))

    revenue = sum_metric("receita_servicos")
    deductions = sum_metric("deducoes_receita")
    taxes = sum_metric("tributos_registrados")
    expenses = sum_metric("despesas_operacionais")
    payroll = sum_metric("folha_pro_labore")
    profit = sum_metric("lucro_apurado_base")
    profit_distribution = sum_metric("lucros_distribuidos")
    debt = last["metricas"]["emprestimos"]
    tax_liability = last["metricas"]["tributos_a_recolher"]

    result = {
        "receita_servicos_total": _entry(revenue),
        "deducoes_receita_total": _entry(deductions),
        "tributos_registrados_total": _entry(taxes),
        "folha_pro_labore_total": _entry(payroll),
        "despesas_operacionais_total": _entry(expenses),
        "lucro_apurado_total": _entry(profit),
        "lucros_distribuidos_total": _entry(profit_distribution),
        "tributos_a_recolher_final": _entry(tax_liability),
        "emprestimos_final": _entry(debt),
        "caixa_e_bancos_final": _entry(last["metricas"]["caixa_e_bancos"]),
        "clientes_recebiveis_final": _entry(last["metricas"]["clientes_recebiveis"]),
        "adiantamentos_final": _entry(last["metricas"]["adiantamentos"]),
        "indicadores_derivados": {
            "carga_tributaria_efetiva_anual": _safe_percent(taxes, revenue),
            "deducoes_sobre_receita_anual": _safe_percent(deductions, revenue),
            "despesas_sobre_receita_anual": _safe_percent(expenses, revenue),
            "folha_sobre_receita_anual": _safe_percent(payroll, revenue),
            "lucro_sobre_receita_anual": _safe_percent(profit, revenue),
            "distribuicao_lucros_sobre_lucro": _safe_percent(profit_distribution, profit),
            "receita_sobre_limite_simples": _safe_percent(revenue, SIMPLES_ANNUAL_LIMIT),
            "endividamento_sobre_receita": _safe_percent(debt, revenue),
        },
    }
    return result


def _annual_findings(quarters: list[dict[str, Any]], totals: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    codes = Counter(code for q in quarters for code in q["achados_codigos"])

    for code, count in sorted(codes.items()):
        if count >= 2:
            findings.append(
                _finding(
                    "AN-REC-" + code,
                    f"Achado recorrente: {code}",
                    "alto" if count >= 3 or code.startswith("SN-COMP") else "medio",
                    18 if count >= 3 else 10,
                    f"O achado {code} foi identificado em {count} trimestres do exercício.",
                    {"codigo_base": code, "recorrencias": str(count)},
                    "Priorizar plano de ação corretivo e validar se a causa raiz foi eliminada antes do próximo fechamento.",
                )
            )

    revenue = _value(totals, "receita_servicos_total")
    profit = _value(totals, "lucro_apurado_total")
    profit_distribution = _value(totals, "lucros_distribuidos_total")
    debt = _value(totals, "emprestimos_final")
    tax_liability = _value(totals, "tributos_a_recolher_final")

    if revenue >= SIMPLES_ANNUAL_LIMIT * Decimal("0.90"):
        findings.append(
            _finding(
                "AN-SN-001B",
                "Receita anual próxima ao limite do Simples Nacional",
                "alto",
                30,
                "A receita anual atingiu 90% ou mais do limite anual do Simples Nacional.",
                {"receita_anual": format_brl(revenue), "limite_simples": format_brl(SIMPLES_ANNUAL_LIMIT)},
                "Projetar a receita dos próximos meses e validar risco de excesso de sublimite ou desenquadramento.",
            )
        )
    elif revenue >= SIMPLES_ANNUAL_LIMIT * Decimal("0.70"):
        findings.append(
            _finding(
                "AN-SN-001A",
                "Receita anual em faixa de atenção do Simples Nacional",
                "medio",
                15,
                "A receita anual atingiu 70% ou mais do limite anual do Simples Nacional.",
                {"receita_anual": format_brl(revenue), "limite_simples": format_brl(SIMPLES_ANNUAL_LIMIT)},
                "Acompanhar receita acumulada e simular cenários de crescimento para o exercício seguinte.",
            )
        )

    if profit_distribution > profit and profit_distribution > 0:
        findings.append(
            _finding(
                "AN-LUC-001",
                "Lucros distribuídos acima do lucro anual apurado",
                "alto",
                30,
                "A distribuição anual de lucros supera o resultado contábil acumulado no exercício.",
                {"lucro_anual": format_brl(profit), "lucros_distribuidos": format_brl(profit_distribution)},
                "Validar escrituração anual, balancetes de suporte e base legal antes de manter a distribuição isenta.",
            )
        )

    if revenue > 0 and debt / revenue > Decimal("0.60"):
        findings.append(
            _finding(
                "AN-END-001",
                "Endividamento final elevado em relação à receita anual",
                "medio",
                12,
                "O saldo final de empréstimos representa percentual relevante da receita anual.",
                {"emprestimos_final": format_brl(debt), "receita_anual": format_brl(revenue), "percentual": format_percent(debt / revenue)},
                "Avaliar cronograma de amortização, contratos bancários e capacidade de geração de caixa.",
            )
        )

    if len(quarters) >= 2:
        first_tax = quarters[0]["metricas"]["tributos_a_recolher"]
        last_tax = quarters[-1]["metricas"]["tributos_a_recolher"]
        if first_tax > 0 and last_tax > first_tax * Decimal("1.50"):
            findings.append(
                _finding(
                    "AN-TRIB-001",
                    "Passivo tributário cresceu de forma relevante no ano",
                    "medio",
                    14,
                    "O saldo de tributos a recolher aumentou mais de 50% entre o primeiro e o último trimestre informado.",
                    {"saldo_inicial": format_brl(first_tax), "saldo_final": format_brl(last_tax), "crescimento": format_percent((last_tax - first_tax) / first_tax)},
                    "Conciliar guias, parcelamentos, pagamentos e saldos fiscais antes do encerramento anual.",
                )
            )
        elif tax_liability > 0 and revenue > 0 and tax_liability / revenue > Decimal("0.10"):
            findings.append(
                _finding(
                    "AN-TRIB-002",
                    "Passivo tributário final relevante",
                    "medio",
                    10,
                    "O saldo final de tributos a recolher é relevante em relação à receita anual.",
                    {"tributos_a_recolher_final": format_brl(tax_liability), "receita_anual": format_brl(revenue), "percentual": format_percent(tax_liability / revenue)},
                    "Validar composição do saldo e eventual necessidade de regularização ou parcelamento.",
                )
            )

    return findings


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
        "explicacao_pontuacao": _annual_score_explanation(quarters, findings, level, score),
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
        "variacao_receita_primeiro_ultimo": _safe_percent(last_revenue - first_revenue, first_revenue),
        "melhor_trimestre_resultado": best["trimestre"],
        "pior_trimestre_resultado": worst["trimestre"],
        "achados_recorrentes": [{"codigo": code, "trimestres": count} for code, count in sorted(by_code.items()) if count >= 2],
        "total_achados_anuais": len(findings),
        "receita_anual_formatada": totals["receita_servicos_total"]["formatado"],
        "resultado_anual_formatado": totals["lucro_apurado_total"]["formatado"],
    }


def _render_annual_summary(payload: dict[str, Any]) -> str:
    risco = payload["risco_anual"]
    metricas = payload["metricas_anual"]
    meta = payload["meta"]
    identificacao = payload["identificacao"]
    return (
        f"A análise comparativa do exercício {identificacao.get('exercicio')} considerou "
        f"{meta['total_trimestres_informados']} trimestre(s) informado(s). O nível de risco anual "
        f"apurado é {risco['nivel_geral'].upper()}, com pontuação de {risco['pontuacao_total']} pontos "
        f"e {len(payload['achados_anuais'])} achado(s) anual(is). A receita anual consolidada foi "
        f"{metricas['receita_servicos_total']['formatado']} e o resultado anual apurado foi "
        f"{metricas['lucro_apurado_total']['formatado']}."
    )


def _render_quarter_table(payload: dict[str, Any]) -> str:
    lines = [
        "| Trimestre | Período | Receita | Resultado | Risco | Achados |",
        "|-----------|---------|---------|-----------|-------|---------|",
    ]
    for q in payload["comparativo_trimestral"]:
        metrics = q["metricas"]
        lines.append(
            "| "
            f"{q['trimestre']} | {q['periodo']} | {format_brl(metrics['receita_servicos'])} | "
            f"{format_brl(metrics['lucro_apurado_base'])} | {q['risco'].upper()} | "
            f"{', '.join(q['achados_codigos']) or 'nenhum'} |"
        )
    return "\n".join(lines)


def _render_annual_findings(findings: list[dict[str, Any]]) -> str:
    if not findings:
        return "Nenhum achado anual adicional foi identificado a partir da consolidação dos trimestres."

    lines = [
        "| Código | Achado | Nível | Evidência | Recomendação |",
        "|--------|--------|-------|-----------|--------------|",
    ]
    for finding in findings:
        evidence = "; ".join(f"{key}: {value}" for key, value in finding["evidencia"].items()) or "Não aplicável"
        lines.append(
            "| "
            f"{finding['codigo']} | {finding['titulo']} | {finding['nivel'].upper()} | "
            f"{evidence} | {finding['recomendacao']} |"
        )
    return "\n".join(lines)


def _render_annual_metrics(metricas: dict[str, Any], evolution: dict[str, Any]) -> str:
    indicators = metricas["indicadores_derivados"]
    return (
        f"Receita anual: {metricas['receita_servicos_total']['formatado']}. "
        f"Deduções da receita: {metricas['deducoes_receita_total']['formatado']}. "
        f"Tributos registrados: {metricas['tributos_registrados_total']['formatado']} "
        f"({indicators['carga_tributaria_efetiva_anual']}). "
        f"Despesas operacionais: {metricas['despesas_operacionais_total']['formatado']} "
        f"({indicators['despesas_sobre_receita_anual']}). "
        f"Resultado anual: {metricas['lucro_apurado_total']['formatado']}. "
        f"Melhor trimestre por resultado: {evolution['melhor_trimestre_resultado']}. "
        f"Pior trimestre por resultado: {evolution['pior_trimestre_resultado']}."
    )


def _render_annual_opinion(payload: dict[str, Any]) -> str:
    identificacao = payload["identificacao"]
    risco = payload["risco_anual"]
    findings = payload["achados_anuais"]
    codes = ", ".join(f["codigo"] for f in findings) or "nenhum achado anual adicional"
    return (
        f"Com base na consolidação dos trimestres do exercício {identificacao.get('exercicio')}, "
        f"emito opinião técnica anual {risco['modalidade_opiniao_sugerida']} para o conjunto analisado. "
        f"Os principais achados anuais considerados foram: {codes}. A conclusão anual não substitui "
        "auditoria independente completa e deve ser lida em conjunto com os pareceres trimestrais que "
        "serviram de base para esta consolidação."
    )


def _metric(metricas: dict[str, Any], key: str) -> Decimal:
    value = metricas.get(key, {})
    if isinstance(value, dict):
        return Decimal(str(value.get("valor") or 0))
    return Decimal("0")


def _entry(value: Decimal) -> dict[str, Any]:
    return {"valor": float(value), "formatado": format_brl(value)}


def _value(metricas: dict[str, Any], key: str) -> Decimal:
    return Decimal(str(metricas.get(key, {}).get("valor") or 0))


def _safe_percent(numerator: Decimal, denominator: Decimal) -> str:
    if denominator == 0:
        return "0,0%"
    return format_percent(numerator / denominator)


def _finding(
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
        "evidencia": evidence,
        "recomendacao": recommendation,
        "normas_aplicaveis": [
            "NBC PG 100 (R1) de 2018",
            "NBC TA 700 (R1)",
            "NBC TG 26 (R3) = CPC 26 R1",
        ],
    }


def _annual_score_explanation(
    quarters: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    level: str,
    score: int,
) -> list[str]:
    explanations = [f"Nível anual {level} com pontuação consolidada de {score} pontos."]
    if any(q["risco"] == "alto" for q in quarters):
        explanations.append("Ao menos um trimestre apresentou risco alto.")
    recurring = [f for f in findings if f["codigo"].startswith("AN-REC-")]
    if recurring:
        explanations.append(f"Foram identificados {len(recurring)} achado(s) recorrente(s).")
    if not findings:
        explanations.append("Não houve achados anuais adicionais além dos pareceres trimestrais.")
    return explanations


def _missing_quarters(quarters: list[dict[str, Any]]) -> list[str]:
    found = {q["trimestre"] for q in quarters if q["trimestre"] in {"T1", "T2", "T3", "T4"}}
    return [q for q in ("T1", "T2", "T3", "T4") if q not in found]


def _quarter_label(period: str) -> str:
    normalized = period.upper()
    match = re.search(r"\bT([1-4])\b", normalized)
    if match:
        return "T" + match.group(1)

    dates = re.findall(r"(\d{2})/(\d{2})/((?:19|20)\d{2})", period)
    if dates:
        month = int(dates[-1][1])
        return "T" + str(((month - 1) // 3) + 1)
    return "[VERIFICAR: trimestre]"


def _quarter_order(label: str, period: str) -> int:
    if label in {"T1", "T2", "T3", "T4"}:
        return int(label[1])
    dates = re.findall(r"(\d{2})/(\d{2})/((?:19|20)\d{2})", period)
    if dates:
        return int(dates[-1][1])
    return 99


def _first_non_empty(values: Any) -> str:
    for value in values:
        if value:
            return str(value)
    return ""
