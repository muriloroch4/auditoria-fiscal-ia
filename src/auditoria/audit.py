from __future__ import annotations

from decimal import Decimal
from typing import Any

from .account_classification import build_account_classification_report
from .config_loader import load_config
from .models import AuditResult, RiskLevel, RuleFinding, TrialBalance
from .risk import max_score_for_ruleset, score_findings_0_100
from .rules import analyze_simples_nacional, normalize_ruleset
from .rules.metricas import (
    calculate_advances,
    calculate_customer_advances,
    calculate_cost_of_goods,
    calculate_inventory,
    calculate_operating_expenses,
    calculate_partner_accounts_balance,
    calculate_profit_basis,
    calculate_profit_distribution,
    calculate_revenue,
    calculate_revenue_deductions,
    calculate_suppliers,
    calculate_tax_credits,
    calculate_tax_expense,
    calculate_tax_liability,
    calculate_third_party_services_expense,
)
from .tax_context import (
    aliquota_context_label as _aliquota_context_label,
    build_contexto_regime_simples as _build_contexto_regime_simples,
    context_decimal as _context_decimal,
    normalize_rbt12_context as _normalize_rbt12_context,
    simples_aliquota_esperada as _simples_aliquota_esperada,
    simples_anexo_estimado as _simples_anexo_estimado,
    simples_faixa as _simples_faixa,
)
from .utils import format_brl, format_percent


def run_quarterly_audit(
    balance: TrialBalance,
    regime_tributario: str = "Simples Nacional",
    atividade: str = "servicos",
    contexto_rbt12: dict[str, Any] | None = None,
) -> AuditResult:
    conjunto_regras = normalize_ruleset(atividade)
    rbt12_context = _normalize_rbt12_context(contexto_rbt12)
    revenue = calculate_revenue(balance)
    revenue_deductions = calculate_revenue_deductions(balance)
    expenses = calculate_operating_expenses(balance)
    third_party_services = calculate_third_party_services_expense(balance)
    payroll = abs(balance.debito_por_grupo("folha"))
    tax_expense = calculate_tax_expense(balance)
    tax_liability = calculate_tax_liability(balance)
    partners = calculate_partner_accounts_balance(balance)
    profit_dist = calculate_profit_distribution(balance)
    cash = balance.total_por_grupo("caixa") + balance.total_por_grupo("bancos")
    clients = abs(balance.total_por_grupo("clientes"))
    advances = calculate_advances(balance)
    customer_advances = calculate_customer_advances(balance)
    suppliers = calculate_suppliers(balance)
    inventory = calculate_inventory(balance)
    tax_credits = calculate_tax_credits(balance)
    cogs = calculate_cost_of_goods(balance)
    debt = abs(balance.total_por_grupo("emprestimos"))
    equity = abs(balance.total_por_grupo("patrimonio") + balance.total_por_grupo("patrimonio_liquido"))

    profit_basis = calculate_profit_basis(balance, revenue, expenses)

    findings = analyze_simples_nacional(
        balance,
        conjunto_regras,
        profit_basis=profit_basis,
        rbt12_context=rbt12_context,
    )
    cfg = load_config()
    score_details = score_findings_0_100(findings, max_score_for_ruleset(cfg, conjunto_regras))
    overall_risk = score_details.nivel
    score = score_details.pontuacao_total

    metricas_valores = _build_metricas_valores(
        revenue, revenue_deductions, tax_expense, tax_liability, payroll, expenses,
        third_party_services, partners, profit_dist, profit_basis, cash, clients, advances, customer_advances,
        suppliers, inventory, tax_credits, cogs, debt, equity,
    )

    contexto_regime = _build_contexto_regime_simples(
        regime_tributario, revenue, payroll, tax_expense, conjunto_regras, rbt12_context
    )

    return AuditResult(
        cliente=balance.cliente,
        periodo=balance.periodo,
        cnpj=balance.cnpj,
        regime_tributario=regime_tributario,
        nivel_geral=overall_risk,
        pontuacao_total=score,
        pontuacao_bruta=score_details.pontuacao_bruta,
        pontuacao_maxima_aplicavel=score_details.pontuacao_maxima_aplicavel,
        escala_pontuacao=score_details.escala_pontuacao,
        achados=findings,
        resumo_metricas=_build_resumo_metricas(
            revenue, revenue_deductions, tax_expense, tax_liability, payroll, expenses,
            third_party_services, partners, profit_dist, profit_basis, cash, clients, advances, customer_advances,
            suppliers, inventory, tax_credits, cogs, debt, equity,
        ),
        metricas_valores=metricas_valores,
        explicacao_pontuacao=_explain_score(
            findings,
            overall_risk,
            score,
            score_details.pontuacao_bruta,
            score_details.pontuacao_maxima_aplicavel,
        ),
        contexto_regime=contexto_regime,
        total_contas_analisadas=len(balance.contas),
        total_regras_verificadas=_total_regras_configuradas(conjunto_regras),
        conjunto_regras=conjunto_regras,
        classificacao_contas=build_account_classification_report(balance),
    )


