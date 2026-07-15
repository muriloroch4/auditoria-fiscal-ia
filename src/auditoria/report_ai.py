from __future__ import annotations

import json
import logging
from typing import Any

from .consultivo import consultivo_for_code
from .models import AuditResult

_logger = logging.getLogger(__name__)

_VERIFY_CNPJ = ""


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


def generate_markdown_report(
    result: AuditResult,
    *,
    use_ai: bool = True,
    api_key: str | None = None,
    cnpj: str | None = None,
) -> str:
    cnpj = _normalize_cnpj(cnpj or result.cnpj)
    if use_ai:
        try:
            return _generate_ai_report(result, api_key=api_key, cnpj=cnpj)
        except Exception:
            _logger.warning(
                "Falha ao gerar relatório via IA. Usando relatório padrão.",
                exc_info=True,
            )
    return _generate_local_report(result, cnpj=cnpj)


def _generate_ai_report(
    result: AuditResult,
    *,
    api_key: str | None = None,
    cnpj: str | None = None,
) -> str:
    from .ai_client import call_openrouter

    prompt_data = _build_prompt_data(result, cnpj=cnpj)
    user_message = _format_user_message(prompt_data)
    messages = [
        {"role": "system", "content": _system_prompt()},
        {"role": "user", "content": user_message},
    ]
    return call_openrouter(messages, api_key=api_key)


def _generate_local_report(
    result: AuditResult,
    *,
    cnpj: str | None = None,
) -> str:
    payload = _build_prompt_data(result, cnpj=cnpj)
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
# Renderers for the operational template
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


def _render_metricas_principais(payload: dict[str, Any]) -> str:
    pontos = payload.get("resumo_analise", {}).get("principais_pontos") or []
    return "Principais pontos identificados: " + ("; ".join(pontos) if pontos else "[VERIFICAR: principais pontos].")


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


def _orientacao_consultiva_de_conclusao(value: str) -> str:
    normalized = value.strip().lower().replace("_", " ")
    if normalized in {"adversa", "opiniao adversa", "opinião adversa"}:
        return "regularizar os achados relevantes antes de usar os dados para decisões externas ou fechamento anual"
    if normalized in {"com ressalva", "ressalva", "com ressalvas"}:
        return "corrigir, documentar e validar os pontos destacados antes do fechamento definitivo"
    if normalized in {"abstencao de opiniao", "abstenção de opinião"}:
        return "obter documentação complementar antes de concluir a análise"
    return "manter a documentação suporte e acompanhar os controles nos próximos trimestres"


def _recommendation_for_finding(recommendations: list[dict[str, Any]], achado: dict[str, Any], index: int) -> str:
    code = str(achado.get("codigo") or "")
    for item in recommendations:
        description = str(item.get("descricao") or "")
        if code and code in description:
            return description
    if index < len(recommendations):
        return str(recommendations[index].get("descricao") or "")
    return str(achado.get("impacto_tecnico") or "[VERIFICAR: recomendação técnica]")


def _client_safe_text(value: str) -> str:
    return (
        str(value or "")
        .replace("possível sinal de sonegação fiscal", "risco de receita não reconhecida ou tratamento fiscal pendente")
        .replace("Possível sinal de sonegação fiscal", "Risco de receita não reconhecida ou tratamento fiscal pendente")
        .replace("sonegação fiscal", "risco fiscal")
        .replace("Sonegação fiscal", "Risco fiscal")
        .replace("omissão de receita", "receita possivelmente não reconhecida")
        .replace("Omissão de receita", "Receita possivelmente não reconhecida")
        .replace("fraude", "irregularidade")
        .replace("Fraude", "Irregularidade")
    )


