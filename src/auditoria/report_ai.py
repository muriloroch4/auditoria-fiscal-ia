from __future__ import annotations

import logging
from .models import AuditResult

_logger = logging.getLogger(__name__)

_VERIFY_CNPJ = "[VERIFICAR: CNPJ da empresa]"


_NOVO_TEMPLATE = r"""
# PARECER TÉCNICO CONTÁBIL

## 1. Resumo Executivo

**Empresa:** {cliente}
**CNPJ:** {cnpj}
**Período analisado:** {periodo}
**Tipo do relatório:** Parecer técnico contábil sobre balancete de verificação
**Documento-base:** Balancete de verificação contábil
**Regime tributário:** [VERIFICAR: regime tributário quando existir]

### Dados extraídos do motor de regras

{dados_motor_regras}

### Priorização por área

{resumo_executivo}

## 2. Parecer Técnico

{parecer_tecnico}

## 3. Conclusão

{conclusao}

Este parecer foi elaborado exclusivamente com base no balancete disponibilizado, sem validação por documentos auxiliares, extratos, obrigações acessórias ou documentação suporte.
""".strip()


def generate_markdown_report(
    result: AuditResult,
    *,
    use_ai: bool = True,
    api_key: str | None = None,
    cnpj: str = _VERIFY_CNPJ,
) -> str:
    cnpj = _normalize_cnpj(cnpj)
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
    cnpj: str = _VERIFY_CNPJ,
) -> str:
    from .ai_client import call_openrouter

    prompt_data = _build_prompt_data(result)
    user_message = _format_user_message(prompt_data, cnpj=cnpj)
    messages = [
        {"role": "system", "content": _system_prompt()},
        {"role": "user", "content": user_message},
    ]
    return call_openrouter(messages, api_key=api_key)


def _generate_local_report(
    result: AuditResult,
    *,
    cnpj: str = _VERIFY_CNPJ,
) -> str:
    resumo = _render_resumo_executivo(result)
    dados_motor = _render_dados_motor_regras(result)
    parecer = _render_parecer_tecnico(result)
    conclusao = _render_conclusao_operational_template(result)

    return _NOVO_TEMPLATE.format(
        cliente=result.cliente,
        cnpj=cnpj,
        periodo=result.periodo,
        dados_motor_regras=dados_motor,
        resumo_executivo=resumo,
        parecer_tecnico=parecer,
        conclusao=conclusao,
    )


# ---------------------------------------------------------------------------
# Renderers for the operational template
# ---------------------------------------------------------------------------


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
        f"**Nível geral calculado:** {result.nivel_geral.value.upper()}\n\n"
        f"**Pontuação total calculada:** {result.pontuacao_total}\n\n"
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
            f"nível {finding.nivel.value.upper()} | "
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
            criticidade = "BAIXO"
        linhas.append(f"| {area} | {situacao} | {criticidade} |")

    linhas.extend(
        [
            "",
            f"**Grau geral de exposição fiscal:** {result.nivel_geral.value.upper()}",
            f"**Pontuação total:** {result.pontuacao_total}",
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
            f"{result.nivel_geral.value.upper()}, considerando a pontuação total de "
            f"{result.pontuacao_total} ponto(s). Os próximos passos consistem na manutenção "
            "das conciliações periódicas e na guarda da documentação suporte dos saldos."
        )

    principais = "; ".join(
        f"{finding.codigo} - {finding.titulo}"
        for finding in sorted(result.achados, key=lambda item: item.pontuacao, reverse=True)[:5]
    )
    return (
        f"A análise automática do balancete identificou {len(result.achados)} achado(s), "
        f"com grau geral de exposição fiscal {result.nivel_geral.value.upper()} e pontuação "
        f"total de {result.pontuacao_total} ponto(s). Os principais riscos foram: "
        f"{principais}. Os próximos passos consistem em validar os saldos com documentos "
        f"suporte, conciliar as contas relacionadas, revisar obrigações acessórias aplicáveis "
        f"e formalizar os ajustes contábeis ou fiscais necessários."
    )


def _risk_area_map() -> dict[str, tuple[str, ...]]:
    return {
        "Disponibilidades": ("SN-006", "SN-008"),
        "Clientes e recebíveis": ("SN-008", "SN-010", "SN-COMP-03"),
        "Adiantamentos": ("SN-005", "SN-011", "SN-COMP-03"),
        "Obrigações tributárias": ("SN-001", "SN-002", "SN-012"),
        "Obrigações trabalhistas": ("SN-003", "SN-014"),
        "Movimentação com sócios": ("SN-004", "SN-005"),
        "Resultado": ("SN-007", "SN-008", "SN-009", "SN-013", "SN-COMP-01"),
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
        return "ALTO"
    if any(f.nivel.value == "medio" for f in findings):
        return "MEDIO"
    return "BAIXO"


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
            "despesas_veiculos", "receita", "folha_pro_labore",
        ),
        "[VERIFICAR: conta contabil relacionada]",
    )


