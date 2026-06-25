from __future__ import annotations

from decimal import Decimal
from typing import Any

from .config_loader import load_config
from .models import AuditResult, RiskLevel, RuleFinding, TrialBalance
from .risk import classify_total_risk
from .rules import analyze_simples_servicos
from .rules.simples_servicos import (
    calculate_advances,
    calculate_operating_expenses,
    calculate_profit_basis,
    calculate_profit_distribution,
    calculate_revenue,
    calculate_revenue_deductions,
    calculate_tax_expense,
    calculate_tax_liability,
)
from .utils import format_brl, format_percent


def run_quarterly_audit(
    balance: TrialBalance,
    regime_tributario: str = "Simples Nacional",
) -> AuditResult:
    revenue = calculate_revenue(balance)
    revenue_deductions = calculate_revenue_deductions(balance)
    expenses = calculate_operating_expenses(balance)
    payroll = abs(balance.debito_por_grupo("folha"))
    tax_expense = calculate_tax_expense(balance)
    tax_liability = calculate_tax_liability(balance)
    partners = abs(balance.total_por_grupo("socios"))
    profit_dist = calculate_profit_distribution(balance)
    cash = balance.total_por_grupo("caixa") + balance.total_por_grupo("bancos")
    clients = abs(balance.total_por_grupo("clientes"))
    advances = calculate_advances(balance)
    suppliers = abs(balance.total_por_grupo("fornecedores"))
    inventory = abs(balance.total_por_grupo("estoques") + balance.total_por_grupo("estoque"))
    tax_credits = abs(balance.total_por_grupo("creditos_fiscais"))
    debt = abs(balance.total_por_grupo("emprestimos"))
    equity = abs(balance.total_por_grupo("patrimonio") + balance.total_por_grupo("patrimonio_liquido"))

    profit_basis = calculate_profit_basis(balance, revenue, expenses)

    findings = analyze_simples_servicos(balance, profit_basis=profit_basis)
    overall_risk, score = classify_total_risk(findings)

    metricas_valores = _build_metricas_valores(
        revenue, revenue_deductions, tax_expense, tax_liability, payroll, expenses,
        profit_dist, profit_basis, cash, clients, advances, suppliers, inventory,
        tax_credits, debt, equity,
    )

    contexto_regime = _build_contexto_regime_simples(
        regime_tributario, revenue, payroll, tax_expense
    )

    return AuditResult(
        cliente=balance.cliente,
        periodo=balance.periodo,
        cnpj=balance.cnpj,
        regime_tributario=regime_tributario,
        nivel_geral=overall_risk,
        pontuacao_total=score,
        achados=findings,
        resumo_metricas=_build_resumo_metricas(
            revenue, revenue_deductions, tax_expense, tax_liability, payroll, expenses,
            profit_dist, profit_basis, cash, clients, advances, suppliers, inventory,
            tax_credits, debt, equity,
        ),
        metricas_valores=metricas_valores,
        explicacao_pontuacao=_explain_score(findings, overall_risk, score),
        contexto_regime=contexto_regime,
        total_contas_analisadas=len(balance.contas),
        total_regras_verificadas=_total_regras_configuradas(),
    )


def _build_resumo_metricas(
    revenue: Decimal,
    revenue_deductions: Decimal,
    tax_expense: Decimal,
    tax_liability: Decimal,
    payroll: Decimal,
    expenses: Decimal,
    profit_dist: Decimal,
    profit_basis: Any,
    cash: Decimal,
    clients: Decimal,
    advances: Decimal,
    suppliers: Decimal,
    inventory: Decimal,
    tax_credits: Decimal,
    debt: Decimal,
    equity: Decimal,
) -> dict[str, str]:
    return {
        "receita_servicos": format_brl(revenue),
        "deducoes_receita": format_brl(revenue_deductions),
        "tributos": format_brl(tax_liability),
        "tributos_a_recolher": format_brl(tax_liability),
        "tributos_registrados": format_brl(tax_expense),
        "folha_pro_labore": format_brl(payroll),
        "despesas": format_brl(expenses),
        "lucros_distribuidos": format_brl(profit_dist),
        "lucro_apurado_base": format_brl(profit_basis.value),
        "origem_lucro_apurado": profit_basis.source,
        "caixa_bancos": format_brl(cash),
        "clientes_recebiveis": format_brl(clients),
        "adiantamentos": format_brl(advances),
        "fornecedores": format_brl(suppliers),
        "estoques": format_brl(inventory),
        "creditos_fiscais": format_brl(tax_credits),
        "emprestimos": format_brl(debt),
        "patrimonio_liquido": format_brl(equity),
    }


