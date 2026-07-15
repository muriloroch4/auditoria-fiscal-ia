from __future__ import annotations

from typing import Any

from .annual_consultivo import (
    annual_documents_for_finding,
    annual_meaning,
    annual_orientation,
    annual_owner,
)
from .utils import format_brl


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
            "## 2. Leitura consultiva para o cliente\n\n" + _render_annual_client_guidance(payload),
            "## 3. Plano de ação anual\n\n" + _render_annual_action_plan(payload),
            "## 4. Comparativo trimestral\n\n" + _render_quarter_table(payload),
            "## 5. Achados anuais e recorrências\n\n" + _render_annual_findings(findings),
            "## 6. Indicadores consolidados\n\n" + _render_annual_metrics(metricas, evolution),
            "## 7. Conclusão técnica anual e próximos passos\n\n" + _render_annual_opinion(payload),
        ]
    )


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


def _render_annual_client_guidance(payload: dict[str, Any]) -> str:
    consultivo = payload.get("consultivo") or {}
    if consultivo.get("leitura_cliente"):
        steps = consultivo.get("proximos_passos") or []
        if steps:
            return consultivo["leitura_cliente"] + "\n\n**Próximos passos:**\n\n" + "\n".join(f"- {step}" for step in steps)
        return consultivo["leitura_cliente"]

    risco = payload["risco_anual"]
    evolution = payload["resumo_evolucao"]
    findings = payload["achados_anuais"]
    level = str(risco.get("nivel_geral") or "baixo").lower()
    priority = {
        "alto": "regularização prioritária antes de decisões externas, distribuição de lucros ou fechamento final",
        "medio": "correção e documentação dos pontos recorrentes no início do próximo exercício",
        "baixo": "manutenção dos controles e acompanhamento trimestral preventivo",
    }.get(level, "acompanhamento preventivo")
    recurrent = evolution.get("achados_recorrentes") or []
    recurrent_text = ", ".join(f"{item['codigo']} ({item['trimestres']} trimestres)" for item in recurrent[:6])
    if not recurrent_text:
        recurrent_text = "sem recorrência relevante informada pelo motor"
    main_findings = "; ".join(f"{item['codigo']} - {item['titulo']}" for item in findings[:4])
    if not main_findings:
        main_findings = "nenhum achado anual adicional identificado"

    return (
        f"A leitura anual indica {priority}. A tendência de risco foi classificada como "
        f"{evolution.get('tendencia_risco', 'insuficiente')}, com recorrências em {recurrent_text}. "
        f"Os principais pontos para explicar ao cliente são: {main_findings}. "
        "A recomendação consultiva é transformar esses pontos em plano de ação documentado, com responsáveis, "
        "prazo de regularização e conferência já no primeiro trimestre do próximo exercício."
    )


def _render_annual_action_plan(payload: dict[str, Any]) -> str:
    consultivo = payload.get("consultivo") or {}
    plano = consultivo.get("plano_acao_anual") or []
    if plano:
        lines = []
        for index, item in enumerate(plano, start=1):
            lines.extend(
                [
                    f"### {index}. {item['codigo']} — {item['ponto_atencao']}",
                    "",
                    f"- **Prioridade:** {_risk_label(item['prioridade'])}",
                    f"- **O que significa:** {item['o_que_significa']}",
                    f"- **Como solucionar:** {item['como_solucionar']}",
                    f"- **Documentos necessários:** {', '.join(item['documentos_necessarios'])}",
                    f"- **Responsável sugerido:** {item['responsavel_sugerido']}",
                    f"- **Prazo sugerido:** {item['prazo_sugerido']}",
                    "",
                ]
            )
        return "\n".join(lines).strip()

    findings = payload["achados_anuais"]
    evolution = payload["resumo_evolucao"]
    if not findings:
        return (
            "Nenhuma ação anual corretiva adicional foi indicada pela consolidação. Manter conciliações trimestrais, "
            "guarda documental e acompanhamento do limite do Simples Nacional no próximo exercício."
        )

    lines = []
    for index, finding in enumerate(findings, start=1):
        docs = annual_documents_for_finding(finding)
        lines.extend(
            [
                f"### {index}. {finding['codigo']} — {finding['titulo']}",
                "",
                f"- **Prioridade:** {_risk_label(finding['nivel'])}",
                f"- **O que significa:** {annual_meaning(finding, evolution)}",
                f"- **Como solucionar:** {finding['recomendacao']}",
                f"- **Documentos necessários:** {', '.join(docs)}",
                f"- **Responsável sugerido:** {annual_owner(finding)}",
                "",
            ]
        )
    return "\n".join(lines).strip()


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

    lines = []
    for finding in findings:
        structured = finding["evidencia"]
        extracted = structured.get("campos_extraidos") or {}
        evidence = "; ".join(f"{key}: {value}" for key, value in extracted.items()) or "Não aplicável"
        documents = ", ".join(structured.get("documentos_recomendados") or [])
        lines.extend(
            [
                f"### {finding['codigo']} — {finding['titulo']}",
                "",
                f"- **Nível:** {_risk_label(finding['nivel'])}",
                f"- **Evidência:** {evidence}",
                f"- **Fonte:** {structured.get('fonte_dado', '') or '[VERIFICAR: fonte]'}",
                f"- **Confiança:** {_risk_label(structured.get('confianca', ''))}",
                f"- **Documentos recomendados:** {documents or '[VERIFICAR: documentos recomendados]'}",
                f"- **Recomendação técnica:** {finding['recomendacao']}",
                "",
            ]
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
        f"Saldo final em contas de socios: {metricas['saldo_contas_socios_final']['formatado']}. "
        f"CMV/custos anual: {metricas['cmv_custos_total']['formatado']} "
        f"({indicators['cmv_sobre_receita_anual']}). "
        f"Estoques finais: {metricas['estoques_final']['formatado']}. "
        f"Fornecedores finais: {metricas['fornecedores_final']['formatado']}. "
        f"Créditos fiscais finais: {metricas['creditos_fiscais_final']['formatado']}. "
        f"RBT12 consolidado: {metricas['rbt12_receita']['formatado']} "
        f"({metricas['contexto_rbt12']['base_calculo']}). "
        f"Adiantamentos de clientes finais: {metricas['adiantamentos_clientes_final']['formatado']}. "
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
        f"a orientação técnica anual é {annual_orientation(risco['modalidade_opiniao_sugerida'])}. "
        f"Os principais achados anuais considerados foram: {codes}. A conclusão anual não substitui "
        "auditoria independente completa e deve ser lida em conjunto com os pareceres trimestrais que "
        "serviram de base para esta consolidação. Para o próximo exercício, recomenda-se manter fechamento "
        "trimestral, documentação suporte por achado e acompanhamento das providências até sua baixa."
    )


def _risk_label(value: str) -> str:
    labels = {
        "alto": "Alto",
        "medio": "M?dio",
        "media": "M?dia",
        "baixo": "Baixo",
        "baixa": "Baixa",
    }
    return labels.get(str(value).lower(), str(value).capitalize())