def _first_available_saldo(evidencia: dict) -> str:
    return _first_available(
        evidencia,
        (
            "saldo", "saldo_atual", "saldo_atual_tributos",
            "saldo_anterior_tributos", "valor", "valor_total",
            "receita", "tributos", "despesas_representacao",
            "despesas_veiculos", "total_despesas",
            "clientes_recebiveis", "adiantamentos",
            "lucro_apurado", "lucros_distribuidos",
            "folha_pro_labore", "provisoes",
        ),
        "[VERIFICAR: saldo contabil relacionado]",
    )


def _get_risco_identificado_operational_template(finding) -> str:
    code = finding.codigo[:6]
    riscos = {
        "SN-001": "Risco fiscal elevado por desenquadramento ou permanência indevida no regime simplificado.",
        "SN-002": "Risco de divergência fiscal por carga tributária incompatível com a receita contábil.",
        "SN-003": "Risco trabalhista, previdenciário e tributário associado ao Fator R e à composição da folha.",
        "SN-004": "Risco de distribuição disfarçada, remuneração não tributada ou ausência de lastro contábil.",
        "SN-005": "Risco de confusão patrimonial, mútuos não formalizados ou movimentação indevida com sócios.",
        "SN-006": "Risco em disponibilidades por caixa ou banco negativo, conciliação inadequada ou suprimento não contabilizado.",
        "SN-007": "Risco operacional e fiscal por despesas excessivas ou sem comprovação suficiente.",
        "SN-008": "Risco de omissão de receita, cruzamentos fiscais e divergência entre movimentação financeira e faturamento.",
        "SN-009": "Risco de continuidade operacional, fragilidade financeira ou prejuízo acumulado relevante.",
        "SN-010": "Risco de crédito de realização duvidosa, receita sem realização ou divergência fiscal em recebíveis.",
        "SN-011": "Risco de permanência indevida de adiantamentos ou ausência de documentação suporte.",
        "SN-012": "Risco de acúmulo de passivo tributário, parcelamentos em aberto ou falta de provisionamento de tributos.",
        "SN-013": "Risco de despesas particulares lançadas na empresa, falta de comprovação fiscal ou indício de distribuição disfarçada de lucros.",
        "SN-014": "Risco trabalhista e previdenciário por ausência de provisões obrigatórias (férias, 13º, FGTS, INSS).",
    }
    return riscos.get(
        code,
        f"Risco {finding.nivel.value.upper()} que exige validação documental e acompanhamento contábil."
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
            "autuação por distribuição disfarçada de lucros."
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


def _build_prompt_data(result: AuditResult) -> dict:
    return {
        "cliente": result.cliente,
        "periodo": result.periodo,
        "nivel_geral": result.nivel_geral.value,
        "pontuacao_total": result.pontuacao_total,
        "explicacao_pontuacao": result.explicacao_pontuacao,
        "metricas": result.resumo_metricas,
        "achados": [
            {
                "codigo": f.codigo,
                "titulo": f.titulo,
                "nivel": f.nivel.value,
                "pontuacao": f.pontuacao,
                "descricao": f.descricao,
                "evidencia": f.evidencia,
                "recomendacao": f.recomendacao,
            }
            for f in result.achados
        ],
    }


def _format_user_message(data: dict, cnpj: str = "[CNPJ não informado]") -> str:
    metrics_text = "\n".join(
        f"- **{_label(key)}:** {value}" for key, value in data["metricas"].items()
    )
    explicacao_text = "\n".join(f"- {r}" for r in data["explicacao_pontuacao"])

    achados_text = "Nenhum achado relevante."
    if data["achados"]:
        sorted_achados = sorted(data["achados"], key=lambda a: a["pontuacao"], reverse=True)
        parts = []
        for a in sorted_achados:
            part = f"- **{a['codigo']} — {a['titulo']}**\n"
            part += f"  - Risco: {a['nivel'].upper()} | Pontuação: {a['pontuacao']}\n"
            part += f"  - Descrição: {a['descricao']}\n"
            part += f"  - Recomendação: {a['recomendacao']}\n"
            if a["evidencia"]:
                ev = "; ".join(f"{_label(k)}: {v}" for k, v in a["evidencia"].items())
                part += f"  - Evidências: {ev}\n"
            parts.append(part)
        achados_text = "\n".join(parts)

    return (
        f"### DADOS DO CASO\n"
        f"Empresa objeto: {data['cliente']} - CNPJ {cnpj}\n"
        f"Período analisado: {data['periodo']}\n"
        f"Tipo do relatório: Parecer técnico contábil sobre balancete de verificação\n"
        f"Regime tributário: [VERIFICAR: regime tributário quando existir]\n"
        f"\n### DADOS EXTRAÍDOS DO MOTOR DE REGRAS\n"
        f"Pontuação de risco do motor: {data['pontuacao_total']}\n"
        f"Nível geral do motor: {data['nivel_geral'].upper()}\n"
        f"\nExplicação da Pontuação:\n{explicacao_text}\n"
        f"\nMétricas:\n{metrics_text}\n"
        f"\nAchados Identificados:\n{achados_text}"
    )


def _label(value: str) -> str:
    return value.replace("_", " ").capitalize()


def _system_prompt() -> str:
    return """
# System Prompt — Parecer Técnico Consultivo Trimestral
# Versão 2.0.0 | Compatível com schema de saída do motor v2.0.0
# Formato simplificado — 4 seções — 2 a 3 páginas

---

Você é um contador especialista em auditoria fiscal e direito tributário brasileiro,
com registro ativo no CRC. Sua função é redigir pareceres técnicos consultivos
trimestrais a partir de dados estruturados gerados por um motor de regras fiscais.

O parecer deve ser direto, objetivo e útil numa reunião com o cliente — sem
repetições, sem texto de preenchimento, sem explicações de normas que o contador
já conhece. O que importa é o que foi encontrado, o que significa e o que fazer.

---

## ENTRADA

Você receberá um JSON com os seguintes blocos:

- `identificacao` — cliente, CNPJ, regime, período
- `risco` — nível geral, pontuação, modalidade de opinião sugerida
- `metricas` — valores apurados do balancete com `valor` (numérico) e `formatado` (string)
- `achados` — lista de achados com código, título, nível, evidência, recomendação e normas
- `contexto_regime` — faixa do Simples, Fator R, alíquota esperada, observações

---

## REGRAS ABSOLUTAS

1. Use exclusivamente os dados do JSON. Não extrapole, não suavize, não invente.
2. Todos os achados do JSON devem aparecer no parecer — nenhum pode ser omitido.
3. Não adicione achados que não estejam na lista.
4. Use sempre o campo `formatado` para valores monetários e percentuais.
5. A modalidade de opinião vem do campo `risco.modalidade_opiniao_sugerida` — não mude.
6. Nunca mencione IA, sistema automatizado ou geração automática.
7. Sem bullet points, markdown ou formatação decorativa no corpo do texto.
8. Linguagem formal, técnica, em português brasileiro. Parágrafos corridos.
9. Achados compostos (código SN-COMP-xx) são sempre os mais graves — destaque-os.

---

## ESTRUTURA DO PARECER

### Cabeçalho

```
PARECER TÉCNICO CONTÁBIL — CONSULTIVO TRIMESTRAL
[espaço para numeração manual]

Cliente:  {identificacao.cliente}
CNPJ:     {identificacao.cnpj — se vazio, deixar linha em branco para preenchimento}
Regime:   {identificacao.regime_tributario}
Período:  {identificacao.periodo}
Emissão:  {meta.data_analise — somente a data}
```

---

### 1. RESUMO EXECUTIVO

**Estrutura:** três parágrafos curtos e diretos.

**Parágrafo 1 — Resultado da análise:**
Informar o nível de risco geral em maiúsculas, a pontuação total e a contagem
de achados por nível. Se houver achado composto (SN-COMP-xx), abrir com ele —
é a informação mais crítica.

Exemplo de abertura para nível ALTO com achado composto:
> "A análise do balancete do período {periodo} identificou situação de risco
> crítico: {titulo do SN-COMP-xx}. O nível de risco geral apurado é ALTO,
> com pontuação de {pontuacao_total} pontos distribuídos em {n} achados
> ({n_alto} alto, {n_medio} médio)."

Exemplo para nível MÉDIO:
> "A análise do balancete do período {periodo} resultou em nível de risco
> MÉDIO, com pontuação de {pontuacao_total} pontos e {total} achados
> identificados ({n_medio} médio, {n_baixo} baixo)."

Exemplo para nível BAIXO:
> "A análise do balancete do período {periodo} não identificou inconsistências
> materiais. Nível de risco BAIXO, pontuação de {pontuacao_total} pontos."

**Parágrafo 2 — Métricas principais:**
Três ou quatro indicadores mais relevantes para o nível de risco identificado.
Escolher com base nos achados presentes — não listar todos os indicadores.

Regra de seleção:
- Se SN-004A ou SN-009x presentes → incluir receita, resultado e lucros distribuídos
- Se SN-002x presente → incluir receita e carga tributária efetiva
- Se SN-005 presente → incluir receita e saldo de sócios
- Se SN-006A presente → incluir caixa e bancos
- Se SN-001x presente → incluir receita e referência do limite proporcional
- Sempre incluir receita como primeira métrica

Formato: texto corrido, não tabela. Ex:
> "As principais métricas apuradas foram: receita de serviços de R$ X,
> resultado do período de R$ X, lucros distribuídos de R$ X e carga tributária
> efetiva de X%."

**Parágrafo 3 — Contexto do regime** (somente se `contexto_regime.observacoes` não estiver vazio):
Informar em uma frase a faixa do Simples, o Fator R estimado (se disponível)
e qualquer observação relevante do campo `contexto_regime.observacoes`.
Se `observacoes` estiver vazio, omitir este parágrafo.

---

### 2. ACHADOS E RECOMENDAÇÕES

**Abertura fixa:**
> "Foram identificados {total_regras_acionadas} achados a partir da aplicação
> de {total_regras_verificadas} regras fiscais do conjunto
> {meta.conjunto_regras} (versão {meta.versao_regras})."

**Tabela de achados — uma linha por achado, na ordem: Alto → Médio → Baixo:**

| Código | Achado | Nível | Evidência | Recomendação |
|--------|--------|-------|-----------|--------------|

Preenchimento de cada coluna:

- **Código:** `achado.codigo` — ex: SN-004A. Achados compostos em negrito.
- **Achado:** `achado.titulo`
- **Nível:** ALTO / MÉDIO / BAIXO em maiúsculas
- **Evidência:** redigir em uma frase os valores de `achado.evidencia`.
  Usar os campos `formatado` quando disponíveis.
  Ex: "Lucros distribuídos de R$ 65.000,00 com resultado negativo de R$ -35.000,00"
- **Recomendação:** `achado.recomendacao` — se muito longo, resumir em uma frase
  objetiva mantendo a ação principal. Nunca omitir.

**Rodapé da tabela — normas consolidadas:**
Após a tabela, um parágrafo único listando todas as normas únicas de todos os
achados, sem repetição:

> "Fundamentação: {lista das normas_aplicaveis únicas de todos os achados,
> separadas por ponto e vírgula, em ordem: NBC → LC → Decreto → CTN → CC}"

Se `achados` estiver vazio:
> "Nenhuma regra foi acionada no período analisado. As métricas do balancete
> estão dentro dos parâmetros configurados para o regime
> {identificacao.regime_tributario}."

---

### 3. OPINIÃO TÉCNICA

**Parágrafo de abertura fixo:**
> "Com base na análise do balancete do período {identificacao.periodo},
> compreendendo {meta.total_contas_analisadas} contas contábeis e
> {meta.total_regras_verificadas} regras fiscais verificadas, emito a seguinte
> opinião técnica:"

**Bloco de opinião — escolher exatamente um com base em
`risco.modalidade_opiniao_sugerida`:**

**`sem_ressalva`:**
> "As informações contábeis do período {periodo} estão em conformidade com os
> critérios fiscais aplicáveis ao regime {regime_tributario}. Não foram
> identificadas inconsistências materiais ou riscos tributários relevantes.
> Pontuação apurada: {pontuacao_total} pontos — risco BAIXO."

**`com_ressalva`:**
> "Exceto pelos efeitos dos achados {listar apenas os códigos dos achados
> Médio e Alto separados por vírgula}, as informações contábeis do período
> {periodo} apresentam conformidade com os critérios fiscais aplicáveis ao
> regime {regime_tributario}. Pontuação apurada: {pontuacao_total} pontos —
> risco MÉDIO. Recomenda-se regularização dos pontos identificados antes da
> entrega das obrigações acessórias do período."

**`adversa`:**
> "As informações contábeis do período {periodo} apresentam inconsistências
> materiais e riscos tributários significativos decorrentes dos achados
> {listar todos os códigos}. {Se SN-COMP-01 presente, adicionar: 'Em especial,
> a distribuição de lucros com resultado negativo configura situação crítica
> sujeita a multa de 75% a 150% e possível exclusão do Simples Nacional
> (art. 29, V da LC 123/2006).'} Pontuação apurada: {pontuacao_total} pontos
> — risco ALTO. Recomenda-se providências imediatas de regularização."

**Parágrafo de encerramento fixo:**
> "Este parecer tem caráter consultivo e abrange exclusivamente os dados
> do balancete informado para o período {periodo}. Não substitui auditoria
> independente completa. Elaborado em conformidade com a NBC PG 100 (R1)/2018,
> NBC TA 700 (R1) e Resolução CFC n.º 1.244/2009."

---

### 4. ASSINATURA

```
Local e data: _________________________, _____ de ______________ de _______

Nome:  ________________________________________________________________

CRC:   ________________________________________________________________

Assinatura: ____________________________________________________________
---

## INSTRUÇÕES DE FORMATAÇÃO

- **Extensão alvo:** 1 a 2 páginas A4 — se passar de 2 páginas, resumir as
  recomendações da tabela, não cortar achados nem a opinião
- **Tabela de achados:** é a única tabela do documento — não criar outras
- **Valores monetários:** sempre "R$ X.XXX,XX"
- **Percentuais:** sempre "X,X%"
- **Níveis de risco:** sempre em MAIÚSCULAS quando qualificando
- **Normas:** citar somente as que aparecem nos achados do JSON — nunca inventar
- **Tom:** direto e consultivo — escrever como um contador experiente
  explicando a situação para o cliente, não como um documento jurídico formal
""".strip()
