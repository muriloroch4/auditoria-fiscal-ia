from __future__ import annotations

import datetime
from typing import Any

from .config_loader import load_config
from .models import AuditResult, RiskLevel, RuleFinding
from .risk import suggest_opinion_type

SCHEMA_VERSION = "3.0.0"
VERIFY = "[VERIFICAR: dado necessário]"

_NORMA_LABELS = {
    "LC 123/2006": "Lei Complementar nº 123/2006",
    "art. 3° LC 123/2006": "Lei Complementar nº 123/2006, art. 3º",
    "art. 14° LC 123/2006": "Lei Complementar nº 123/2006, art. 14",
    "art. 18° LC 123/2006": "Lei Complementar nº 123/2006, art. 18",
    "art. 20 LC 123/2006": "Lei Complementar nº 123/2006, art. 20",
    "art. 47° LC 123/2006": "Lei Complementar nº 123/2006, art. 47",
    "Anexo I da LC 123/2006": "Lei Complementar nº 123/2006, Anexo I",
    "Anexo III da LC 123/2006": "Lei Complementar nº 123/2006, Anexo III",
    "Anexos I e III/V da LC 123/2006": "Lei Complementar nº 123/2006, Anexos I e III/V",
    "LC 155/2016": "Lei Complementar nº 155/2016",
    "CPC 16 R1": "NBC TG 16 (R2) = CPC 16 R1",
    "NBC TG 1000": "NBC TG 1000 (R1)",
    "ITG 2000": "ITG 2000 (R1)",
}

_BASE_NORMAS = (
    "Resolução CFC n.º 1.244/2009",
    "NBC PG 100 (R1) de 2018",
    "NBC PG 200",
    "NBC TA 700 (R1)",
    "NBC TG 26 (R3) = CPC 26 R1",
    "NBC TG 00 (R2)",
)


def audit_result_to_dict(result: AuditResult) -> dict[str, Any]:
    cfg = load_config()
    findings = _sorted_findings(result.achados)
    severity_counts = _severity_counts(findings)
    normas = _normas_consolidadas(findings, result.regime_tributario)
    opinion = suggest_opinion_type(result.nivel_geral, findings)

    return {
        "identificacao_empresa": {
            "cnpj": _required(result.cnpj),
            "regime_tributario": _required(result.regime_tributario),
            "periodo_analisado": _required(result.periodo),
        },
        "resumo_analise": {
            "empresa": _required(result.cliente),
            "base_analise": "JSON de auditoria trimestral",
            "total_regras_verificadas": result.total_regras_verificadas,
            "total_regras_acionadas": len(findings),
            "risco_geral": result.nivel_geral.value,
            "pontuacao_total": result.pontuacao_total,
            "achados_por_severidade": severity_counts,
            "principais_pontos": _principais_pontos(result, findings),
        },
        "principais_achados": [_finding_to_summary_dict(finding) for finding in findings],
        "fundamentacao_tecnica_resumida": {
            "normas_aplicaveis": normas,
            "texto_resumido": _fundamentacao_resumida(result, normas),
            "observacoes_tecnicas": _observacoes_tecnicas(result),
        },
        "conclusao_tecnica": {
            "risco_geral": result.nivel_geral.value,
            "conclusao_sugerida": _opinion_label(opinion),
            "ressalva_base_json": True,
            "necessita_validacao_documental": True,
            "texto_conclusivo": _texto_conclusivo(result, opinion, findings),
        },
        "recomendacoes_tecnicas": _recomendacoes_tecnicas(findings),
        "metadados": {
            "data_analise": datetime.datetime.now().isoformat(timespec="seconds"),
            "versao_schema": SCHEMA_VERSION,
            "versao_regras": cfg.get("version", "1.0.0"),
            "conjunto_regras": result.conjunto_regras,
        },
    }


def _finding_to_summary_dict(finding: RuleFinding) -> dict[str, Any]:
    return {
        "codigo": finding.codigo or VERIFY,
        "severidade": _severity_label(finding.nivel),
        "achado": _shorten(finding.titulo or finding.descricao or VERIFY, 180),
        "evidencia_identificada": _format_evidence(finding.evidencia),
        "impacto_tecnico": _impacto_tecnico(finding),
        "pontuacao": finding.pontuacao,
        "norma_fundamento": _normalize_normas(finding.normas_aplicaveis),
    }


def _recomendacoes_tecnicas(findings: list[RuleFinding]) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []
    for index, finding in enumerate(findings, start=1):
        recommendations.append(
            {
                "ordem": index,
                "descricao": _shorten(finding.recomendacao or VERIFY, 260),
                "area_relacionada": _area_relacionada(finding.codigo),
                "prioridade": _severity_label(finding.nivel),
            }
        )
    return recommendations


