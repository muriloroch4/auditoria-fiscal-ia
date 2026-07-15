from __future__ import annotations

from typing import Any

from .consultivo import consultivo_for_code
from .evidence import structured_finding_evidence
from .models import AuditResult, RuleFinding
from .serializer_common import (
    VERIFY,
    area_relacionada,
    client_safe_text,
    orientacao_por_opiniao,
    severity_label,
    shorten,
)


def consultivo_trimestral(
    result: AuditResult,
    findings: list[RuleFinding],
    severity_counts: dict[str, int],
    opinion: str,
) -> dict[str, Any]:
    return {
        "resumo_orientativo": consultivo_resumo_orientativo(result, findings, severity_counts, opinion),
        "leitura_cliente": consultivo_leitura_cliente(findings),
        "plano_acao": [consultivo_item(finding) for finding in findings],
    }


def consultivo_resumo_orientativo(
    result: AuditResult,
    findings: list[RuleFinding],
    severity_counts: dict[str, int],
    opinion: str,
) -> str:
    if not findings:
        return (
            "A análise não acionou regras de risco no período. Recomenda-se manter conciliações, documentação fiscal "
            "e controles auxiliares organizados para conferência futura."
        )

    prioridade = orientacao_por_opiniao(opinion)
    return (
        f"O trimestre apresenta risco {result.nivel_geral.value}, com pontuação {result.pontuacao_total}/100 "
        f"({result.pontuacao_bruta} de {result.pontuacao_maxima_aplicavel} ponto(s) bruto(s) aplicáveis) "
        f"e {len(findings)} achado(s) acionado(s), "
        f"sendo {severity_counts.get('alta', 0)} de prioridade alta, {severity_counts.get('media', 0)} de prioridade média "
        f"e {severity_counts.get('baixa', 0)} de prioridade baixa. Orientação consultiva: {prioridade}."
    )


def consultivo_leitura_cliente(findings: list[RuleFinding]) -> str:
    if not findings:
        return (
            "Não foram identificados pontos automáticos de atenção no JSON analisado. A empresa deve manter a guarda "
            "dos documentos do período e continuar o acompanhamento trimestral preventivo."
        )

    principais = "; ".join(
        f"{finding.codigo} - {client_safe_text(shorten(finding.titulo, 90))}"
        for finding in findings[:3]
    )
    return (
        "Foram identificados pontos que exigem validação documental antes do fechamento definitivo. "
        f"Principais mensagens para o cliente: {principais}. A orientação é separar documentos, validar saldos "
        "com a contabilidade e registrar as providências adotadas."
    )


def consultivo_item(finding: RuleFinding) -> dict[str, Any]:
    consultive = consultivo_for_code(finding.codigo, severity=finding.nivel.value)
    evidence = structured_finding_evidence(finding)
    documents = evidence.get("documentos_recomendados") or consultive.get("documentos_necessarios") or []
    meaning = (
        str(consultive.get("o_que_significa") or "")
        if consultive.get("matched")
        else shorten(finding.descricao or "O achado indica ponto que deve ser validado antes do fechamento definitivo.", 260)
    )
    solution = (
        str(consultive.get("como_solucionar") or "")
        if consultive.get("matched")
        else shorten(finding.recomendacao or VERIFY, 320)
    )
    return {
        "codigo": finding.codigo or VERIFY,
        "prioridade": severity_label(finding.nivel),
        "area_relacionada": area_relacionada(finding.codigo),
        "ponto_atencao": client_safe_text(shorten(finding.titulo or finding.descricao or VERIFY, 180)),
        "o_que_significa": client_safe_text(meaning),
        "como_solucionar": client_safe_text(solution),
        "documentos_necessarios": [str(item) for item in documents],
        "responsavel_sugerido": str(consultive.get("responsavel_sugerido") or ""),
        "prazo_sugerido": str(consultive.get("prazo_sugerido") or ""),
    }
