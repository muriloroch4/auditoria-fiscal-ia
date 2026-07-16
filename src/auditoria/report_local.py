from __future__ import annotations

from typing import Any

from .models import AuditResult
from .report_payload import build_prompt_data
from .report_consultivo_helpers import (
    _client_safe_text,
    _consultative_meaning,
    _consultative_solution,
    _documents_for_finding,
    _escape_table,
    _level_label,
    _orientacao_consultiva_de_conclusao,
    _recommendation_for_finding,
    _suggested_owner,
)

_NOVO_TEMPLATE = r"""
Parecer técnico contábil consultivo trimestral

Cliente:  {cliente}
CNPJ:     {cnpj}
Regime:   {regime_tributario}
Período:  {periodo}
Emissão:  {emissao}

## 1. Resumo executivo

{resumo_executivo}

## 2. Leitura para o cliente

{leitura_cliente}

## 3. Plano de ação consultivo

{plano_acao}

## 4. Análise técnica para a contabilidade

{achados_recomendacoes}

## 5. Conclusão técnica e próximos passos

{opiniao_tecnica}
""".strip()


def generate_local_report(
    result: AuditResult,
    *,
    cnpj: str | None = None,
) -> str:
    payload = build_prompt_data(result, cnpj=cnpj)
    identificacao = payload["identificacao_empresa"]
    resumo = payload["resumo_analise"]
    meta = payload["metadados"]

    return _NOVO_TEMPLATE.format(
        cliente=resumo["empresa"],
        cnpj=identificacao.get("cnpj", ""),
        regime_tributario=identificacao["regime_tributario"],
        periodo=identificacao["periodo_analisado"],
        emissao=str(meta["data_analise"]).split("T", 1)[0],
        resumo_executivo=_render_consultivo_resumo(payload),
        leitura_cliente=_render_consultivo_leitura_cliente(payload),
        plano_acao=_render_consultivo_plano_acao(payload),
        achados_recomendacoes=_render_consultivo_achados(payload),
        opiniao_tecnica=_render_consultivo_opiniao(payload),
    )


# ---------------------------------------------------------------------------
# Renderers for the local consultive template
# ---------------------------------------------------------------------------


def _render_consultivo_resumo(payload: dict[str, Any]) -> str:
    identificacao = payload["identificacao_empresa"]
    resumo = payload["resumo_analise"]
    counts = resumo.get("achados_por_severidade", {})
    periodo = identificacao["periodo_analisado"]
    total = resumo["total_regras_acionadas"]
    pontos = resumo.get("principais_pontos") or []

    raw_score = resumo.get("pontuacao_bruta")
    max_score = resumo.get("pontuacao_maxima_aplicavel")
    score_base = (
        f" Base bruta: {raw_score} de {max_score} ponto(s) aplicáveis."
        if raw_score is not None and max_score is not None
        else ""
    )

    primeiro = (
        f"A análise do período {periodo}, com base em {resumo['base_analise']}, resultou em risco "
        f"{resumo['risco_geral']} e pontuação total de {resumo['pontuacao_total']}/100.{score_base} "
        f"Foram verificadas {resumo['total_regras_verificadas']} regras, das quais {total} foram acionadas "
        f"({counts.get('alta', 0)} alta, {counts.get('media', 0)} média e {counts.get('baixa', 0)} baixa)."
    )

    segundo = "Principais pontos identificados: " + ("; ".join(pontos) if pontos else "[VERIFICAR: principais pontos].")
    contexto = _render_contexto_regime(payload)
    classificacao = _render_classificacao_contas_resumo(payload)
    return "\n\n".join(item for item in (primeiro, segundo, classificacao, contexto) if item)


def _render_contexto_regime(payload: dict[str, Any]) -> str:
    fundamentacao = payload.get("fundamentacao_tecnica_resumida", {})
    observacoes = fundamentacao.get("observacoes_tecnicas") or []
    if not observacoes:
        return ""
    return "Observações técnicas resumidas: " + " ".join(str(obs).rstrip(".") + "." for obs in observacoes[:4])


