from __future__ import annotations

from collections import Counter
from decimal import Decimal
from typing import Any

from .annual_metrics import SIMPLES_ANNUAL_LIMIT, entry_value
from .config_loader import get_rule_config
from .evidence import structured_evidence
from .utils import format_brl, format_percent

def annual_findings(quarters: list[dict[str, Any]], totals: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    codes = Counter(code for q in quarters for code in q["achados_codigos"])

    for code, count in sorted(codes.items()):
        if count >= 2:
            findings.append(
                annual_finding(
                    "AN-REC-" + code,
                    f"Achado recorrente: {code}",
                    "alto" if count >= 3 or code.startswith("SN-COMP") else "medio",
                    18 if count >= 3 else 10,
                    f"O achado {code} foi identificado em {count} trimestres do exercício.",
                    {"codigo_base": code, "recorrencias": str(count)},
                    "Priorizar plano de ação corretivo e validar se a causa raiz foi eliminada antes do próximo fechamento.",
                )
            )

    revenue = entry_value(totals, "receita_servicos_total")
    expenses = entry_value(totals, "despesas_operacionais_total")
    third_party_services = entry_value(totals, "servicos_terceiros_total")
    profit = entry_value(totals, "lucro_apurado_total")
    profit_distribution = entry_value(totals, "lucros_distribuidos_total")
    partner_accounts = entry_value(totals, "saldo_contas_socios_final")
    debt = entry_value(totals, "emprestimos_final")
    tax_liability = entry_value(totals, "tributos_a_recolher_final")
    inventory = entry_value(totals, "estoques_final")
    suppliers = entry_value(totals, "fornecedores_final")
    cogs = entry_value(totals, "cmv_custos_total")
    tax_credits = entry_value(totals, "creditos_fiscais_final")
    clients = entry_value(totals, "clientes_recebiveis_final")

    if revenue >= SIMPLES_ANNUAL_LIMIT * Decimal("0.90"):
        findings.append(
            annual_finding(
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
            annual_finding(
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
            annual_finding(
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
            annual_finding(
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
            annual_finding(
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

    if partner_accounts > 0:
        cfg = get_rule_config("SN-005")
        lim_abs = Decimal(str(cfg.get("limite_medio_absoluto", 10000)))
        lim_ratio = Decimal(str(cfg.get("limite_medio_receita", cfg.get("limite_medio", 0.05))))
        partner_ratio = partner_accounts / revenue if revenue > 0 else None
        material = partner_accounts >= lim_abs or (partner_ratio is not None and partner_ratio >= lim_ratio)
        level = "medio" if material else "baixo"
        score = int(cfg.get("pontuacao_medio", 12) if material else cfg.get("pontuacao_baixo", 6))
        findings.append(
            annual_finding(
                "AN-DOC-MUTUO-001",
                "Saldo final em contas de socios exige validacao documental",
                level,
                score,
                (
                    "O consolidado anual apresenta saldo material em contas de socios, administradores, pessoas ligadas ou mutuos, exigindo validacao de contrato, razao, extratos e IOF quando aplicavel."
                    if material
                    else "O consolidado anual apresenta saldo de baixa materialidade em contas de socios, administradores, pessoas ligadas ou mutuos, exigindo conciliacao e suporte documental."
                ),
                {
                    "saldo_contas_socios_final": format_brl(partner_accounts),
                    "percentual_sobre_receita_anual": format_percent(partner_ratio) if partner_ratio is not None else "[VERIFICAR: receita anual]",
                    "limite_absoluto_relevancia": format_brl(lim_abs),
                    "limite_percentual_relevancia": format_percent(lim_ratio),
                    "classificacao_materialidade": "material" if material else "baixa_materialidade",
                    "criterio_rastreio": "saldo_contas_socios_final consolidado a partir do ultimo JSON trimestral",
                    "contrato_mutuo": "[VERIFICAR: existência, valor, prazo, juros, partes e assinatura]",
                    "iof_recolhido": "[VERIFICAR: memoria de calculo, guia e comprovante de recolhimento quando aplicavel]",
                },
                "Validar razao contabil, extratos, contrato de mutuo ou instrumento equivalente, natureza da movimentacao, prazo, juros e IOF antes do encerramento anual.",
            )
        )

    if revenue > 0 and debt / revenue > Decimal("0.60"):
        findings.append(
            annual_finding(
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
            annual_finding(
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
            annual_finding(
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
            annual_finding(
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
            annual_finding(
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
            annual_finding(
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
        findings.extend(trend_findings(quarters))
        first_tax = quarters[0]["metricas"]["tributos_a_recolher"]
        last_tax = quarters[-1]["metricas"]["tributos_a_recolher"]
        if first_tax > 0 and last_tax > first_tax * Decimal("1.50"):
            findings.append(
                annual_finding(
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
                annual_finding(
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