def _consultative_meaning(achado: dict[str, Any]) -> str:
    code = str(achado.get("codigo") or "")
    consultive = consultivo_for_code(code)
    if consultive.get("matched") and consultive.get("o_que_significa"):
        return _client_safe_text(str(consultive["o_que_significa"]))
    impact = _client_safe_text(str(achado.get("impacto_tecnico") or ""))
    if code.startswith("SN-004"):
        return "A distribuição de lucros precisa ter lastro contábil suficiente antes de ser mantida como isenta."
    if code.startswith("SN-005"):
        return "Saldos com sócios exigem contrato, conciliação financeira e validação de IOF quando houver mútuo."
    if code.startswith(("SN-006", "SN-022")):
        return "O saldo de caixa ou bancos deve ser compatível com a operação e com os comprovantes financeiros."
    if code.startswith("SN-008"):
        return "A movimentação financeira pode não estar totalmente conciliada com o faturamento reconhecido."
    if code.startswith(("SN-010", "SN-023")):
        return "Os recebíveis precisam refletir valores efetivamente pendentes, com baixas e controles auxiliares consistentes."
    if code.startswith(("SN-015", "SN-018")):
        return "Estoque, CMV e margem devem estar coerentes com compras, vendas e controles internos."
    if code.startswith("SN-025"):
        return "Serviços de terceiros relevantes precisam comprovar natureza, competência e vínculo com a atividade."
    if code.startswith("SN-026"):
        return "Adiantamentos de clientes podem ser legítimos, mas precisam comprovar se ainda estão pendentes ou se já deveriam ter sido baixados."
    return impact or "O achado indica ponto que deve ser validado antes do fechamento definitivo."


def _consultative_solution(achado: dict[str, Any], recommendation: str) -> str:
    code = str(achado.get("codigo") or "")
    consultive = consultivo_for_code(code)
    if consultive.get("matched") and consultive.get("como_solucionar"):
        return _client_safe_text(str(consultive["como_solucionar"]))
    if code.startswith("SN-004"):
        return "Reconciliar resultado, lucros acumulados, reservas e comprovantes de distribuição."
    if code.startswith("SN-005"):
        return "Conferir razão e extratos, formalizar contrato de mútuo quando aplicável e validar IOF, prazo, juros e liquidação."
    if code.startswith(("SN-006", "SN-022")):
        return "Conciliar extratos, caixa físico e lançamentos de sócios; reclassificar valores sem natureza de disponibilidade."
    if code.startswith("SN-008"):
        return "Comparar notas fiscais, extratos, faturamento e recebimentos para identificar lançamentos ausentes ou em competência incorreta."
    if code.startswith(("SN-010", "SN-023")):
        return "Validar relatório de clientes, aging list, recebimentos posteriores e baixas do período seguinte."
    if code.startswith(("SN-015", "SN-018")):
        return "Confrontar inventário, compras, vendas e memória do CMV; ajustar baixas ou reclassificações necessárias."
    if code.startswith("SN-025"):
        return "Conferir a conta 325 com notas fiscais, contratos, comprovantes bancários e retenções aplicáveis."
    if code.startswith("SN-026"):
        return "Validar contrato, pedido, nota fiscal, extrato e baixa posterior; regularizar valores já liquidados que permaneçam como adiantamento."
    return _client_safe_text(recommendation or "Validar documentos, conciliar saldos e registrar a providência adotada.")


def _documents_for_finding(achado: dict[str, Any]) -> list[str]:
    evidence = achado.get("evidencia") or {}
    docs = evidence.get("documentos_recomendados") or []
    if docs:
        return [str(item) for item in docs]
    code = str(achado.get("codigo") or "")
    consultive = consultivo_for_code(code)
    if consultive.get("matched") and consultive.get("documentos_necessarios"):
        return [str(item) for item in consultive["documentos_necessarios"]]
    if code.startswith("SN-004"):
        return ["balancete", "razão contábil", "DRE", "comprovantes de distribuição"]
    if code.startswith("SN-005"):
        return ["razão das contas de sócios", "extratos bancários", "contrato de mútuo", "comprovante de IOF quando aplicável"]
    if code.startswith("SN-025"):
        return ["razão da conta 325", "notas fiscais", "contratos", "comprovantes bancários"]
    if code.startswith("SN-026"):
        return ["contratos ou pedidos", "notas fiscais", "extratos", "razão contábil e baixas posteriores"]
    return ["balancete", "razão contábil", "documentos fiscais", "extratos e relatórios auxiliares"]


def _suggested_owner(achado: dict[str, Any]) -> str:
    code = str(achado.get("codigo") or "")
    consultive = consultivo_for_code(code)
    if consultive.get("matched") and consultive.get("responsavel_sugerido"):
        return str(consultive["responsavel_sugerido"])
    if code.startswith(("SN-003", "SN-014")):
        return "Departamento pessoal + contabilidade"
    if code.startswith(("SN-004", "SN-005")):
        return "Sócios/administradores + contabilidade"
    if code.startswith(("SN-001", "SN-002", "SN-019", "SN-020")):
        return "Fiscal + contabilidade"
    if code.startswith(("SN-015", "SN-016", "SN-018", "SN-024")):
        return "Cliente/estoque/financeiro + contabilidade"
    return "Cliente + contabilidade"


