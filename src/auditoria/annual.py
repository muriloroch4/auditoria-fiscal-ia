from __future__ import annotations

import datetime
import re
from collections import Counter, defaultdict
from decimal import Decimal
from typing import Any

from .evidence import structured_evidence
from .schema_validator import validate_payload_against_schema
from .utils import format_brl, format_percent

ANNUAL_SCHEMA_VERSION = "annual-1.0.0"
SIMPLES_ANNUAL_LIMIT = Decimal("4800000")


def build_annual_comparison(quarterly_payloads: list[dict[str, Any]]) -> dict[str, Any]:
    if not quarterly_payloads:
        raise ValueError("Informe ao menos um JSON trimestral para consolidar o parecer anual.")

    quarters = sorted((_quarter_summary(payload) for payload in quarterly_payloads), key=lambda item: item["ordem"])
    rbt12_context = _rbt12_context(quarters)
    totals = _annual_totals(quarters, rbt12_context)
    findings = _annual_findings(quarters, totals)
    risk = _annual_risk(quarters, findings)
    identificacao = _annual_identification(quarters)

    payload = {
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
    validate_payload_against_schema(payload, "anual")
    return payload


def build_rbt12_context(quarterly_payloads: list[dict[str, Any]]) -> dict[str, Any]:
    if not quarterly_payloads:
        return {}
    quarters = sorted((_quarter_summary(payload) for payload in quarterly_payloads), key=lambda item: item["ordem"])
    return _rbt12_context(quarters)


def generate_annual_markdown_report(payload: dict[str, Any]) -> str:
    identificacao = payload["identificacao"]
    risco = payload["risco_anual"]
    metricas = payload["metricas_anual"]
    findings = payload["achados_anuais"]
    evolution = payload["resumo_evolucao"]
    meta = payload["meta"]

    return "\n\n".join(
        [
            "Parecer técnico contábil consultivo anual comparativo\n"
            f"Cliente:  {identificacao.get('cliente', '')}\n"
            f"CNPJ:     {identificacao.get('cnpj', '')}\n"
            f"Regime:   {identificacao.get('regime_tributario', '')}\n"
            f"Exercício:{identificacao.get('exercicio', '')}\n"
            f"Emissão:  {str(meta['data_analise']).split('T', 1)[0]}",
            "## 1. Resumo executivo\n\n" + _render_annual_summary(payload),
            "## 2. Comparativo trimestral\n\n" + _render_quarter_table(payload),
            "## 3. Achados anuais e recorrências\n\n" + _render_annual_findings(findings),
            "## 4. Indicadores consolidados\n\n" + _render_annual_metrics(metricas, evolution),
            "## 5. Opinião técnica anual\n\n" + _render_annual_opinion(payload),
        ]
    )


def _quarter_summary(payload: dict[str, Any]) -> dict[str, Any]:
    if "identificacao_empresa" in payload and "resumo_analise" in payload:
        identificacao = payload.get("identificacao_empresa", {})
        resumo = payload.get("resumo_analise", {})
        conclusao = payload.get("conclusao_tecnica", {})
        achados = payload.get("principais_achados", [])
        metricas = payload.get("metricas", {})
        periodo = str(identificacao.get("periodo_analisado") or "[VERIFICAR: período]")
        trimestre = _quarter_label(periodo)

        return {
            "trimestre": trimestre,
            "ordem": _quarter_order(trimestre, periodo),
            "periodo": periodo,
            "cliente": resumo.get("empresa", ""),
            "cnpj": identificacao.get("cnpj", ""),
            "regime_tributario": identificacao.get("regime_tributario", ""),
            "risco": resumo.get("risco_geral") or conclusao.get("risco_geral") or "baixo",
            "pontuacao": int(resumo.get("pontuacao_total") or 0),
            "modalidade_opiniao_sugerida": _opinion_code(conclusao.get("conclusao_sugerida", "sem ressalva")),
            "metricas": {
                "receita_servicos": _metric(metricas, "receita_servicos"),
                "deducoes_receita": _metric(metricas, "deducoes_receita"),
                "tributos_registrados": _metric(metricas, "tributos_registrados"),
                "tributos_a_recolher": _metric(metricas, "tributos_a_recolher"),
                "folha_pro_labore": _metric(metricas, "folha_pro_labore"),
                "despesas_operacionais": _metric(metricas, "despesas_operacionais"),
                "servicos_terceiros": _metric(metricas, "servicos_terceiros"),
                "lucros_distribuidos": _metric(metricas, "lucros_distribuidos"),
                "lucro_apurado_base": _metric(metricas, "lucro_apurado_base"),
                "caixa_e_bancos": _metric(metricas, "caixa_e_bancos"),
                "clientes_recebiveis": _metric(metricas, "clientes_recebiveis"),
                "adiantamentos": _metric(metricas, "adiantamentos"),
                "emprestimos": _metric(metricas, "emprestimos"),
                "fornecedores": _metric(metricas, "fornecedores"),
                "estoques": _metric(metricas, "estoques"),
                "cmv_custos": _metric(metricas, "cmv_custos"),
                "creditos_fiscais": _metric(metricas, "creditos_fiscais"),
            },
            "achados": achados,
            "achados_codigos": [str(item.get("codigo", "")) for item in achados if item.get("codigo")],
        }

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
            "servicos_terceiros": _metric(metricas, "servicos_terceiros"),
            "lucros_distribuidos": _metric(metricas, "lucros_distribuidos"),
            "lucro_apurado_base": _metric(metricas, "lucro_apurado_base"),
            "caixa_e_bancos": _metric(metricas, "caixa_e_bancos"),
            "clientes_recebiveis": _metric(metricas, "clientes_recebiveis"),
            "adiantamentos": _metric(metricas, "adiantamentos"),
            "emprestimos": _metric(metricas, "emprestimos"),
            "fornecedores": _metric(metricas, "fornecedores"),
            "estoques": _metric(metricas, "estoques"),
            "cmv_custos": _metric(metricas, "cmv_custos"),
            "creditos_fiscais": _metric(metricas, "creditos_fiscais"),
        },
        "achados": achados,
        "achados_codigos": [str(item.get("codigo", "")) for item in achados if item.get("codigo")],
    }


