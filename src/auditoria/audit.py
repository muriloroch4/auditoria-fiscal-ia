from __future__ import annotations

from .models import AuditResult, RiskLevel, RuleFinding, TrialBalance
from .risk import classify_total_risk
from .rules import analyze_simples_servicos
from .rules.simples_servicos import calculate_profit_basis


def run_quarterly_audit(balance: TrialBalance) -> AuditResult:
    findings = analyze_simples_servicos(balance)
    overall_risk, score = classify_total_risk(findings)
    revenue = abs(balance.credito_por_grupo("receita"))
    expenses = abs(balance.debito_por_grupo("despesas"))
    profit_basis = calculate_profit_basis(balance, revenue, expenses)

    return AuditResult(
        cliente=balance.cliente,
        periodo=balance.periodo,
        nivel_geral=overall_risk,
        pontuacao_total=score,
        achados=findings,
        resumo_metricas={
            "receita_servicos": _money(abs(balance.credito_por_grupo("receita"))),
            "tributos": _money(abs(balance.total_por_grupo("tributos"))),
            "folha_pro_labore": _money(abs(balance.debito_por_grupo("folha"))),
            "despesas": _money(abs(balance.debito_por_grupo("despesas"))),
            "lucros_distribuidos": _money(abs(balance.debito_por_grupo("lucros"))),
            "lucro_apurado_base": _money(profit_basis.value),
            "origem_lucro_apurado": profit_basis.source,
            "caixa_bancos": _money(balance.total_por_grupo("caixa") + balance.total_por_grupo("bancos")),
        },
        explicacao_pontuacao=_explain_score(findings, overall_risk, score),
    )


def _money(value) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _explain_score(findings: list[RuleFinding], overall_risk: RiskLevel, score: int) -> list[str]:
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

    high_label = "achado" if len(high_findings) == 1 else "achados"
    medium_label = "achado" if len(medium_findings) == 1 else "achados"

    top_findings = sorted(findings, key=lambda f: f.pontuacao, reverse=True)[:3]
    top_summary = ", ".join(
        f"{f.codigo} \u2014 {f.titulo} ({f.pontuacao} pts)"
        for f in top_findings
    )

    reasons = [
        f"Pontuação total de {score} pontos, somando os pesos das regras acionadas.",
    ]

    if high_findings:
        reasons.append(
            f"Risco alto: {len(high_findings)} {high_label} somando {high_score} pontos."
        )
    if medium_findings:
        reasons.append(
            f"Risco médio: {len(medium_findings)} {medium_label} somando {medium_score} pontos."
        )
    if low_findings:
        low_label = "achado" if len(low_findings) == 1 else "achados"
        reasons.append(
            f"Risco baixo: {len(low_findings)} {low_label} somando {low_score} pontos."
        )

    reasons.append(
        f"Maiores contribuições para o score: {top_summary}."
    )

    if overall_risk == RiskLevel.ALTO:
        if high_findings:
            reasons.append(
                "Nível geral alto porque existe pelo menos um achado classificado como alto."
            )
        else:
            reasons.append(
                "Nível geral alto porque a pontuação total atingiu 70 pontos ou mais."
            )
    elif overall_risk == RiskLevel.MEDIO:
        reasons.append(
            "Nível geral médio porque existe achado de risco médio ou a pontuação total atingiu pelo menos 30 pontos."
        )
    else:
        reasons.append(
            "Nível geral baixo porque a pontuação ficou abaixo de 30 e não houve achados de risco médio ou alto."
        )

    return reasons
