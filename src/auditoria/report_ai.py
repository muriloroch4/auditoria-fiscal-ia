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
    "Você é um assistente especializado em auditoria fiscal para empresas "
    "de serviços no Simples Nacional.\n\n"
    "Regras de formatação OBRIGATÓRIAS:\n"
    "1. Use EXATAMENTE a estrutura abaixo:\n"
    "   - Título H1: 'Relatório Trimestral de Risco Fiscal'\n"
    "   - Tabela com Cliente, Período, Data de geração\n"
    "   - Separador '---'\n"
    "   - H2 'Sumário Executivo' com tabela de indicadores e parágrafo de resumo\n"
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
    "2. Não invente dados ou achados que não estejam nas métricas fornecidas.\n"
    "3. Para cada achado, use tabelas Markdown para Risco e Pontuação.\n"
    "4. Use negrito para rótulos e texto normal para valores.\n"
    "5. Sempre inclua as recomendações na observação final."
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