def _render_classificacao_contas_resumo(payload: dict[str, Any]) -> str:
    classificacao = payload.get("classificacao_contas") or {}
    total_revisao = int(classificacao.get("total_contas_revisao") or 0)
    if total_revisao <= 0:
        return ""
    total = int(classificacao.get("total_contas") or 0)
    return (
        f"Classificação do plano de contas: {total_revisao} de {total} conta(s) foram marcadas para revisão "
        "quanto ao grupo contábil atribuído pelo parser."
    )


def _render_consultivo_achados(payload: dict[str, Any]) -> str:
    resumo = payload["resumo_analise"]
    achados = payload["principais_achados"]
    abertura = (
        f"Foram identificados {resumo['total_regras_acionadas']} achado(s) a partir da aplicação "
        f"de {resumo['total_regras_verificadas']} regras fiscais."
    )

    if not achados:
        regime = payload["identificacao_empresa"]["regime_tributario"]
        return (
            f"{abertura}\n\n"
            f"Nenhuma regra foi acionada no período analisado. As métricas do balancete "
            f"estão dentro dos parâmetros configurados para o regime {regime}."
        )

    linhas = [
        abertura,
        "",
        "| Código | Achado | Nível | Evidência | Fonte | Confiança | Documentos recomendados | Impacto técnico |",
        "|--------|--------|-------|-----------|-------|-----------|--------------------------|-----------------|",
    ]
    for achado in achados:
        codigo = achado["codigo"]
        if str(codigo).startswith("SN-COMP"):
            codigo = f"**{codigo}**"
        evidencia = achado.get("evidencia") or {}
        documentos = ", ".join(evidencia.get("documentos_recomendados") or [])
        linhas.append(
            "| "
            f"{codigo} | "
            f"{_escape_table(achado['achado'])} | "
            f"{_level_label(achado['severidade'])} | "
            f"{_escape_table(achado.get('evidencia_identificada') or 'Não aplicável')} | "
            f"{_escape_table(evidencia.get('fonte_dado') or 'balancete_contabil')} | "
            f"{_level_label(evidencia.get('confianca') or 'media')} | "
            f"{_escape_table(documentos or '[VERIFICAR: documentos recomendados]')} | "
            f"{_escape_table(achado.get('impacto_tecnico') or '[VERIFICAR: impacto técnico]')} |"
        )

    normas = payload.get("fundamentacao_tecnica_resumida", {}).get("normas_aplicaveis") or []
    if normas:
        linhas.extend(["", f"Fundamentação: {'; '.join(normas)}."])

    recommendations = payload.get("recomendacoes_tecnicas") or []
    if recommendations:
        linhas.extend(
            [
                "",
                "Recomendações técnicas:",
                "",
                "| Ordem | Recomendação | Área | Prioridade |",
                "|-------|--------------|------|------------|",
            ]
        )
        for item in recommendations:
            linhas.append(
                "| "
                f"{item.get('ordem', '')} | "
                f"{_escape_table(item.get('descricao') or '[VERIFICAR: recomendação]')} | "
                f"{_escape_table(item.get('area_relacionada') or '[VERIFICAR: área]')} | "
                f"{_level_label(item.get('prioridade') or '')} |"
            )
    return "\n".join(linhas)


def _render_consultivo_leitura_cliente(payload: dict[str, Any]) -> str:
    consultivo = payload.get("consultivo") or {}
    if consultivo.get("leitura_cliente"):
        resumo = consultivo.get("resumo_orientativo")
        return "\n\n".join(item for item in (consultivo["leitura_cliente"], resumo) if item)

    resumo = payload["resumo_analise"]
    achados = payload["principais_achados"]
    risco = str(resumo.get("risco_geral") or "baixo").lower()
    prioridade = {
        "alto": "prioridade imediata",
        "medio": "prioridade de curto prazo",
        "baixo": "acompanhamento preventivo",
    }.get(risco, "acompanhamento preventivo")
    principais = achados[:3]
    if principais:
        bullets = "\n".join(
            f"- {_client_safe_text(item.get('achado') or item.get('codigo') or '[VERIFICAR: achado]')}"
            for item in principais
        )
    else:
        bullets = "- Nenhum achado foi acionado pelo motor; manter documentação e conciliações em dia."

    return (
        f"O resultado do trimestre indica **{prioridade}**. A leitura consultiva para o cliente é que "
        "os pontos abaixo devem orientar a organização documental, a regularização contábil e o acompanhamento "
        "dos próximos fechamentos.\n\n"
        "**Principais mensagens para o cliente:**\n\n"
        f"{bullets}\n\n"
        "**Como conduzir:** separar documentos de suporte, validar saldos com razão contábil e extratos, "
        "corrigir lançamentos ou baixas pendentes e registrar a providência adotada para acompanhamento."
    )


