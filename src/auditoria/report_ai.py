from __future__ import annotations

import logging

from .models import AuditResult

_logger = logging.getLogger(__name__)


_REPORT_TEMPLATE = """\
# Relatório Trimestral de Risco Fiscal

**Cliente:** {cliente}
**Período:** {periodo}
**Data de geração:** {data_geracao}

---

## Sumário Executivo

| Indicador | Valor |
| --- | --- |
| Nível de risco | {nivel_badge} |
| Pontuação total | {pontuacao} |
| Achados identificados | {total_achados} |

{resumo_executivo}

---

## Composição da Pontuação

{explicacao_pontuacao}

---

## Métricas Analisadas

{metricas}

---

## Achados Detalhados

{achados}

---

## Observações Finais

{observacao}
""".strip()


_ACHADO_TEMPLATE = """\
### {codigo} — {titulo}

| Campo | Detalhe |
| --- | --- |
| Risco | {nivel_badge} |
| Pontuação | {pontuacao} |

**Descrição:** {descricao}

**Recomendação:** {recomendacao}

{evidencia}
""".strip()


def build_report_prompt(result: AuditResult) -> dict:
    return {
        "tarefa": "Gerar relatório trimestral de pré-auditoria fiscal para empresa do Simples Nacional, setor de serviços.",
        "cliente": result.cliente,
        "periodo": result.periodo,
        "nivel_geral": result.nivel_geral.value,
        "pontuacao_total": result.pontuacao_total,
        "explicacao_pontuacao": result.explicacao_pontuacao,
        "metricas": result.resumo_metricas,
        "achados": [
            {
                "codigo": finding.codigo,
                "titulo": finding.titulo,
                "nivel": finding.nivel.value,
                "pontuacao": finding.pontuacao,
                "descricao": finding.descricao,
                "evidencia": finding.evidencia,
                "recomendacao": finding.recomendacao,
            }
            for finding in result.achados
        ],
        "orientacao": _SYSTEM_PROMPT,
    }