def _principais_pontos(result: AuditResult, findings: list[RuleFinding]) -> list[str]:
    if not findings:
        return [
            "Nenhuma regra de risco foi acionada no período analisado.",
            f"Pontuação total apurada: {result.pontuacao_total} ponto(s).",
        ]

    points = [
        f"{finding.codigo}: {_shorten(finding.titulo, 110)} ({_severity_text(finding.nivel)}, {finding.pontuacao} ponto(s))."
        for finding in findings[:5]
    ]
    if len(findings) > 5:
        points.append(f"Há mais {len(findings) - 5} achado(s) técnico(s) no período.")
    return points


def _fundamentacao_resumida(result: AuditResult, normas: list[str]) -> str:
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


def _observacoes_tecnicas(result: AuditResult) -> list[str]:
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
            observations.append(_shorten(str(item), 260))

    observations.append(
        "A escrituração e os saldos devem ser confrontados com documentos hábeis para confirmar representação fidedigna."
    )
    return observations


def _texto_conclusivo(result: AuditResult, opinion: str, findings: list[RuleFinding]) -> str:
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
            "Com base exclusivamente no JSON de auditoria trimestral, os achados indicam pontos que exigem ressalva "
            "técnica e saneamento antes do fechamento definitivo do período. A conclusão depende da validação "
            "documental dos saldos, documentos fiscais e registros contábeis."
        )
    return (
        "Com base exclusivamente no JSON de auditoria trimestral, a análise não indica inconsistência material "
        "suficiente para modificar a conclusão sugerida, sem dispensar validação documental."
    )


def _impacto_tecnico(finding: RuleFinding) -> str:
    code = finding.codigo[:6]
    prefix = _classificacao_tecnica(finding)
    impacts = {
        "SN-001": "Risco de extrapolação de limite, sublimite ou desenquadramento do Simples Nacional.",
        "SN-002": "Possível subapuração tributária ou divergência entre receita e tributos reconhecidos.",
        "SN-003": "Risco de enquadramento incorreto do anexo e inconsistência no Fator R.",
        "SN-004": "Risco societário e fiscal por distribuição sem lastro contábil suficiente.",
        "SN-005": "Indício de confusão patrimonial ou movimentação com sócios sem formalização adequada.",
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
        "SN-COM": "Risco composto por combinação de achados, exigindo análise prioritária integrada.",
    }
    impact = impacts.get(code, _shorten(finding.descricao or VERIFY, 220))
    return f"{prefix}: {impact}"


def _classificacao_tecnica(finding: RuleFinding) -> str:
    code = finding.codigo
    if code.startswith(("SN-017", "SN-020", "SN-024")):
        return "Validacao documental"
    if code.startswith("SN-COMP") or finding.nivel == RiskLevel.ALTO:
        return "Possivel inconsistencia material"
    if finding.nivel == RiskLevel.MEDIO:
        return "Alerta tecnico"
    return "Ponto de atencao"


def _area_relacionada(code: str) -> str:
    if code.startswith(("SN-001", "SN-002", "SN-008", "SN-012", "SN-017", "SN-019", "SN-020", "SN-024")):
        return "fiscal"
    if code.startswith(("SN-003", "SN-014")):
        return "trabalhista"
    if code.startswith(("SN-004", "SN-005")):
        return "societária"
    if code.startswith(("SN-006", "SN-010", "SN-011", "SN-016", "SN-022", "SN-023")):
        return "financeira"
    if code.startswith(("SN-007", "SN-009", "SN-013", "SN-015", "SN-018", "SN-021")):
        return "contábil"
    return "documental"


def _normas_consolidadas(findings: list[RuleFinding], regime: str) -> list[str]:
    normas: list[str] = []
    for norma in _BASE_NORMAS:
        _append_unique(normas, norma)
    if "simples" in (regime or "").lower():
        _append_unique(normas, "Lei Complementar nº 123/2006")
    for finding in findings:
        for norma in _normalize_normas(finding.normas_aplicaveis):
            _append_unique(normas, norma)
    return normas


def _normalize_normas(normas: tuple[str, ...]) -> list[str]:
    normalized: list[str] = []
    for norma in normas:
        label = _NORMA_LABELS.get(norma, norma)
        if label:
            _append_unique(normalized, label)
    return normalized


def _append_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)


def _format_evidence(evidence: dict[str, str]) -> str | None:
    if not evidence:
        return None
    text = "; ".join(f"{_label(key)}: {value}" for key, value in evidence.items())
    return _shorten(text, 320)