def _total_regras_configuradas() -> int:
    return sum(1 for key in load_config() if key.startswith("SN-"))


def _build_metricas_valores(
    revenue: Decimal,
    revenue_deductions: Decimal,
    tax_expense: Decimal,
    tax_liability: Decimal,
    payroll: Decimal,
    expenses: Decimal,
    profit_dist: Decimal,
    profit_basis: Any,
    cash: Decimal,
    clients: Decimal,
    advances: Decimal,
    suppliers: Decimal,
    inventory: Decimal,
    tax_credits: Decimal,
    debt: Decimal,
    equity: Decimal,
) -> dict[str, Any]:
    def _f(d: Decimal) -> float:
        return float(d)

    result: dict[str, Any] = {
        "receita_servicos": _f(revenue),
        "deducoes_receita": _f(revenue_deductions),
        "tributos_a_recolher": _f(tax_liability),
        "tributos_registrados": _f(tax_expense),
        "folha_pro_labore": _f(payroll),
        "despesas_operacionais": _f(expenses),
        "lucros_distribuidos": _f(profit_dist),
        "lucro_apurado_base": _f(profit_basis.value),
        "origem_lucro_apurado": profit_basis.source,
        "caixa_e_bancos": _f(cash),
        "clientes_recebiveis": _f(clients),
        "adiantamentos": _f(advances),
        "fornecedores": _f(suppliers),
        "estoques": _f(inventory),
        "creditos_fiscais": _f(tax_credits),
        "emprestimos": _f(debt),
        "patrimonio_liquido": _f(equity),
    }

    if revenue > 0:
        result["indicadores_derivados"] = {
            "carga_tributaria_efetiva_percentual": format_percent(tax_expense / revenue),
            "percentual_deducoes_sobre_receita": format_percent(revenue_deductions / revenue),
            "percentual_folha_sobre_receita": format_percent(payroll / revenue),
            "percentual_despesas_sobre_receita": format_percent(expenses / revenue),
            "endividamento_bancario_sobre_receita": format_percent(debt / revenue),
            "resultado_positivo": profit_basis.value >= 0,
        }
    else:
        result["indicadores_derivados"] = {
            "carga_tributaria_efetiva_percentual": "0,0%",
            "percentual_deducoes_sobre_receita": "0,0%",
            "percentual_folha_sobre_receita": "0,0%",
            "percentual_despesas_sobre_receita": "0,0%",
            "endividamento_bancario_sobre_receita": "0,0%",
            "resultado_positivo": profit_basis.value >= 0,
        }

    return result


def _build_contexto_regime_simples(
    regime: str,
    revenue: Decimal,
    payroll: Decimal,
    taxes: Decimal,
) -> dict[str, Any]:
    annual_proxy = revenue * Decimal("4")

    faixa = _simples_faixa(annual_proxy)
    aliquota_esperada = _simples_aliquota_esperada(annual_proxy)

    fator_r: str | None = None
    fator_r_threshold = "0,28"
    if payroll > 0 and revenue > 0:
        fator_r = format_percent(payroll / revenue)

    observacoes: list[str] = []
    if fator_r:
        fator_r_valor = payroll / revenue if revenue > 0 else Decimal("0")
        if fator_r_valor < Decimal("0.28"):
            observacoes.append(
                f"Fator R estimado de {fator_r} está abaixo do threshold de 28% "
                "— empresa permanece no Anexo V (alíquota mais elevada)."
            )
        else:
            observacoes.append(
                f"Fator R estimado de {fator_r} está acima de 28% "
                "— empresa pode migrar para o Anexo III (alíquota reduzida)."
            )

    sublimite_risco = annual_proxy > Decimal("3600000")
    if sublimite_risco:
        observacoes.append(
            "Receita anualizada supera R$ 3.600.000 — verificar sublimite estadual "
            "para ICMS/ISS fora do DAS (art. 20 da LC 123/2006)."
        )

    return {
        "regime": regime,
        "faixa_receita_estimada": faixa,
        "aliquota_efetiva_esperada": aliquota_esperada,
        "fator_r_calculado": fator_r,
        "fator_r_threshold": fator_r_threshold,
        "sublimite_risco": sublimite_risco,
        "observacoes": observacoes,
    }


