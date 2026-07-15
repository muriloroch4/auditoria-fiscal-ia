from __future__ import annotations

from typing import Any

from .evidence import structured_finding_evidence
from .models import AuditResult, RiskLevel, RuleFinding
from .serializer_common import (
    BASE_NORMAS,
    VERIFY,
    append_unique,
    area_relacionada,
    clean_text,
    format_evidence,
    normalize_normas,
    severity_label,
    severity_text,
    shorten,
)


def finding_to_summary_dict(finding: RuleFinding) -> dict[str, Any]:
    return {
        "codigo": finding.codigo or VERIFY,
        "severidade": severity_label(finding.nivel),
        "achado": shorten(finding.titulo or finding.descricao or VERIFY, 180),
        "evidencia_identificada": format_evidence(finding.evidencia),
        "evidencia": structured_finding_evidence(finding),
        "impacto_tecnico": impacto_tecnico(finding),
        "pontuacao": finding.pontuacao,
        "norma_fundamento": normalize_normas(finding.normas_aplicaveis),
    }


def recomendacoes_tecnicas(findings: list[RuleFinding]) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []
    for index, finding in enumerate(findings, start=1):
        recommendations.append(
            {
                "ordem": index,
                "descricao": clean_text(finding.recomendacao or VERIFY),
                "area_relacionada": area_relacionada(finding.codigo),
                "prioridade": severity_label(finding.nivel),
            }
        )
    return recommendations


def principais_pontos(result: AuditResult, findings: list[RuleFinding]) -> list[str]:
    if not findings:
        return [
            "Nenhuma regra de risco foi acionada no período analisado.",
            f"Pontuação total apurada: {result.pontuacao_total}/100.",
        ]

    points = [
        f"{finding.codigo}: {shorten(finding.titulo, 110)} ({severity_text(finding.nivel)}, {finding.pontuacao} ponto(s))."
        for finding in findings[:5]
    ]
    if len(findings) > 5:
        points.append(f"Há mais {len(findings) - 5} achado(s) técnico(s) no período.")
    return points


def fundamentacao_resumida(result: AuditResult, normas: list[str]) -> str:
    if normas:
        return (
            "A fundamentação técnica considera as normas aplicáveis aos achados acionados pelo motor de regras, "
            "com foco em escrituração regular, representação fidedigna das informações contábeis e aderência ao "
            f"regime tributário {result.regime_tributario}."
        )
    return (
        "A fundamentação técnica deve ser confirmada a partir da documentação de suporte, pois não houve norma "
        "específica vinculada a achados no JSON."
    )


def observacoes_tecnicas(result: AuditResult) -> list[str]:
    context = result.contexto_regime or {}
    observations: list[str] = []

    if result.regime_tributario:
        observations.append(
            f"Regime tributário informado: {result.regime_tributario}. Validar enquadramento, anexo aplicável e eventuais sublimites com documentação fiscal."
        )
    if context.get("faixa_receita_estimada"):
        observations.append(f"Faixa estimada do Simples Nacional: {context['faixa_receita_estimada']}.")
    if context.get("anexo_estimado"):
        observations.append(f"Anexo tributário estimado pelo motor: {context['anexo_estimado']}.")
    if context.get("aliquota_efetiva_esperada"):
        observations.append(f"Alíquota efetiva esperada informada pelo contexto tributário: {context['aliquota_efetiva_esperada']}.")
    if context.get("base_calculo_estimativa"):
        observations.append(f"Base da estimativa tributária: {context['base_calculo_estimativa']}.")
    if context.get("receita_rbt12_utilizada"):
        observations.append(f"RBT12 utilizado pelo motor: {context['receita_rbt12_utilizada']}.")
    if context.get("folha_rbt12_utilizada"):
        observations.append(f"Folha/RBT12 utilizada para Fator R: {context['folha_rbt12_utilizada']}.")
    if context.get("rbt12_disponivel") is False:
        observations.append("RBT12 completo nao foi informado; estimativas de limite, faixa e aliquota devem ser tratadas como alerta.")
    if context.get("fator_r_calculado"):
        observations.append(
            f"Fator R trimestral estimado: {context['fator_r_calculado']}; validar o cálculo oficial com folha e receita acumuladas dos últimos 12 meses."
        )

    for item in context.get("observacoes") or []:
        if item:
            observations.append(shorten(str(item), 260))

    observations.append(
        "A escrituração e os saldos devem ser confrontados com documentos hábeis para confirmar representação fidedigna."
    )
    return observations


def texto_conclusivo(result: AuditResult, opinion: str, findings: list[RuleFinding]) -> str:
    if not findings:
        return (
            "Com base exclusivamente no JSON de auditoria trimestral, não foram identificados achados materiais "
            "no período. A conclusão depende da validação documental dos saldos e lançamentos contábeis."
        )

    if opinion == "adversa":
        return (
            "Com base exclusivamente no JSON de auditoria trimestral, os achados indicam risco técnico elevado e "
            "requerem regularização prioritária. A conclusão não representa auditoria independente definitiva e "
            "depende da validação documental dos fatos identificados."
        )
    if opinion == "com_ressalva":
        return (
            "Com base exclusivamente no JSON de auditoria trimestral, os achados indicam pontos que exigem validação "
            "documental e saneamento antes do fechamento definitivo do período. A conclusão depende da validação "
            "documental dos saldos, documentos fiscais e registros contábeis."
        )
    return (
        "Com base exclusivamente no JSON de auditoria trimestral, a análise não indica inconsistência material "
        "suficiente para modificar a conclusão sugerida, sem dispensar validação documental."
    )