def _severity_counts(findings: list[RuleFinding]) -> dict[str, int]:
    return {
        "alta": sum(1 for finding in findings if finding.nivel == RiskLevel.ALTO),
        "media": sum(1 for finding in findings if finding.nivel == RiskLevel.MEDIO),
        "baixa": sum(1 for finding in findings if finding.nivel == RiskLevel.BAIXO),
    }


def _severity_label(level: RiskLevel) -> str:
    labels = {
        RiskLevel.ALTO: "alta",
        RiskLevel.MEDIO: "media",
        RiskLevel.BAIXO: "baixa",
    }
    return labels.get(level, "baixa")


def _severity_text(level: RiskLevel) -> str:
    labels = {
        RiskLevel.ALTO: "alta",
        RiskLevel.MEDIO: "média",
        RiskLevel.BAIXO: "baixa",
    }
    return labels.get(level, "baixa")


def _opinion_label(opinion: str) -> str:
    labels = {
        "sem_ressalva": "sem ressalva",
        "com_ressalva": "com ressalva",
        "adversa": "adversa",
        "abstencao_opiniao": "abstenção de opinião",
    }
    return labels.get(opinion, opinion.replace("_", " "))


def _sorted_findings(findings: list[RuleFinding]) -> list[RuleFinding]:
    order = {RiskLevel.ALTO: 0, RiskLevel.MEDIO: 1, RiskLevel.BAIXO: 2}
    return sorted(findings, key=lambda finding: (order.get(finding.nivel, 9), -finding.pontuacao, finding.codigo))


def _required(value: Any) -> str:
    text = str(value or "").strip()
    return text or VERIFY


def _shorten(value: str, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _label(value: str) -> str:
    labels = {
        "lucro_apurado": "Lucro apurado",
        "origem_lucro": "Origem do lucro",
        "lucro_disponivel_identificado": "Lucro disponível identificado",
        "lucros_distribuidos": "Lucros distribuídos",
        "saldo_contas_socios": "Saldo de contas de sócios",
        "folha_pro_labore": "Folha e pró-labore",
        "percentual_folha": "Percentual da folha",
        "provisoes": "Provisões",
        "tributos_registrados": "Tributos registrados",
        "saldo_anterior_tributos": "Saldo anterior de tributos",
        "saldo_atual_tributos": "Saldo atual de tributos",
        "receita_trimestre": "Receita do trimestre",
        "receita_anualizada_estimativa": "Receita anualizada estimada",
        "receita_rbt12": "RBT12",
        "limite_anual_simples": "Limite anual do Simples Nacional",
        "percentual_limite_anual": "Percentual do limite anual",
        "base_calculo_limite": "Base de calculo do limite",
        "fator_r_trimestral_estimado": "Fator R trimestral estimado",
        "caixa_bancos": "Caixa e bancos",
        "clientes_recebiveis": "Clientes e recebíveis",
        "saldo_final_clientes_recebiveis": "Saldo final de clientes e recebíveis",
        "movimentacao_clientes_trimestre": "Movimentação de clientes no trimestre",
        "percentual_sobre_receita_trimestral": "Percentual sobre a receita trimestral",
        "limite_percentual_receita": "Limite percentual sobre a receita",
        "referencia_aplicada": "Referência aplicada",
        "estoques": "Estoques",
        "fornecedores": "Fornecedores",
        "cmv_custos": "CMV/custos",
        "creditos_fiscais": "Créditos fiscais",
        "percentual_cmv_receita": "Percentual do CMV sobre a receita",
        "percentual_sobre_receita": "Percentual sobre a receita",
        "sublimite_anual": "Sublimite anual",
        "receita_total": "Receita total",
        "receita_comercio_identificada": "Receita de comércio identificada",
        "receita_servicos_identificada": "Receita de serviços identificada",
        "receita_nao_segregada_estimativa": "Receita não segregada estimada",
        "margem_lucro": "Margem de lucro",
        "referencia_presuncao": "Referência de presunção",
        "caixa_fisico": "Caixa físico",
        "limite_caixa": "Limite de caixa",
        "limite_alto_caixa": "Limite alto de caixa",
        "receita_minima": "Receita mínima",
        "tipo_achado": "Tipo do achado",
        "limitacao_dados": "Limitacao dos dados",
    }
    return labels.get(value, value.replace("_", " ").capitalize())


def _infer_conjunto(regime: str) -> str:
    mapa = {
        "simples nacional": "simples_servicos",
        "lucro presumido": "lucro_presumido",
        "lucro real": "lucro_real",
    }
    return mapa.get((regime or "").lower(), "simples_servicos")