def _build_resumo_metricas(
    revenue: Decimal,
    revenue_deductions: Decimal,
    tax_expense: Decimal,
    tax_liability: Decimal,
    payroll: Decimal,
    expenses: Decimal,
    third_party_services: Decimal,
    partners: Decimal,
    profit_dist: Decimal,
    profit_basis: Any,
    cash: Decimal,
    clients: Decimal,
    advances: Decimal,
    customer_advances: Decimal,
    suppliers: Decimal,
    inventory: Decimal,
    tax_credits: Decimal,
    cogs: Decimal,
    debt: Decimal,
    equity: Decimal,
) -> dict[str, str]:
    return {
        "receita_servicos": format_brl(revenue),
        "receita_operacional": format_brl(revenue),
        "deducoes_receita": format_brl(revenue_deductions),
        "tributos": format_brl(tax_liability),
        "tributos_a_recolher": format_brl(tax_liability),
        "tributos_registrados": format_brl(tax_expense),
        "folha_pro_labore": format_brl(payroll),
        "despesas": format_brl(expenses),
        "servicos_terceiros": format_brl(third_party_services),
        "saldo_contas_socios": format_brl(partners),
        "lucros_distribuidos": format_brl(profit_dist),
        "lucro_apurado_base": format_brl(profit_basis.value),
        "origem_lucro_apurado": profit_basis.source,
        "caixa_bancos": format_brl(cash),
        "clientes_recebiveis": format_brl(clients),
        "adiantamentos": format_brl(advances),
        "adiantamentos_clientes": format_brl(customer_advances),
        "fornecedores": format_brl(suppliers),
        "estoques": format_brl(inventory),
        "cmv_custos": format_brl(cogs),
        "creditos_fiscais": format_brl(tax_credits),
        "emprestimos": format_brl(debt),
        "patrimonio_liquido": format_brl(equity),
    }


def _total_regras_configuradas(conjunto_regras: str) -> int:
    cfg = load_config()
    configured = cfg.get("conjuntos_regras", {}).get(conjunto_regras)
    if configured:
        return len(configured)
    return sum(1 for key in cfg if key.startswith("SN-"))