def impacto_tecnico(finding: RuleFinding) -> str:
    code = finding.codigo[:6]
    prefix = classificacao_tecnica(finding)
    impacts = {
        "SN-001": "Risco de extrapolação de limite, sublimite ou desenquadramento do Simples Nacional.",
        "SN-002": "Possível subapuração tributária ou divergência entre receita e tributos reconhecidos.",
        "SN-003": "Risco de enquadramento incorreto do anexo e inconsistência no Fator R.",
        "SN-004": "Risco societário e fiscal por distribuição sem lastro contábil suficiente.",
        "SN-005": "Indício de saldo com sócios, administradores ou mútuo sem validação documental de contrato e IOF.",
        "SN-006": "Possível inconsistência de conciliação financeira ou saldo contábil sem suporte.",
        "SN-007": "Possível distorção de resultado por despesas elevadas ou sem aderência operacional.",
        "SN-008": "Indício de receita não reconhecida ou divergência entre movimentação e faturamento.",
        "SN-009": "Risco de desequilíbrio econômico, prejuízo relevante ou fragilidade de continuidade.",
        "SN-010": "Risco de realização de recebíveis, baixa pendente ou saldo sem conciliação suficiente.",
        "SN-011": "Risco documental por adiantamentos sem contraprestação, baixa ou suporte adequado.",
        "SN-012": "Risco de acúmulo de passivo tributário, regularidade fiscal ou parcelamento pendente.",
        "SN-013": "Risco de despesas sem comprovação ou gastos particulares registrados na empresa.",
        "SN-014": "Risco trabalhista e contábil por ausência de provisões compatíveis com a folha.",
        "SN-015": "Risco de distorção de estoque, giro comercial ou baixa pendente de mercadorias.",
        "SN-016": "Risco de passivo comercial sem conciliação, compras sem giro ou baixa de fornecedores pendente.",
        "SN-017": "Risco de ativo fiscal sem suporte documental ou crédito incompatível com o Simples Nacional.",
        "SN-018": "Risco de margem e resultado distorcidos por CMV ausente, baixo ou excessivo.",
        "SN-019": "Risco de sublimite estadual, ICMS fora do DAS ou apuração fiscal incompleta.",
        "SN-020": "Risco de anexo, Fator R, ISS/ICMS ou DAS incorreto por falta de segregação de receitas.",
        "SN-021": "Risco de resultado superestimado por despesas, custos ou apropriações de competência não reconhecidos.",
        "SN-022": "Risco de saldo de caixa físico sem suporte operacional, bancário ou documental compatível.",
        "SN-023": "Ponto de atenção sobre recebimento à vista, baixa de recebíveis ou ausência de controle de clientes.",
        "SN-024": "Ponto de atencao documental sobre ICMS-ST, creditos fiscais, ressarcimentos ou saldos recuperaveis em operacao comercial.",
        "SN-025": "Ponto de atencao documental sobre pagamentos e servicos de terceiros lancados diretamente em despesas.",
        "SN-026": "Risco fiscal e documental se houver receita ja liquidada sem baixa, emissao fiscal ou reconhecimento contabil/fiscal adequado.",
        "SN-027": "Risco de classificação contábil inadequada, baixa pendente ou conta redutora sem identificação clara.",
        "SN-028": "Risco de passivo financeiro sem apropriação de juros, encargos ou despesas financeiras por competência.",
        "SN-COM": "Risco composto por combinação de achados, exigindo análise prioritária integrada.",
    }
    impact = impacts.get(code, shorten(finding.descricao or VERIFY, 220))
    return f"{prefix}: {impact}"


def classificacao_tecnica(finding: RuleFinding) -> str:
    code = finding.codigo
    if code.startswith(("SN-005", "SN-017", "SN-020", "SN-024", "SN-025", "SN-026", "SN-027", "SN-028")):
        return "Validacao documental"
    if code.startswith("SN-COMP") or finding.nivel == RiskLevel.ALTO:
        return "Possivel inconsistencia material"
    if finding.nivel == RiskLevel.MEDIO:
        return "Alerta tecnico"
    return "Ponto de atencao"


def normas_consolidadas(findings: list[RuleFinding], regime: str) -> list[str]:
    normas: list[str] = []
    for norma in BASE_NORMAS:
        append_unique(normas, norma)
    if "simples" in (regime or "").lower():
        append_unique(normas, "Lei Complementar nº 123/2006")
    for finding in findings:
        for norma in normalize_normas(finding.normas_aplicaveis):
            append_unique(normas, norma)
    return normas