def _metric_value(metricas: dict[str, Any], key: str) -> str | None:
    value = metricas.get(key)
    if isinstance(value, dict):
        return value.get("formatado")
    if isinstance(value, str):
        return value
    return None


def _level_label(value: str) -> str:
    labels = {"alto": "Alto", "medio": "Médio", "baixo": "Baixo", "alta": "Alta", "media": "Média", "baixa": "Baixa"}
    return labels.get(str(value).lower(), str(value).capitalize())


def _finding_sort_key(achado: dict[str, Any]) -> tuple[int, str]:
    order = {"alto": 0, "medio": 1, "baixo": 2}
    return (order.get(str(achado.get("nivel", "")).lower(), 9), str(achado.get("codigo", "")))


def _format_evidence_dict(evidencia: dict[str, Any]) -> str:
    if not evidencia:
        return "Não aplicável"
    return "; ".join(f"{_label(str(key))}: {value}" for key, value in evidencia.items())


def _normas_consolidadas(achados: list[dict[str, Any]]) -> list[str]:
    normas: list[str] = []
    for achado in achados:
        for norma in achado.get("normas_aplicaveis", []):
            if norma and norma not in normas:
                normas.append(norma)
    return sorted(normas, key=_norma_sort_key)


def _norma_sort_key(norma: str) -> tuple[int, str]:
    text = norma.upper()
    if text.startswith("NBC"):
        return (0, text)
    if "LC " in text or text.startswith("LC"):
        return (1, text)
    if "DECRETO" in text:
        return (2, text)
    if "CTN" in text:
        return (3, text)
    if "CC" in text or "CÓDIGO CIVIL" in text:
        return (4, text)
    return (9, text)


def _finding_codes(achados: list[dict[str, Any]], only_medium_high: bool = False) -> str:
    selected = [
        achado["codigo"]
        for achado in sorted(achados, key=_finding_sort_key)
        if not only_medium_high or achado.get("nivel") in ("alto", "medio")
    ]
    return ", ".join(selected) if selected else "[VERIFICAR: achados]"


