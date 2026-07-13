from __future__ import annotations

from decimal import Decimal
from typing import Any

from .account_classification import build_account_classification_report
from .config_loader import load_config, load_simples_anexos
from .models import AuditResult, RiskLevel, RuleFinding, TrialBalance
from .risk import classify_total_risk
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
    overall_risk, score = classify_total_risk(findings)

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
        achados=findings,
        resumo_metricas=_build_resumo_metricas(
            revenue, revenue_deductions, tax_expense, tax_liability, payroll, expenses,
            third_party_services, partners, profit_dist, profit_basis, cash, clients, advances, customer_advances,
            suppliers, inventory, tax_credits, cogs, debt, equity,
        ),
        metricas_valores=metricas_valores,
        explicacao_pontuacao=_explain_score(findings, overall_risk, score),
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


def _build_contexto_regime_simples(
    regime: str,
    revenue: Decimal,
    payroll: Decimal,
    taxes: Decimal,
    conjunto_regras: str,
    rbt12_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    annual_proxy = revenue * Decimal("4")
    rbt12_revenue = _context_decimal(rbt12_context, "receita")
    rbt12_payroll = _context_decimal(rbt12_context, "folha")
    has_rbt12_revenue = rbt12_revenue is not None and rbt12_revenue > 0
    if has_rbt12_revenue:
        base_revenue = rbt12_revenue or Decimal("0")
        base_description = str((rbt12_context or {}).get("base_calculo") or "RBT12 consolidado a partir do historico salvo")
    else:
        base_revenue = annual_proxy
        base_description = "receita trimestral anualizada (receita x 4)"

    faixa = _simples_faixa(base_revenue)
    fator_r: str | None = None
    fator_r_valor: Decimal | None = None
    fator_r_base = "nao calculado"
    fator_r_threshold = "28%"
    if revenue > 0 and conjunto_regras in {"simples_servicos", "simples_comercio_servicos"}:
        if has_rbt12_revenue and rbt12_payroll is not None:
            fator_r_valor = rbt12_payroll / base_revenue
            fator_r_base = "RBT12 consolidado"
        else:
            fator_r_valor = payroll / revenue
            fator_r_base = "trimestre analisado"
        fator_r = format_percent(fator_r_valor)

    anexo_key, anexo_label = _simples_anexo_estimado(conjunto_regras, fator_r_valor)
    aliquota_info = _simples_aliquota_esperada(base_revenue, anexo_key) if anexo_key else None
    aliquota_esperada = _aliquota_context_label(aliquota_info, anexo_label)

    observacoes: list[str] = []
    if conjunto_regras == "simples_comercio":
        observacoes.append(
            "Atividade analisada como comercio: contexto tributario estimado pelo Anexo I; validar segregacao de receitas, estoque, fornecedores, CMV, ICMS e possivel ICMS-ST."
        )
    elif conjunto_regras == "simples_comercio_servicos":
        observacoes.append(
            "Atividade analisada como comercio e servicos: nao ha aliquota unica sem segregacao; validar receitas por natureza, Anexo I para comercio e Anexo III/V para servicos, Fator R, ISS, ICMS e ICMS-ST."
        )

    if fator_r:
        if fator_r_valor is not None and fator_r_valor < Decimal("0.28"):
            observacoes.append(
                f"Fator R trimestral estimado de {fator_r} está abaixo da referência de 28%. "
                "Para servicos sujeitos ao Fator R, o contexto estimado aponta para Anexo V; validar o calculo oficial com folha e receita acumuladas dos ultimos 12 meses antes de concluir sobre o anexo aplicavel."
            )
        else:
            observacoes.append(
                f"Fator R trimestral estimado de {fator_r} está acima de 28%. "
                "Para servicos sujeitos ao Fator R, o contexto estimado aponta para Anexo III; validar o calculo oficial com folha e receita acumuladas dos ultimos 12 meses antes de concluir sobre o anexo aplicavel."
            )

    sublimite_risco = base_revenue > Decimal("3600000")
    if sublimite_risco:
        observacoes.append(
            "Receita trimestral anualizada supera R$ 3.600.000 — verificar receita acumulada dos últimos 12 meses, sublimite estadual "
            "para ICMS/ISS fora do DAS (art. 20 da LC 123/2006)."
        )

    if has_rbt12_revenue:
        observacoes.append(
            "O contexto tributario usou RBT12 consolidado pelo historico disponivel; conferir PGDAS-D e segregacao oficial antes de emitir conclusao definitiva."
        )
    else:
        observacoes.append(
            "Sem RBT12 completo informado ao motor, a faixa e a aliquota usam receita trimestral anualizada apenas como alerta."
        )

    return {
        "regime": regime,
        "atividade": conjunto_regras,
        "faixa_receita_estimada": faixa,
        "aliquota_efetiva_esperada": aliquota_esperada,
        "anexo_estimado": anexo_label,
        "aliquota_nominal_estimada": aliquota_info["aliquota_nominal"] if aliquota_info else "[VERIFICAR: receita segregada por anexo]",
        "parcela_deduzir_estimada": aliquota_info["parcela_deduzir"] if aliquota_info else "[VERIFICAR: receita segregada por anexo]",
        "base_calculo_estimativa": base_description,
        "receita_rbt12_utilizada": format_brl(rbt12_revenue) if has_rbt12_revenue else None,
        "folha_rbt12_utilizada": format_brl(rbt12_payroll) if rbt12_payroll is not None else None,
        "rbt12_disponivel": has_rbt12_revenue,
        "origem_rbt12": str((rbt12_context or {}).get("origem") or ""),
        "fonte_tabela_anexos": "Lei Complementar n. 123/2006, anexos I, III e V",
        "fator_r_calculado": fator_r,
        "fator_r_base": fator_r_base,
        "fator_r_threshold": fator_r_threshold,
        "sublimite_risco": sublimite_risco,
        "observacoes": observacoes,
    }


def _normalize_rbt12_context(context: dict[str, Any] | None) -> dict[str, Any] | None:
    if not context:
        return None

    normalized = dict(context)
    for key in ("receita", "folha"):
        value = _context_decimal(normalized, key)
        if value is not None:
            normalized[key] = value
    return normalized


def _context_decimal(context: dict[str, Any] | None, key: str) -> Decimal | None:
    if not context:
        return None

    value = context.get(key)
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


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


def _simples_anexo_estimado(conjunto_regras: str, fator_r_valor: Decimal | None) -> tuple[str | None, str]:
    if conjunto_regras == "simples_comercio":
        return "anexo_i", "Anexo I (comercio)"
    if conjunto_regras == "simples_comercio_servicos":
        return None, "Anexos I e III/V (exige segregacao de receitas)"
    if fator_r_valor is not None and fator_r_valor < Decimal("0.28"):
        return "anexo_v", "Anexo V estimado (Fator R trimestral abaixo de 28%)"
    return "anexo_iii", "Anexo III estimado"


def _simples_aliquota_esperada(annual_revenue: Decimal, anexo_key: str) -> dict[str, str] | None:
    anexos = load_simples_anexos().get("anexos", {})
    anexo = anexos.get(anexo_key)
    if not anexo:
        return None

    if annual_revenue <= 0:
        return {
            "anexo": str(anexo.get("nome") or anexo_key),
            "aliquota_nominal": "0,00%",
            "parcela_deduzir": "R$ 0,00",
            "aliquota_efetiva": "0,00%",
        }

    for faixa in anexo.get("faixas", []):
        limite = Decimal(str(faixa.get("limite_superior", 0)))
        if annual_revenue <= limite:
            nominal = Decimal(str(faixa.get("aliquota", 0)))
            deduction = Decimal(str(faixa.get("parcela_deduzir", 0)))
            effective = max((annual_revenue * nominal - deduction) / annual_revenue, Decimal("0"))
            return {
                "anexo": str(anexo.get("nome") or anexo_key),
                "aliquota_nominal": format_percent(nominal),
                "parcela_deduzir": format_brl(deduction),
                "aliquota_efetiva": format_percent(effective),
            }

    return {
        "anexo": str(anexo.get("nome") or anexo_key),
        "aliquota_nominal": "Acima do limite",
        "parcela_deduzir": "Acima do limite",
        "aliquota_efetiva": "Acima do limite",
    }


def _aliquota_context_label(aliquota_info: dict[str, str] | None, anexo_label: str) -> str:
    if not aliquota_info:
        return "[VERIFICAR: segregar receita de comercio e servicos para estimar aliquota por anexo]"
    return (
        f"{anexo_label}: nominal {aliquota_info['aliquota_nominal']}; "
        f"efetiva estimada {aliquota_info['aliquota_efetiva']}; "
        f"parcela a deduzir {aliquota_info['parcela_deduzir']}"
    )


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
    compound_findings = [f for f in findings if f.codigo.startswith("SN-COMP")]
    compound_score = sum(f.pontuacao for f in compound_findings)
    base_score = score - compound_score

    top_findings = sorted(findings, key=lambda f: f.pontuacao, reverse=True)[:3]
    top_summary = ", ".join(
        f"{f.codigo} \u2014 {f.titulo} ({f.pontuacao} pts)"
        for f in top_findings
    )

    reasons = [
        f"Pontuação total de {score} pontos, somando os pesos das regras acionadas.",
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