def _annual_totals(quarters: list[dict[str, Any]], rbt12_context: dict[str, Any] | None = None) -> dict[str, Any]:
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
    debt = last["metricas"]["emprestimos"]
    tax_liability = last["metricas"]["tributos_a_recolher"]
    suppliers = last["metricas"]["fornecedores"]
    inventory = last["metricas"]["estoques"]
    tax_credits = last["metricas"]["creditos_fiscais"]

    result = {
        "receita_servicos_total": _entry(revenue),
        "deducoes_receita_total": _entry(deductions),
        "tributos_registrados_total": _entry(taxes),
        "folha_pro_labore_total": _entry(payroll),
        "despesas_operacionais_total": _entry(expenses),
        "servicos_terceiros_total": _entry(third_party_services),
        "lucro_apurado_total": _entry(profit),
        "lucros_distribuidos_total": _entry(profit_distribution),
        "tributos_a_recolher_final": _entry(tax_liability),
        "emprestimos_final": _entry(debt),
        "fornecedores_final": _entry(suppliers),
        "estoques_final": _entry(inventory),
        "cmv_custos_total": _entry(cogs),
        "creditos_fiscais_final": _entry(tax_credits),
        "rbt12_receita": _entry(Decimal(str((rbt12_context or {}).get("receita") or revenue))),
        "rbt12_folha": _entry(Decimal(str((rbt12_context or {}).get("folha") or payroll))),
        "contexto_rbt12": {
            "dados_suficientes": bool((rbt12_context or {}).get("dados_suficientes")),
            "origem": str((rbt12_context or {}).get("origem") or ""),
            "base_calculo": str((rbt12_context or {}).get("base_calculo") or ""),
            "trimestres_considerados": list((rbt12_context or {}).get("trimestres_considerados") or []),
            "fator_r_rbt12": str((rbt12_context or {}).get("fator_r_formatado") or "0,0%"),
        },
        "caixa_e_bancos_final": _entry(last["metricas"]["caixa_e_bancos"]),
        "clientes_recebiveis_final": _entry(last["metricas"]["clientes_recebiveis"]),
        "adiantamentos_final": _entry(last["metricas"]["adiantamentos"]),
        "indicadores_derivados": {
            "carga_tributaria_efetiva_anual": _safe_percent(taxes, revenue),
            "deducoes_sobre_receita_anual": _safe_percent(deductions, revenue),
            "despesas_sobre_receita_anual": _safe_percent(expenses, revenue),
            "servicos_terceiros_sobre_despesas_anual": _safe_percent(third_party_services, expenses),
            "folha_sobre_receita_anual": _safe_percent(payroll, revenue),
            "lucro_sobre_receita_anual": _safe_percent(profit, revenue),
            "cmv_sobre_receita_anual": _safe_percent(cogs, revenue),
            "estoques_finais_sobre_receita_anual": _safe_percent(inventory, revenue),
            "fornecedores_finais_sobre_receita_anual": _safe_percent(suppliers, revenue),
            "creditos_fiscais_finais_sobre_receita_anual": _safe_percent(tax_credits, revenue),
            "distribuicao_lucros_sobre_lucro": _safe_percent(profit_distribution, profit),
            "receita_sobre_limite_simples": _safe_percent(revenue, SIMPLES_ANNUAL_LIMIT),
            "endividamento_sobre_receita": _safe_percent(debt, revenue),
        },
    }
    return result