def _simples_faixa(annual_revenue: Decimal) -> str:
    faixas = [
        (Decimal("180000"), "1ª faixa (até R$ 180.000,00/ano)"),
        (Decimal("360000"), "2ª faixa (R$ 180.000,01 a R$ 360.000,00/ano)"),
        (Decimal("720000"), "3ª faixa (R$ 360.000,01 a R$ 720.000,00/ano)"),
        (Decimal("1800000"), "4ª faixa (R$ 720.000,01 a R$ 1.800.000,00/ano)"),
        (Decimal("3600000"), "5ª faixa (R$ 1.800.000,01 a R$ 3.600.000,00/ano)"),
        (Decimal("4800000"), "6ª faixa (R$ 3.600.000,01 a R$ 4.800.000,00/ano)"),
    ]
    for limite, descricao in faixas:
        if annual_revenue <= limite:
            return descricao
    return "Acima do limite do Simples Nacional"


def _simples_aliquota_esperada(annual_revenue: Decimal) -> str:
    aliquotas = [
        (Decimal("180000"), "6,0%"),
        (Decimal("360000"), "11,2%"),
        (Decimal("720000"), "13,5%"),
        (Decimal("1800000"), "16,0%"),
        (Decimal("3600000"), "21,0%"),
        (Decimal("4800000"), "33,0%"),
    ]
    for limite, aliquota in aliquotas:
        if annual_revenue <= limite:
            return aliquota
    return "Acima do limite"


def _explain_score(
    findings: list[RuleFinding],
    overall_risk: RiskLevel,
    score: int,
) -> list[str]:
    if not findings:
        return [
            "Pontuação total igual a 0 porque nenhuma regra foi acionada.",
            "Nível geral baixo porque não houve achados de risco médio ou alto.",
        ]

    high_findings = [f for f in findings if f.nivel == RiskLevel.ALTO]
    medium_findings = [f for f in findings if f.nivel == RiskLevel.MEDIO]
    low_findings = [f for f in findings if f.nivel == RiskLevel.BAIXO]

    high_score = sum(f.pontuacao for f in high_findings)
    medium_score = sum(f.pontuacao for f in medium_findings)
    low_score = sum(f.pontuacao for f in low_findings)

    top_findings = sorted(findings, key=lambda f: f.pontuacao, reverse=True)[:3]
    top_summary = ", ".join(
        f"{f.codigo} \u2014 {f.titulo} ({f.pontuacao} pts)"
        for f in top_findings
    )

    reasons = [
        f"Pontuação total de {score} pontos, somando os pesos das regras acionadas.",
    ]

    if high_findings:
        lbl = "achado" if len(high_findings) == 1 else "achados"
        reasons.append(f"Risco alto: {len(high_findings)} {lbl} somando {high_score} pontos.")
    if medium_findings:
        lbl = "achado" if len(medium_findings) == 1 else "achados"
        reasons.append(f"Risco médio: {len(medium_findings)} {lbl} somando {medium_score} pontos.")
    if low_findings:
        lbl = "achado" if len(low_findings) == 1 else "achados"
        reasons.append(f"Risco baixo: {len(low_findings)} {lbl} somando {low_score} pontos.")

    reasons.append(f"Maiores contribuições para o score: {top_summary}.")

    if overall_risk == RiskLevel.ALTO:
        if high_findings:
            reasons.append("Nível geral alto porque existe pelo menos um achado classificado como alto.")
        else:
            reasons.append("Nível geral alto porque a pontuação total atingiu 70 pontos ou mais.")
    elif overall_risk == RiskLevel.MEDIO:
        reasons.append(
            "Nível geral médio porque existe achado de risco médio ou a pontuação total atingiu pelo menos 30 pontos."
        )
    else:
        reasons.append(
            "Nível geral baixo porque a pontuação ficou abaixo de 30 e não houve achados de risco médio ou alto."
        )

    return reasons