def _render_consultivo_plano_acao(payload: dict[str, Any]) -> str:
    consultivo = payload.get("consultivo") or {}
    plano = consultivo.get("plano_acao") or []
    if plano:
        linhas = []
        for index, item in enumerate(plano, start=1):
            linhas.extend(
                [
                    f"### {index}. {item.get('codigo', '[VERIFICAR: código]')} — {_client_safe_text(item.get('ponto_atencao') or '[VERIFICAR: ponto de atenção]')}",
                    "",
                    f"- **Prioridade:** {_level_label(item.get('prioridade') or 'media')}",
                    f"- **O que significa:** {item.get('o_que_significa') or '[VERIFICAR: significado]'}",
                    f"- **Como solucionar:** {item.get('como_solucionar') or '[VERIFICAR: solução]'}",
                    f"- **Documentos necessários:** {', '.join(item.get('documentos_necessarios') or []) or '[VERIFICAR: documentos necessários]'}",
                    f"- **Responsável sugerido:** {item.get('responsavel_sugerido') or '[VERIFICAR: responsável]'}",
                    f"- **Prazo sugerido:** {item.get('prazo_sugerido') or '[VERIFICAR: prazo]'}",
                    "",
                ]
            )
        return "\n".join(linhas).strip()

    achados = payload["principais_achados"]
    recomendacoes = payload.get("recomendacoes_tecnicas") or []
    if not achados:
        return (
            "Nenhuma ação corretiva prioritária foi indicada pelo motor. Recomenda-se manter conciliações, "
            "documentação fiscal e controles auxiliares atualizados para os próximos trimestres."
        )

    linhas = []
    for index, achado in enumerate(achados, start=1):
        recomendacao = _recommendation_for_finding(recomendacoes, achado, index - 1)
        linhas.extend(
            [
                f"### {index}. {achado.get('codigo', '[VERIFICAR: código]')} — {_client_safe_text(achado.get('achado') or '[VERIFICAR: achado]')}",
                "",
                f"- **Prioridade:** {_level_label(achado.get('severidade') or 'media')}",
                f"- **O que significa:** {_consultative_meaning(achado)}",
                f"- **Como solucionar:** {_consultative_solution(achado, recomendacao)}",
                f"- **Documentos necessários:** {', '.join(_documents_for_finding(achado))}",
                f"- **Responsável sugerido:** {_suggested_owner(achado)}",
                "",
            ]
        )
    return "\n".join(linhas).strip()


def _render_consultivo_opiniao(payload: dict[str, Any]) -> str:
    identificacao = payload["identificacao_empresa"]
    resumo = payload["resumo_analise"]
    conclusao = payload["conclusao_tecnica"]
    achados = payload["principais_achados"]
    periodo = identificacao["periodo_analisado"]
    regime = identificacao["regime_tributario"]
    orientacao = conclusao.get("orientacao_consultiva") or _orientacao_consultiva_de_conclusao(
        str(conclusao.get("conclusao_sugerida") or "")
    )

    abertura = (
        f"Com base na análise do balancete do período {periodo}, compreendendo "
        f"{resumo['total_regras_verificadas']} regras fiscais verificadas, apresenta-se a seguinte orientação técnica consultiva:"
    )

    codigos = ", ".join(str(achado.get("codigo")) for achado in achados) or "nenhum achado acionado"
    bloco = (
        f"Orientação consultiva: {orientacao}. "
        f"Risco geral {conclusao['risco_geral']} para o regime {regime}, considerando os achados {codigos}. "
        f"{conclusao['texto_conclusivo']}"
    )

    encerramento = (
        f"Este parecer tem caráter consultivo e abrange exclusivamente os dados do balancete informado "
        f"para o período {periodo}. Não substitui auditoria independente completa. Elaborado em conformidade "
        "com a NBC PG 100 (R1) de 2018, NBC TA 700 (R1), NBC TG 26 (R3) = CPC 26 R1 e Resolução CFC n.º 1.244/2009."
    )
    return "\n\n".join([abertura, bloco, encerramento])
