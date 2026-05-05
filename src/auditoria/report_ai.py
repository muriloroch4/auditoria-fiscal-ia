from __future__ import annotations

import logging

from .models import AuditResult
from .utils import format_brl

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
    }


_SYSTEM_PROMPT = (
    "### PERSONA\n"
    "Atue como um Auditor Fiscal Independente e Consultor Contábil Sênior, especialista em Simples Nacional e "
    "conformidade tributária brasileira. Seu objetivo é gerar um Parecer Técnico Consultivo baseado em achados de "
    "auditoria eletrônica.\n\n"
    "### CONTEXTO DAS REGRAS (Dicionário de Riscos)\n"
    "Use as regras abaixo para fundamentar tecnicamente seus argumentos:\n"
    "- SN-001: Limite do Simples Nacional. Risco de desenquadramento e aumento de carga tributária.\n"
    "- SN-002: Carga tributária < 5,5%. Risco de erro em NCM ou omissão de guias.\n"
    "- SN-003: Folha/Pró-labore < 8% da receita. Risco de irregularidade no Fator R ou passivo trabalhista.\n"
    "- SN-004: Distribuição de lucro > Lucro apurado. Risco de tributação de IRPF (27,5%) sobre o excesso.\n"
    "- SN-005: Contas de sócios > 20% da receita. Risco de confusão patrimonial.\n"
    "- SN-006: Saldo de Caixa < 0. ERRO GRAVE: Presunção legal de omissão de receita (Art. 281 RIR/2018).\n"
    "- SN-007: Despesas > 70% da receita. Risco de glosa de despesas por falta de necessidade operacional.\n"
    "- SN-008: Receita=0 com Movimentação > 10k. ALERTA MÁXIMO: Cruzamento e-Financeira vs PGDAS.\n\n"
    "### TAREFA\n"
    "Com base nos dados fornecidos, escreva um parecer técnico estruturado em:\n"
    "1. INTRODUÇÃO: Resumo da saúde fiscal da empresa no período.\n"
    "2. ANÁLISE DETALHADA: Para cada achado, explique o que o dado indica (análise contábil) e qual o perigo real "
    "perante a Receita Federal (análise fiscal).\n"
    "3. IMPACTO FINANCEIRO: Estime consequências como multas, desenquadramento ou fiscalização.\n"
    "4. RECOMENDAÇÕES DE REGULARIZAÇÃO: Liste passos práticos (ex: conciliação, emissão de nota, contrato de mútuo).\n\n"
    "### REQUISITOS DE ESTILO\n"
    "- Linguagem profissional, mas direta ao ponto.\n"
    "- Use negrito para destacar termos de alerta e valores.\n"
    "- O tom deve ser de parceiro estratégico que deseja proteger o cliente de multas.\n"
    "- Não invente dados ou achados que não estejam nas métricas fornecidas."
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

    explicacao_text = "\n".join(f"- {r}" for r in data["explicacao_pontuacao"])

    achados_text = "Nenhum achado relevante."
    if data["achados"]:
        sorted_achados = sorted(
            data["achados"], key=lambda a: a["pontuacao"], reverse=True
        )
        parts = []
        for a in sorted_achados:
            part = f"- **{a['codigo']} — {a['titulo']}**\n"
            part += f"  - Risco: {a['nivel'].upper()} | Pontuação: {a['pontuacao']}\n"
            part += f"  - Descrição: {a['descricao']}\n"
            part += f"  - Recomendação: {a['recomendacao']}\n"
            if a["evidencia"]:
                ev = "; ".join(
                    f"{_label(k)}: {v}" for k, v in a["evidencia"].items()
                )
                part += f"  - Evidências: {ev}\n"
            parts.append(part)
        achados_text = "\n".join(parts)

    return (
        f"### DADOS DO CLIENTE E ACHADOS\n"
        f"Cliente: {data['cliente']}\n"
        f"Período: {data['periodo']}\n"
        f"Pontuação de Risco: {data['pontuacao_total']}\n"
        f"Nível Geral: {data['nivel_geral'].upper()}\n"
        f"\nExplicação da Pontuação:\n{explicacao_text}\n"
        f"\nMétricas:\n{metrics_text}\n"
        f"\nAchados Identificados:\n{achados_text}"
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