def _escape_table(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _render_dados_motor_regras(result: AuditResult) -> str:
    metricas = "\n".join(
        f"- **{_label(chave)}:** {valor}"
        for chave, valor in result.resumo_metricas.items()
    )
    if not metricas:
        metricas = "- [VERIFICAR: métricas calculadas pelo motor de regras]"

    explicacao = "\n".join(f"- {item}" for item in result.explicacao_pontuacao)
    if not explicacao:
        explicacao = "- [VERIFICAR: explicação da pontuação do motor de regras]"

    regras = _render_regras_acionadas(result)

    return (
        f"**Nível geral calculado:** {_level_label(result.nivel_geral.value)}\n\n"
        f"**Pontuação total calculada:** {result.pontuacao_total}/100\n\n"
        f"**Base bruta da pontuação:** {result.pontuacao_bruta} de "
        f"{result.pontuacao_maxima_aplicavel} ponto(s) aplicáveis\n\n"
        f"**Métricas calculadas:**\n{metricas}\n\n"
        f"**Explicação da pontuação:**\n{explicacao}\n\n"
        f"**Regras acionadas:**\n{regras}"
    )


def _render_regras_acionadas(result: AuditResult) -> str:
    if not result.achados:
        return "- Nenhuma regra foi acionada pelo motor de regras."

    linhas = []
    for finding in sorted(result.achados, key=lambda item: item.pontuacao, reverse=True):
        linhas.append(
            f"- **{finding.codigo}:** {finding.titulo} | "
            f"nível {_level_label(finding.nivel.value).lower()} | "
            f"{finding.pontuacao} ponto(s) | "
            f"evidências: {_format_evidencia(finding)}"
        )
    return "\n".join(linhas)


def _render_resumo_executivo(result: AuditResult) -> str:
    linhas = [
        "| Área | Situação | Criticidade |",
        "| --- | --- | --- |",
    ]

    for area, codes in _risk_area_map().items():
        area_findings = _findings_by_prefix(result, codes)
        if area_findings:
            situacao = "; ".join(f"{f.codigo} - {f.titulo}" for f in area_findings)
            criticidade = _highest_criticality(area_findings)
        else:
            situacao = "Sem achado automático relevante nos dados analisados"
            criticidade = "Baixo"
        linhas.append(f"| {area} | {situacao} | {criticidade} |")

    linhas.extend(
        [
            "",
            f"**Grau geral de exposição fiscal:** {_level_label(result.nivel_geral.value)}",
            f"**Pontuação total:** {result.pontuacao_total}/100",
        ]
    )
    return "\n".join(linhas)


def _render_parecer_tecnico(result: AuditResult) -> str:
    if not result.achados:
        return (
            "Não foram identificados achados automáticos de risco relevante com base nos "
            "dados extraídos do balancete. A avaliação considerou os grupos de "
            "disponibilidades, clientes e recebíveis, adiantamentos, obrigações tributárias, "
            "obrigações trabalhistas, movimentação com sócios, resultado e patrimônio líquido."
        )

    blocos = []
    for finding in sorted(result.achados, key=lambda item: item.pontuacao, reverse=True):
        blocos.append(_render_achado_operational_template(finding))
    return "\n\n".join(blocos)


def _render_achado_operational_template(finding) -> str:
    evidencia = finding.evidencia or {}
    conta = _first_available_conta(evidencia)
    saldo = _first_available_saldo(evidencia)
    movimentacao = _format_evidencia(finding)

    return (
        f"### {finding.codigo} - {finding.titulo}\n\n"
        f"**Conta:** {conta}\n\n"
        f"**Saldo:** {saldo}\n\n"
        f"**Movimentação:** {movimentacao}\n\n"
        f"**Achado:** {finding.descricao}\n\n"
        f"**Risco identificado:** {_get_risco_identificado_operational_template(finding)}\n\n"
        f"**Impacto potencial:** {_impacto_fiscal_potencial(finding)}\n\n"
        f"**Recomendação:** {finding.recomendacao or '[VERIFICAR: ação sugerida]'}"
    )


def _render_conclusao_operational_template(result: AuditResult) -> str:
    if not result.achados:
        return (
            "A análise automática do balancete não identificou achados relevantes nos testes "
            "de risco executados. O grau geral de exposição fiscal foi classificado como "
            f"{_level_label(result.nivel_geral.value).lower()}, considerando a pontuação total de "
            f"{result.pontuacao_total}/100. Os próximos passos consistem na manutenção "
            "das conciliações periódicas e na guarda da documentação suporte dos saldos."
        )

    principais = "; ".join(
        f"{finding.codigo} - {finding.titulo}"
        for finding in sorted(result.achados, key=lambda item: item.pontuacao, reverse=True)[:5]
    )
    return (
        f"A análise automática do balancete identificou {len(result.achados)} achado(s), "
        f"com grau geral de exposição fiscal {_level_label(result.nivel_geral.value).lower()} e pontuação "
        f"total de {result.pontuacao_total}/100. Os principais riscos foram: "
        f"{principais}. Os próximos passos consistem em validar os saldos com documentos "
        f"suporte, conciliar as contas relacionadas, revisar obrigações acessórias aplicáveis "
        f"e formalizar os ajustes contábeis ou fiscais necessários."
    )


def _risk_area_map() -> dict[str, tuple[str, ...]]:
    return {
        "Disponibilidades": ("SN-006", "SN-008", "SN-022"),
        "Clientes e recebíveis": ("SN-008", "SN-010", "SN-023", "SN-COMP-03"),
        "Estoques e CMV": ("SN-015", "SN-018", "SN-COMP-04"),
        "Fornecedores": ("SN-016",),
        "Adiantamentos": ("SN-005", "SN-011", "SN-026", "SN-COMP-03"),
        "Obrigações tributárias": ("SN-001", "SN-002", "SN-012", "SN-017", "SN-019", "SN-020", "SN-COMP-05"),
        "Obrigações trabalhistas": ("SN-003", "SN-014"),
        "Passivos financeiros": ("SN-028",),
        "Classificação contábil": ("SN-027",),
        "Movimentação com sócios": ("SN-004", "SN-005"),
        "Resultado": ("SN-007", "SN-008", "SN-009", "SN-013", "SN-021", "SN-025", "SN-COMP-01"),
        "Patrimônio líquido": ("SN-004", "SN-009", "SN-COMP-02"),
    }


def _findings_by_prefix(result: AuditResult, prefixes: tuple[str, ...]):
    return [
        finding
        for finding in result.achados
        if any(finding.codigo.startswith(prefix) for prefix in prefixes)
    ]


def _highest_criticality(findings) -> str:
    if any(f.nivel.value == "alto" for f in findings):
        return "Alto"
    if any(f.nivel.value == "medio" for f in findings):
        return "Médio"
    return "Baixo"


def _first_available(evidencia: dict, keys: tuple[str, ...], default: str) -> str:
    for key in keys:
        value = evidencia.get(key)
        if value not in (None, ""):
            return str(value)
    return default


def _first_available_conta(evidencia: dict) -> str:
    return _first_available(
        evidencia,
        (
            "conta", "conta_relacionada", "grupo", "grupo_contabil",
            "saldo_anterior_tributos", "despesas_representacao",
            "despesas_veiculos", "servicos_terceiros", "saldo_contas_socios", "receita", "folha_pro_labore",
            "adiantamentos_clientes",
        ),
        "[VERIFICAR: conta contábil relacionada]",
    )


def _first_available_saldo(evidencia: dict) -> str:
    return _first_available(
        evidencia,
        (
            "saldo", "saldo_atual", "saldo_atual_tributos",
            "saldo_anterior_tributos", "valor", "valor_total",
            "receita", "tributos", "despesas_representacao",
            "despesas_veiculos", "servicos_terceiros", "total_despesas",
            "clientes_recebiveis", "adiantamentos", "adiantamentos_clientes", "saldo_contas_socios",
            "lucro_apurado", "lucros_distribuidos",
            "folha_pro_labore", "provisoes",
        ),
        "[VERIFICAR: saldo contábil relacionado]",
    )


def _get_risco_identificado_operational_template(finding) -> str:
    code = finding.codigo[:6]
    riscos = {
        "SN-001": "Risco fiscal elevado por desenquadramento ou permanência indevida no regime simplificado.",
        "SN-002": "Risco de divergência fiscal por carga tributária incompatível com a receita contábil.",
        "SN-003": "Risco trabalhista, previdenciário e tributário associado ao Fator R e à composição da folha.",
        "SN-004": "Risco de distribuição disfarçada, remuneração não tributada ou ausência de lastro contábil.",
        "SN-005": "Risco de saldo com sócios ou mútuo sem contrato formal, conciliação financeira e validação do IOF quando aplicável.",
        "SN-006": "Risco em disponibilidades por caixa ou banco negativo, conciliação inadequada ou suprimento não contabilizado.",
        "SN-007": "Risco operacional e fiscal por despesas excessivas ou sem comprovação suficiente.",
        "SN-008": "Risco de omissão de receita, cruzamentos fiscais e divergência entre movimentação financeira e faturamento.",
        "SN-009": "Risco de continuidade operacional, fragilidade financeira ou prejuízo acumulado relevante.",
        "SN-010": "Risco de crédito de realização duvidosa, receita sem realização ou divergência fiscal em recebíveis.",
        "SN-011": "Risco de permanência indevida de adiantamentos ou ausência de documentação suporte.",
        "SN-012": "Risco de acúmulo de passivo tributário, parcelamentos em aberto ou falta de provisionamento de tributos.",
        "SN-013": "Risco de despesas particulares lançadas na empresa, falta de comprovação fiscal ou indício de distribuição disfarçada de lucros.",
        "SN-014": "Risco trabalhista e previdenciário por ausência de provisões obrigatórias (férias, 13º, FGTS, INSS).",
        "SN-025": "Risco documental por serviços de terceiros relevantes lançados diretamente em despesas sem validação suficiente.",
        "SN-026": "Risco fiscal e documental por adiantamentos de clientes no passivo quando representarem valores já liquidados sem baixa, emissão fiscal ou reconhecimento adequado.",
        "SN-027": "Risco de classificação contábil inadequada por saldo patrimonial em natureza inversa sem identificação clara de conta redutora.",
        "SN-028": "Risco de passivo financeiro com juros, encargos ou despesas financeiras não apropriados por competência.",
    }
    return riscos.get(
        code,
        f"Risco {_level_label(finding.nivel.value).lower()} que exige validação documental e acompanhamento contábil."
    )


def _impacto_fiscal_potencial(finding) -> str:
    code = finding.codigo[:6]
    impactos = {
        "SN-001": (
            "Exclusão do Simples Nacional com efeitos retroativos; "
            "cobrança de diferenças de IRPJ, CSLL, PIS e COFINS pelo regime geral; "
            "multa de ofício de 75% a 150% (art. 44 da Lei 9.430/96) acrescida de juros SELIC."
        ),
        "SN-002": (
            "Auto de infração com multa de 75% a 150% sobre os tributos não recolhidos; "
            "exigência de declarações retificadoras (PGDAS-D, DEFIS); "
            "possível representação fiscal quando a divergência for confirmada."
        ),
        "SN-003": (
            "Migração compulsória do Anexo III para o Anexo V do Simples Nacional; "
            "cobrança retroativa da diferença de alíquota; "
            "aumento da carga tributária nos períodos subsequentes."
        ),
        "SN-004": (
            "Tributação dos valores excedentes como rendimento do trabalho (IRPF tabela progressiva até 27,5%); "
            "INSS patronal de 20% sobre o excedente requalificado como pró-labore; "
            "multa de ofício de 75%; possível exclusão do Simples Nacional."
        ),
        "SN-005": (
            "Desconsideração da personalidade jurídica (art. 50 do CC c/c art. 135 do CTN); "
            "responsabilização solidária dos sócios por tributos devidos; "
            "questionamento de mútuos sem contrato e cobrança de IOF quando a operação caracterizar crédito."
        ),
        "SN-006": (
            "Arbitramento da base de cálculo (art. 148 do CTN) no caso de caixa negativo; "
            "autuação por omissão de receita com multa qualificada de 150%; "
            "exigência de conciliação bancária e retificação da escrituração."
        ),
        "SN-007": (
            "Glosa de despesas não comprovadas com majoração do lucro tributável; "
            "autuação com multa de 75% sobre o imposto devido; "
            "exigência de documentação comprobatória."
        ),
        "SN-008": (
            "Autuação por omissão de receita com multa qualificada de 150%; "
            "exclusão do Simples Nacional; "
            "representação fiscal para fins penais (Lei 8.137/90); "
            "cobrança de tributos acrescidos de juros SELIC."
        ),
        "SN-009": (
            "Questionamento sobre a continuidade da empresa (NBC TG 26 — going concern); "
            "fiscalização quanto à efetividade das operações e regularidade da escrituração; "
            "possível exigência de recomposição patrimonial pelos sócios."
        ),
        "SN-010": (
            "Possível divergência entre contas a receber, notas fiscais emitidas e recebimentos; "
            "necessidade de conciliação com relatórios auxiliares e validação de perdas esperadas."
        ),
        "SN-011": (
            "Possível glosa ou reclassificação de valores sem documentação suporte; "
            "necessidade de baixa, comprovação contratual ou reclassificação contábil."
        ),
        "SN-026": (
            "Possível autuação por omissão de receita caso os adiantamentos de clientes já tenham sido liquidados "
            "sem emissão fiscal, baixa contábil ou reconhecimento da receita; necessidade de conciliação com "
            "contratos, pedidos, notas fiscais, extratos e comprovantes de recebimento."
        ),
        "SN-027": (
            "Possível distorção de ativo, passivo ou patrimônio por classificação contábil inadequada; "
            "necessidade de validar se o saldo representa conta redutora legítima, baixa pendente, erro de lançamento "
            "ou reclassificação patrimonial."
        ),
        "SN-028": (
            "Possível subavaliação de despesas financeiras e passivos por falta de apropriação de juros, IOF, "
            "variação monetária ou encargos por competência; necessidade de confrontar contrato, cronograma e extratos."
        ),
        "SN-012": (
            "Inscrição em dívida ativa e protesto do título; "
            "restrição ao crédito e à obtenção de certidão negativa; "
            "exclusão do Simples Nacional por dívidas tributárias; "
            "execução fiscal com penhora de bens e bloqueio de contas."
        ),
        "SN-013": (
            "Glosa de despesas não comprovadas com majoração do lucro tributável; "
            "autuação com multa de 75% sobre o imposto devido; "
            "possível caracterização de distribuição disfarçada de lucros (art. 527 do RIR/2018); "
            "exigência de documentação comprobatória e comprovação de necessidade operacional."
        ),
        "SN-014": (
            "Autuação por falta de constituição de provisões trabalhistas obrigatórias; "
            "multa de 75% a 150% sobre os encargos não contabilizados; "
            "divergência com as obrigações do eSocial e DCTFWeb; "
            "passivo trabalhista oculto com impacto no balanço patrimonial."
        ),
    }
    return impactos.get(
        code,
        "Risco de autuação fiscal com multa de 75% a 150%, juros SELIC e demais consectários legais."
    )


def _format_evidencia(finding) -> str:
    if not finding.evidencia:
        return "Não aplicável"
    return "; ".join(f"{_label(k)}: {v}" for k, v in finding.evidencia.items())


def _normalize_cnpj(cnpj: str | None) -> str:
    value = (cnpj or "").strip()
    return value or _VERIFY_CNPJ


def _build_prompt_data(result: AuditResult, cnpj: str | None = None) -> dict[str, Any]:
    from .serializers import audit_result_to_dict

    payload = audit_result_to_dict(result)
    payload["identificacao_empresa"]["cnpj"] = _normalize_cnpj(cnpj or result.cnpj)
    return payload


def _format_user_message(data: dict[str, Any]) -> str:
    return (
        "Redija o relatório consultivo trimestral seguindo exatamente o system prompt. "
        "Use exclusivamente o JSON abaixo como entrada.\n\n"
        "```json\n"
        f"{json.dumps(data, ensure_ascii=False, indent=2)}\n"
        "```"
    )


def _label(value: str) -> str:
    return value.replace("_", " ").capitalize()


def _system_prompt() -> str:
    return """
# System Prompt — Relatório consultivo trimestral
# Compatível com o schema resumido v3.3.0 do motor de regras

Você é um contador consultivo, especialista em auditoria fiscal, contabilidade
societária e direito tributário brasileiro, com registro ativo no CRC. Sua função é
redigir um relatório/parecer técnico consultivo trimestral a partir exclusivamente
do JSON recebido.

O documento deve servir para dois públicos ao mesmo tempo:

- cliente/contratante: entender os principais pontos de atenção, riscos práticos,
  documentos necessários e como resolver;
- equipe contábil: validar evidências, fundamentos, saldos, lançamentos e
  providências técnicas antes do fechamento definitivo.

## Entrada

O JSON terá estes blocos:

- `identificacao_empresa`
- `resumo_analise`
- `classificacao_contas`
- `principais_achados`
- `fundamentacao_tecnica_resumida`
- `conclusao_tecnica`
- `recomendacoes_tecnicas`
- `consultivo`
- `metadados`

## Regras obrigatórias

1. Use exclusivamente os dados do JSON.
2. Não invente valores, documentos, CNPJ, CRC, achados, normas ou conclusões.
3. Se algum dado estiver ausente, preserve `[VERIFICAR: dado necessário]`.
4. Não use linguagem de auditoria independente definitiva.
5. Informe que a análise foi feita com base exclusivamente no JSON e depende de validação documental.
6. Todos os itens de `principais_achados` devem aparecer no parecer.
7. Todas as recomendações de `recomendacoes_tecnicas` devem aparecer no parecer.
8. Mantenha o texto objetivo, consultivo e orientado a ação, em Markdown.
9. Não inclua número de parecer, assinatura, carimbo, rubrica ou fechamento formal.
10. Se `classificacao_contas` indicar contas para revisão, mencione isso de forma objetiva na análise.
11. Produza documento compacto, equivalente a 4 a 6 páginas em PDF para um trimestre comum.
12. Revise ortografia, concordância, letras maiúsculas/minúsculas e espaços antes de pontuação.
13. Evite tabelas largas; use tabelas somente quando as colunas forem curtas.
14. Evite termos acusatórios ao cliente. Quando houver risco sensível, use linguagem como
    "risco fiscal/documental", "receita possivelmente não reconhecida" ou "tratamento fiscal pendente".
15. Não suavize a gravidade técnica: informe risco alto, materialidade e prioridade, mas de forma profissional e orientada à solução.
16. Use `conclusao_tecnica.orientacao_consultiva` como mensagem principal da conclusão, quando disponível.
17. Não copie literalmente `conclusao_sugerida` quando ela vier como "adversa", "com_ressalva" ou termo equivalente; traduza para linguagem consultiva, como "risco alto com regularização prioritária" ou "necessidade de validação documental antes de uso externo".
18. Quando houver campos `[VERIFICAR: ...]`, agrupe-os em um bloco chamado **Validações pendentes** dentro do achado correspondente, em vez de espalhar os placeholders no texto corrido.
19. Em **Validações pendentes**, use lista com um item por pendência. Corrija a pontuação interna do placeholder antes de exibir, por exemplo `valor , prazo` deve virar `valor, prazo`.
20. Antes de finalizar, corrija espaços indevidos antes de pontuação, como `valor , prazo`, `texto .` ou `item ;`.
21. Ao citar `resumo_analise.pontuacao_total`, sempre escreva como escala `X/100`. Use `pontuacao_bruta` e `pontuacao_maxima_aplicavel` apenas como explicação técnica do cálculo, quando isso ajudar.

## Diretrizes de layout para PDF

1. Gere Markdown limpo, compacto e amigável para impressão em PDF.
2. Use apenas um título H1 no início. Depois use H2 numerados e H3 apenas para achados.
3. Evite parágrafos longos: cada parágrafo deve ter no máximo 4 linhas quando impresso.
4. Evite listas muito extensas. Quando houver muitos documentos, agrupe por área ou limite aos documentos prioritários.
5. Na primeira página, use um bloco compacto de identificação, seguido de um resumo executivo curto.
6. Não transforme todos os dados em texto corrido. Prefira blocos com rótulos em negrito e frases curtas.
7. Use tabelas somente quando forem realmente compactas. Cada célula deve ter texto curto, sem frases longas.
8. No plano de ação, use formato de "cartão textual" por achado: prioridade, significado, ação, documentos, responsável e validações pendentes.
9. Não repita a mesma lista completa de documentos em várias seções.
10. A conclusão deve caber em uma página comum, com próximos passos numerados e objetivos.
11. Para um trimestre comum, produza um documento equivalente a 5 a 7 páginas em PDF.
12. Não use linhas horizontais em excesso, caixas ASCII, emojis, ícones ou decoração textual.

## Estrutura esperada

Use esta estrutura:

1. Identificação da empresa
2. Resumo da análise
3. Leitura para o cliente
4. Plano de ação consultivo
5. Análise técnica para a contabilidade
6. Fundamentação técnica resumida
7. Conclusão técnica e próximos passos

Na "Leitura para o cliente", explique em linguagem simples:
- o que foi encontrado;
- por que importa;
- quais riscos práticos existem;
- o que o cliente deve separar ou confirmar.

Use `consultivo.leitura_cliente` e `consultivo.resumo_orientativo` como fonte prioritária para esta seção.

No "Plano de ação consultivo", use formato compacto por achado:
- `### [Código] — [Ponto de atenção]`
- **Prioridade:** alta, média ou baixa. **Responsável:** cliente, contabilidade, fiscal, departamento pessoal, sócios/administradores ou combinação.
- **O que significa:** explicação simples e profissional em uma ou duas frases.
- **Como solucionar:** ação objetiva para corrigir ou validar.
- **Documentos necessários:** documentos citados no JSON ou `[VERIFICAR: dado necessário]`. Se forem muitos, agrupe por tipo.
- **Validações pendentes:** somente quando houver campos `[VERIFICAR: ...]` no JSON, sempre em bullets e sem espaços indevidos antes de pontuação.

Use `consultivo.plano_acao` como fonte prioritária desta seção. Se algum item estiver ausente, complemente apenas com dados existentes em `principais_achados` e `recomendacoes_tecnicas`.

Na "Análise técnica para a contabilidade", use tabela compacta com:
Código, Severidade, Evidência resumida, Procedimento sugerido, Pontuação.
Nas células da tabela, use frases curtas. Após a tabela, detalhe apenas achados de severidade alta ou validações documentais relevantes em parágrafos curtos.

Na conclusão, não use "opinião adversa" nem "conclusão sugerida: adversa" como mensagem principal ao cliente. Traduza a modalidade técnica para orientação prática, por exemplo:
"regularização prioritária antes do fechamento anual" ou "validar documentos antes de decisão externa".
A conclusão deve trazer próximos passos objetivos, preferencialmente em lista numerada de até 8 itens.
""".strip()