_SYSTEM_PROMPT = (
    "Você é um Auditor Fiscal IA. Sua função é analisar achados de auditoria e gerar pareceres técnicos.\n\n"
    "CONHECIMENTO TÉCNICO OBRIGATÓRIO — Regras de Auditoria:\n\n"
    "SN-001: Limite do Simples Nacional\n"
    "Análise Técnica: Monitora a proximidade do teto de faturamento (R$ 4,8 milhões/ano).\n"
    "Risco Fiscal: O estouro do limite obriga a empresa a migrar para o Lucro Presumido ou Real no mês seguinte (se > 20% do excesso) ou no ano seguinte.\n"
    "Consequência: Aumento imediato da carga tributária e necessidade de readequação de todo o planejamento tributário.\n\n"
    "SN-002: Carga Tributária Incompatível\n"
    "Análise Técnica: Avalia se o percentual de impostos pagos está condizente com a receita declarada.\n"
    "Risco Fiscal: Alíquotas muito baixas (< 3%) sugerem erro na classificação de NCM ou falta de apuração de impostos devidos.\n"
    "Consequência: Autuação por falta de recolhimento e multas por declarações inexatas.\n\n"
    "SN-003: Fragilidade na Folha/Pró-labore\n"
    "Análise Técnica: Verifica se a estrutura de pessoal é compatível com o porte da operação.\n"
    "Risco Fiscal: Folha < 8% da receita pode indicar Fator R sendo usado de forma irregular para pagar menos imposto no Simples, ou existência de funcionários informais.\n"
    "Consequência: Desenquadramento de anexo tributário e passivos trabalhistas ocultos.\n\n"
    "SN-004: Distribuição de Lucro Excessiva\n"
    "Análise Técnica: Compara o lucro distribuído aos sócios com o lucro contábil apurado.\n"
    "Risco Fiscal: Distribuir mais do que a empresa lucrou (sem reservas) transforma esse valor em rendimento tributável para o sócio.\n"
    "Consequência: Incidência de IRPF (até 27,5%) sobre o valor excedente e multa por distribuição disfarçada de lucros.\n\n"
    "SN-005: Confusão Patrimonial (Sócios)\n"
    "Análise Técnica: Mede o volume de movimentações entre as contas da empresa e as contas pessoais dos sócios.\n"
    "Risco Fiscal: Movimentações acima de 20% da receita sugerem confusão patrimonial.\n"
    "Consequência: Perda da proteção da responsabilidade limitada e desconsideração da personalidade jurídica.\n\n"
    "SN-006: Inconsistência de Caixa e Bancos\n"
    "Análise Técnica: Identifica saldos negativos (crédito no caixa) ou saldos excessivos sem aplicação.\n"
    "Risco Fiscal: Saldos negativos são erros críticos de escrituração contábil.\n"
    "Consequência: Presunção legal de omissão de receita (Art. 281 do RIR/2018). O Fisco entende que entrou dinheiro sem nota para cobrir essas contas.\n\n"
    "SN-007: Despesas Operacionais Elevadas\n"
    "Análise Técnica: Analisa se a empresa gasta mais de 70% do que ganha em despesas administrativas.\n"
    "Risco Fiscal: Despesas muito altas com receita baixa podem ser usadas para reduzir artificialmente o lucro e evitar impostos.\n"
    "Consequência: Glosa de despesas pela Receita Federal e recálculo do imposto sobre o lucro real.\n\n"
    "SN-008: Omissão de Receita (Movimentação Ativa)\n"
    "Análise Técnica: Compara o faturamento oficial com o que circulou nas contas bancárias.\n"
    "Risco Fiscal: A empresa movimentou mas declarou zero de receita.\n"
    "Consequência: Maior risco de malha fina. A e-Financeira informa esse valor ao Fisco, que cruzará com o faturamento declarado. A multa pode chegar a 150% do valor do imposto devido.\n\n"
    "INSTRUÇÕES DE SAÍDA — Formatação OBRIGATÓRIA:\n"
    "1. Use EXATAMENTE a estrutura abaixo:\n"
    "   - Título H1: 'Relatório Trimestral de Risco Fiscal'\n"
    "   - Tabela com Cliente, Período, Data de geração\n"
    "   - Separador '---'\n"
    "   - H2 'Sumário Executivo' com tabela de indicadores e parágrafo de resumo técnico como Auditor Fiscal IA\n"
    "   - Separador '---'\n"
    "   - H2 'Composição da Pontuação' com lista explicativa\n"
    "   - Separador '---'\n"
    "   - H2 'Métricas Analisadas' com lista formatada\n"
    "   - Separador '---'\n"
    "   - H2 'Achados Detalhados' com H3 para cada achado contendo tabela de risco/pontuação, "
    "descrição, recomendação e evidências se houver\n"
    "   - Separador '---'\n"
    "   - H2 'Observações Finais' contendo:\n"
    "     * Linha inicial: '> **Recomendações:**'\n"
    "     * Lista das recomendações de cada achado (formato: '> - CÓDIGO — Título: recomendação')\n"
    "     * Linha vazia com '> '\n"
    "     * Parágrafo final com '> ' prefix: 'Este relatório constitui uma pré-auditoria baseada exclusivamente "
    "nas métricas e achados fornecidos. Ele não substitui uma análise detalhada realizada por "
    "um auditor fiscal qualificado e necessita de revisão humana antes de qualquer tomada de "
    "decisão ou ação corretiva.'\n"
    "2. Ao analisar cada achado, contextualize com as consequências fiscais e legais descritas acima.\n"
    "3. Não invente dados ou achados que não estejam nas métricas fornecidas.\n"
    "4. Para cada achado, use tabelas Markdown para Risco e Pontuação.\n"
    "5. Use negrito para rótulos e texto normal para valores.\n"
    "6. Sempre inclua as recomendações na observação final.\n"
    "7. Mantenha tom técnico e formal, como um parecer de auditoria profissional."
)


def generate_markdown_report(
    result: AuditResult,
    *,
    use_ai: bool = True,
    api_key: str | None = None,
) -> str:
    if use_ai:
        try:
            return _generate_ai_report(result, api_key=api_key)
        except Exception:
            _logger.warning(
                "Falha ao gerar relatório via IA. Usando relatório padrão.",
                exc_info=True,
            )
    return _generate_local_report(result)


def _generate_ai_report(result: AuditResult, *, api_key: str | None = None) -> str:
    from .ai_client import call_openrouter

    prompt_data = build_report_prompt(result)
    user_message = _format_prompt_message(prompt_data)

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]
    return call_openrouter(messages, api_key=api_key)