def _build_metricas_valores(
    revenue: Decimal,
    revenue_deductions: Decimal,
    tax_expense: Decimal,
    tax_liability: Decimal,
    payroll: Decimal,
    expenses: Decimal,
    third_party_services: Decimal,
    partners: Decimal,
    profit_dist: Decimal,
    profit_basis: Any,
    cash: Decimal,
    clients: Decimal,
    advances: Decimal,
    customer_advances: Decimal,
    suppliers: Decimal,
    inventory: Decimal,
    tax_credits: Decimal,
    cogs: Decimal,
    debt: Decimal,
    equity: Decimal,
) -> dict[str, Any]:
    def _f(d: Decimal) -> float:
        return float(d)

    result: dict[str, Any] = {
        "receita_servicos": _f(revenue),
        "receita_operacional": _f(revenue),
        "deducoes_receita": _f(revenue_deductions),
        "tributos_a_recolher": _f(tax_liability),
        "tributos_registrados": _f(tax_expense),
        "folha_pro_labore": _f(payroll),
        "despesas_operacionais": _f(expenses),
        "servicos_terceiros": _f(third_party_services),
        "saldo_contas_socios": _f(partners),
        "lucros_distribuidos": _f(profit_dist),
        "lucro_apurado_base": _f(profit_basis.value),
        "origem_lucro_apurado": profit_basis.source,
        "caixa_e_bancos": _f(cash),
        "clientes_recebiveis": _f(clients),
        "adiantamentos": _f(advances),
        "adiantamentos_clientes": _f(customer_advances),
        "fornecedores": _f(suppliers),
        "estoques": _f(inventory),
        "cmv_custos": _f(cogs),
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
            "percentual_servicos_terceiros_sobre_despesas": format_percent(third_party_services / expenses) if expenses > 0 else "0,0%",
            "percentual_cmv_sobre_receita": format_percent(cogs / revenue),
            "endividamento_bancario_sobre_receita": format_percent(debt / revenue),
            "resultado_positivo": profit_basis.value >= 0,
        }
    else:
        result["indicadores_derivados"] = {
            "carga_tributaria_efetiva_percentual": "0,0%",
            "percentual_deducoes_sobre_receita": "0,0%",
            "percentual_folha_sobre_receita": "0,0%",
            "percentual_despesas_sobre_receita": "0,0%",
            "percentual_servicos_terceiros_sobre_despesas": format_percent(third_party_services / expenses) if expenses > 0 else "0,0%",
            "percentual_cmv_sobre_receita": "0,0%",
            "endividamento_bancario_sobre_receita": "0,0%",
            "resultado_positivo": profit_basis.value >= 0,
        }

    return result


def _explain_score(
    findings: list[RuleFinding],
    overall_risk: RiskLevel,
    score: int,
    raw_score: int,
    max_score: int,
) -> list[str]:
    if not findings:
        return [
            "Pontuação total igual a 0/100 porque nenhuma regra foi acionada.",
            "Nível geral baixo porque não houve achados de risco médio ou alto.",
        ]

    high_findings = [f for f in findings if f.nivel == RiskLevel.ALTO]
    medium_findings = [f for f in findings if f.nivel == RiskLevel.MEDIO]
    low_findings = [f for f in findings if f.nivel == RiskLevel.BAIXO]

    high_score = sum(f.pontuacao for f in high_findings)
    medium_score = sum(f.pontuacao for f in medium_findings)
    low_score = sum(f.pontuacao for f in low_findings)
    compound_findings = [f for f in findings if f.codigo.startswith("SN-COMP")]
    compound_score = sum(f.pontuacao for f in compound_findings)
    base_score = raw_score - compound_score

    top_findings = sorted(findings, key=lambda f: f.pontuacao, reverse=True)[:3]
    top_summary = ", ".join(
        f"{f.codigo} \u2014 {f.titulo} ({f.pontuacao} pts)"
        for f in top_findings
    )

    reasons = [
        (
            f"Pontuação total normalizada de {score}/100, calculada a partir de "
            f"{raw_score} ponto(s) bruto(s) sobre {max_score} ponto(s) máximos aplicáveis ao conjunto de regras."
        ),
    ]

    if compound_findings:
        reasons.append(
            f"Pontuação base de {base_score} ponto(s), com {compound_score} ponto(s) de regras compostas "
            "(SN-COMP) tratadas como reforço contextual de achados correlacionados."
        )

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
            reasons.append("Nível geral alto porque existe pelo menos um achado classificado como alto, aplicando piso de 70/100.")
        else:
            reasons.append("Nível geral alto porque a pontuação total atingiu 70/100 ou mais.")
    elif overall_risk == RiskLevel.MEDIO:
        reasons.append(
            "Nível geral médio porque existe achado de risco médio ou a pontuação total atingiu pelo menos 30/100."
        )
    else:
        reasons.append(
            "Nível geral baixo porque a pontuação ficou abaixo de 30/100 e não houve achados de risco médio ou alto."
        )

    return reasons