def _rbt12_context(quarters: list[dict[str, Any]]) -> dict[str, Any]:
    revenue = sum((q["metricas"]["receita_servicos"] for q in quarters), Decimal("0"))
    payroll = sum((q["metricas"]["folha_pro_labore"] for q in quarters), Decimal("0"))
    missing = _missing_quarters(quarters)
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
    expenses = _value(totals, "despesas_operacionais_total")
    third_party_services = _value(totals, "servicos_terceiros_total")
    profit = _value(totals, "lucro_apurado_total")
    profit_distribution = _value(totals, "lucros_distribuidos_total")
    debt = _value(totals, "emprestimos_final")
    tax_liability = _value(totals, "tributos_a_recolher_final")
    inventory = _value(totals, "estoques_final")
    suppliers = _value(totals, "fornecedores_final")
    cogs = _value(totals, "cmv_custos_total")
    tax_credits = _value(totals, "creditos_fiscais_final")
    clients = _value(totals, "clientes_recebiveis_final")

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

    if revenue > 0 and profit > 0 and profit / revenue > Decimal("0.64"):
        findings.append(
            _finding(
                "AN-MAR-001",
                "Margem anual de lucro muito elevada",
                "medio",
                12,
                "O lucro anual representa percentual elevado da receita consolidada, sugerindo possivel ausencia de despesas, custos ou apropriacoes de competencia.",
                {"lucro_anual": format_brl(profit), "receita_anual": format_brl(revenue), "margem_lucro": format_percent(profit / revenue)},
                "Revisar custos, despesas, folha, pro-labore, servicos tomados, competencia contabila e documentos de suporte antes de concluir sobre a margem anual.",
            )
        )

    if expenses > 0 and third_party_services >= Decimal("10000") and third_party_services / expenses >= Decimal("0.20"):
        findings.append(
            _finding(
                "AN-DOC-325-001",
                "Servicos prestados por terceiros relevantes no ano",
                "medio",
                12,
                "A conta 325/servicos prestados por terceiros representa percentual relevante das despesas anuais, exigindo validacao documental dos lancamentos.",
                {
                    "conta_referencia": "325 - Servicos prestados por terceiros",
                    "servicos_terceiros_total": format_brl(third_party_services),
                    "despesas_operacionais_total": format_brl(expenses),
                    "percentual_sobre_despesas": format_percent(third_party_services / expenses),
                    "criterio_rastreio": "consolidacao anual da metrica servicos_terceiros dos JSONs trimestrais",
                },
                "Validar contratos, notas fiscais, comprovantes bancarios, retencoes aplicaveis e a correta apropriacao dos pagamentos lancados diretamente em despesas.",
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

    if revenue >= Decimal("800000") and clients <= 0:
        findings.append(
            _finding(
                "AN-CLI-001",
                "Clientes zerados no fechamento anual com receita relevante",
                "baixo",
                6,
                "O saldo final de clientes/recebiveis esta zerado apesar de receita anual relevante, exigindo confirmacao do recebimento a vista ou no proprio periodo.",
                {"clientes_recebiveis_final": format_brl(clients), "receita_anual": format_brl(revenue)},
                "Conciliar notas fiscais, extratos bancarios, baixas de recebiveis e meios de pagamento para confirmar se nao ha saldo pendente.",
            )
        )

    if revenue > 0 and inventory / revenue > Decimal("0.50"):
        findings.append(
            _finding(
                "AN-COM-EST-001",
                "Estoque final relevante em relacao a receita anual",
                "medio",
                12,
                "O saldo final de estoques representa percentual relevante da receita anual consolidada.",
                {"estoques_final": format_brl(inventory), "receita_anual": format_brl(revenue), "percentual": format_percent(inventory / revenue)},
                "Conciliar inventario final, compras, notas fiscais de venda, perdas, devolucoes e baixas por CMV antes do parecer anual.",
            )
        )

    if revenue > 0 and suppliers / revenue > Decimal("0.30"):
        findings.append(
            _finding(
                "AN-COM-FOR-001",
                "Fornecedores finais relevantes em relacao a receita anual",
                "medio",
                10,
                "O saldo final de fornecedores e relevante frente a receita anual, exigindo conciliacao com compras e pagamentos posteriores.",
                {"fornecedores_final": format_brl(suppliers), "receita_anual": format_brl(revenue), "percentual": format_percent(suppliers / revenue)},
                "Validar aging de fornecedores, documentos fiscais de compra, duplicatas pagas, mercadorias recebidas e vinculo com estoque.",
            )
        )

    if revenue > 0 and (inventory > 0 or suppliers > 0) and cogs <= 0:
        findings.append(
            _finding(
                "AN-COM-CMV-001",
                "Operacao comercial anual sem CMV consolidado",
                "alto",
                20,
                "Ha sinais comerciais no fechamento anual, mas nao foi identificado CMV/custo de mercadorias consolidado.",
                {"estoques_final": format_brl(inventory), "fornecedores_final": format_brl(suppliers), "cmv_custos_total": format_brl(cogs)},
                "Verificar baixas de estoque, custo medio, classificacao de contas de custo e demonstracoes de resultado antes de concluir a margem anual.",
            )
        )

    if tax_credits > 0 and revenue > 0 and tax_credits / revenue > Decimal("0.01"):
        findings.append(
            _finding(
                "AN-COM-ST-001",
                "Creditos fiscais finais exigem validacao de ICMS-ST e recuperabilidade",
                "baixo",
                6,
                "Foram identificados creditos fiscais finais relevantes em empresa do Simples, com potencial relacao com ICMS-ST, retencoes ou ressarcimentos.",
                {"creditos_fiscais_final": format_brl(tax_credits), "receita_anual": format_brl(revenue), "percentual": format_percent(tax_credits / revenue)},
                "Validar NCM/CFOP, produtos sujeitos a substituicao tributaria, ressarcimentos, retencoes e documentacao de suporte dos creditos.",
            )
        )

    if len(quarters) >= 2:
        findings.extend(_trend_findings(quarters))
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


def _trend_findings(quarters: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
            _finding(
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
            _finding(
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
        "variacao_pontuacao_primeiro_ultimo": _safe_percent(
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


def _render_annual_summary(payload: dict[str, Any]) -> str:
    risco = payload["risco_anual"]
    metricas = payload["metricas_anual"]
    meta = payload["meta"]
    identificacao = payload["identificacao"]
    return (
        f"A análise comparativa do exercício {identificacao.get('exercicio')} considerou "
        f"{meta['total_trimestres_informados']} trimestre(s) informado(s). O nível de risco anual "
        f"apurado é {_risk_label(risco['nivel_geral']).lower()}, com pontuação de {risco['pontuacao_total']} pontos "
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
            f"{format_brl(metrics['lucro_apurado_base'])} | {_risk_label(q['risco'])} | "
            f"{', '.join(q['achados_codigos']) or 'nenhum'} |"
        )
    return "\n".join(lines)


def _render_annual_findings(findings: list[dict[str, Any]]) -> str:
    if not findings:
        return "Nenhum achado anual adicional foi identificado a partir da consolidação dos trimestres."

    lines = [
        "| Código | Achado | Nível | Evidência | Fonte | Confiança | Documentos recomendados | Recomendação |",
        "|--------|--------|-------|-----------|-------|-----------|--------------------------|--------------|",
    ]
    for finding in findings:
        structured = finding["evidencia"]
        extracted = structured.get("campos_extraidos") or {}
        evidence = "; ".join(f"{key}: {value}" for key, value in extracted.items()) or "Não aplicável"
        documents = ", ".join(structured.get("documentos_recomendados") or [])
        lines.append(
            "| "
            f"{finding['codigo']} | {finding['titulo']} | {_risk_label(finding['nivel'])} | "
            f"{evidence} | {structured.get('fonte_dado', '')} | {_risk_label(structured.get('confianca', ''))} | "
            f"{documents} | {finding['recomendacao']} |"
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
        f"Servicos de terceiros: {metricas['servicos_terceiros_total']['formatado']} "
        f"({indicators['servicos_terceiros_sobre_despesas_anual']} das despesas). "
        f"CMV/custos anual: {metricas['cmv_custos_total']['formatado']} "
        f"({indicators['cmv_sobre_receita_anual']}). "
        f"Estoques finais: {metricas['estoques_final']['formatado']}. "
        f"Fornecedores finais: {metricas['fornecedores_final']['formatado']}. "
        f"Créditos fiscais finais: {metricas['creditos_fiscais_final']['formatado']}. "
        f"RBT12 consolidado: {metricas['rbt12_receita']['formatado']} "
        f"({metricas['contexto_rbt12']['base_calculo']}). "
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
        f"emito opinião técnica anual {_opinion_label(risco['modalidade_opiniao_sugerida'])} para o conjunto analisado. "
        f"Os principais achados anuais considerados foram: {codes}. A conclusão anual não substitui "
        "auditoria independente completa e deve ser lida em conjunto com os pareceres trimestrais que "
        "serviram de base para esta consolidação."
    )


def _metric(metricas: dict[str, Any], key: str) -> Decimal:
    value = metricas.get(key, {})
    if isinstance(value, dict):
        return Decimal(str(value.get("valor") or 0))
    return Decimal("0")


def _risk_label(value: str) -> str:
    labels = {"alto": "Alto", "medio": "Médio", "baixo": "Baixo"}
    return labels.get(str(value).lower(), str(value).capitalize())


def _opinion_label(value: str) -> str:
    labels = {
        "sem_ressalva": "sem ressalva",
        "com_ressalva": "com ressalva",
        "adversa": "adversa",
        "abstencao_opiniao": "com abstenção de opinião",
    }
    return labels.get(str(value), str(value).replace("_", " "))


def _opinion_code(value: str) -> str:
    text = str(value or "").strip().lower().replace("_", " ")
    if text in ("adversa", "opinião adversa", "opiniao adversa"):
        return "adversa"
    if text in ("com ressalva", "ressalva"):
        return "com_ressalva"
    if text in ("abstenção de opinião", "abstencao de opiniao"):
        return "abstencao_opiniao"
    return "sem_ressalva"


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
        "evidencia": structured_evidence(code, evidence, severity=level, source="json_trimestral_consolidado"),
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
