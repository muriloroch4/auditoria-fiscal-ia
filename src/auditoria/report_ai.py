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


def _level_label(value: str) -> str:
    labels = {"alto": "Alto", "medio": "Médio", "baixo": "Baixo", "alta": "Alta", "media": "Média", "baixa": "Baixa"}
    return labels.get(str(value).lower(), str(value).capitalize())


def _escape_table(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


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