def _format_prompt_message(data: dict) -> str:
    metrics_text = "\n".join(
        f"- **{_label(key)}:** {value}" for key, value in data["metricas"].items()
    )

    achados_text = "Nenhum achado relevante."
    if data["achados"]:
        sorted_achados = sorted(
            data["achados"], key=lambda a: a["pontuacao"], reverse=True
        )
        parts = []
        for a in sorted_achados:
            part = f"### {a['codigo']} — {a['titulo']}\n"
            part += f"- **Risco:** {a['nivel'].upper()}\n"
            part += f"- **Pontuação:** {a['pontuacao']}\n"
            part += f"- **Descrição:** {a['descricao']}\n"
            part += f"- **Recomendação:** {a['recomendacao']}\n"
            if a["evidencia"]:
                ev = "; ".join(
                    f"{_label(k)}: {v}" for k, v in a["evidencia"].items()
                )
                part += f"- **Evidências:** {ev}\n"
            parts.append(part)
        achados_text = "\n".join(parts)

    explicacao_text = "\n".join(f"- {r}" for r in data["explicacao_pontuacao"])

    return (
        f"Cliente: {data['cliente']}\n"
        f"Período: {data['periodo']}\n"
        f"Nível de risco: {data['nivel_geral'].upper()}\n"
        f"Pontuação: {data['pontuacao_total']}\n"
        f"\nExplicação:\n{explicacao_text}\n"
        f"\nMétricas:\n{metrics_text}\n"
        f"\nAchados:\n{achados_text}\n"
        f"\n{data['orientacao']}"
    )


def _generate_local_report(result: AuditResult) -> str:
    from datetime import datetime

    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    achados_md = _render_achados(result)
    metricas_md = _render_metricas(result)
    explicacao_md = _render_explicacao(result)
    resumo_md = _executive_summary(result)
    recomendacoes_md = _render_recomendacoes(result)

    return _REPORT_TEMPLATE.format(
        cliente=result.cliente,
        periodo=result.periodo,
        data_geracao=now,
        nivel_badge=_risk_badge(result.nivel_geral.value),
        pontuacao=result.pontuacao_total,
        total_achados=len(result.achados),
        resumo_executivo=resumo_md,
        explicacao_pontuacao=explicacao_md,
        metricas=metricas_md,
        achados=achados_md,
        observacao=recomendacoes_md,
    )


def _render_recomendacoes(result: AuditResult) -> str:
    lines = []
    lines.append("> **Recomendações:**")
    if result.achados:
        for f in sorted(result.achados, key=lambda x: x.pontuacao, reverse=True):
            lines.append(f"> - **{f.codigo} — {f.titulo}:** {f.recomendacao}")
    lines.append(">")
    lines.append(
        "> Este relatório constitui uma pré-auditoria baseada exclusivamente nas "
        "métricas e achados fornecidos. Ele não substitui uma análise detalhada "
        "realizada por um auditor fiscal qualificado e necessita de revisão humana "
        "antes de qualquer tomada de decisão ou ação corretiva."
    )
    return "\n".join(lines)


def _render_achados(result: AuditResult) -> str:
    if not result.achados:
        return "Nenhum achado relevante foi identificado pelas regras configuradas."

    parts = []
    for f in sorted(result.achados, key=lambda x: x.pontuacao, reverse=True):
        evidencia_md = ""
        if f.evidencia:
            evidencia_text = "; ".join(
                f"{_label(k)}: {v}" for k, v in f.evidencia.items()
            )
            evidencia_md = f"**Evidências:** {evidencia_text}"

        parts.append(
            _ACHADO_TEMPLATE.format(
                codigo=f.codigo,
                titulo=f.titulo,
                nivel_badge=_risk_badge(f.nivel.value),
                pontuacao=f.pontuacao,
                descricao=f.descricao,
                recomendacao=f.recomendacao,
                evidencia=evidencia_md,
            )
        )
    return "\n\n".join(parts)


def _render_metricas(result: AuditResult) -> str:
    lines = []
    for name, value in result.resumo_metricas.items():
        lines.append(f"- **{_label(name)}:** {value}")
    return "\n".join(lines)


def _render_explicacao(result: AuditResult) -> str:
    lines = []
    for reason in result.explicacao_pontuacao:
        lines.append(f"- {reason}")
    return "\n".join(lines)


def _risk_badge(level: str) -> str:
    badges = {
        "alto": "ALTO",
        "medio": "MÉDIO",
        "baixo": "BAIXO",
    }
    return badges.get(level, level.upper())


def _executive_summary(result: AuditResult) -> str:
    if not result.achados:
        return (
            "As regras configuradas não identificaram indícios relevantes de "
            "risco fiscal no trimestre analisado."
        )

    high = sum(1 for f in result.achados if f.nivel.value == "alto")
    medium = sum(1 for f in result.achados if f.nivel.value == "medio")
    low = sum(1 for f in result.achados if f.nivel.value == "baixo")

    return (
        f"Foram identificados {len(result.achados)} achados: "
        f"{high} de risco alto, {medium} de risco médio e {low} de risco baixo. "
        "Os pontos abaixo indicam itens que merecem conferência documental "
        "e validação técnica."
    )


def _label(value: str) -> str:
    return value.replace("_", " ").capitalize()
