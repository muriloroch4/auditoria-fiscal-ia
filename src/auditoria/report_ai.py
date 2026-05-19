from __future__ import annotations

import logging
from .models import AuditResult

_logger = logging.getLogger(__name__)

_VERIFY_CNPJ = "[VERIFICAR: CNPJ da empresa]"


_NOVO_TEMPLATE = r"""
# PARECER TECNICO CONTABIL

## 1. Resumo Executivo

**Empresa:** {cliente}
**CNPJ:** {cnpj}
**Periodo analisado:** {periodo}
**Tipo do relatorio:** Parecer tecnico contabil sobre balancete de verificacao
**Documento-base:** Balancete de verificacao contabil
**Regime tributario:** [VERIFICAR: regime tributario quando existir]

### Dados extraidos do motor de regras

{dados_motor_regras}

### Priorizacao por area

{resumo_executivo}

## 2. Parecer Tecnico

{parecer_tecnico}

## 3. Conclusao

{conclusao}

Este parecer foi elaborado exclusivamente com base no balancete disponibilizado, sem validacao por documentos auxiliares, extratos, obrigacoes acessorias ou documentacao suporte.
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
                "Falha ao gerar relatorio via IA. Usando relatorio padrao.",
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
        metricas = "- [VERIFICAR: metricas calculadas pelo motor de regras]"

    explicacao = "\n".join(f"- {item}" for item in result.explicacao_pontuacao)
    if not explicacao:
        explicacao = "- [VERIFICAR: explicacao da pontuacao do motor de regras]"

    regras = _render_regras_acionadas(result)

    return (
        f"**Nivel geral calculado:** {result.nivel_geral.value.upper()}\n\n"
        f"**Pontuacao total calculada:** {result.pontuacao_total}\n\n"
        f"**Metricas calculadas:**\n{metricas}\n\n"
        f"**Explicacao da pontuacao:**\n{explicacao}\n\n"
        f"**Regras acionadas:**\n{regras}"
    )


def _render_regras_acionadas(result: AuditResult) -> str:
    if not result.achados:
        return "- Nenhuma regra foi acionada pelo motor de regras."

    linhas = []
    for finding in sorted(result.achados, key=lambda item: item.pontuacao, reverse=True):
        linhas.append(
            f"- **{finding.codigo}:** {finding.titulo} | "
            f"nivel {finding.nivel.value.upper()} | "
            f"{finding.pontuacao} ponto(s) | "
            f"evidencias: {_format_evidencia(finding)}"
        )
    return "\n".join(linhas)


def _render_resumo_executivo(result: AuditResult) -> str:
    linhas = [
        "| Area | Situacao | Criticidade |",
        "| --- | --- | --- |",
    ]

    for area, codes in _risk_area_map().items():
        area_findings = _findings_by_prefix(result, codes)
        if area_findings:
            situacao = "; ".join(f"{f.codigo} - {f.titulo}" for f in area_findings)
            criticidade = _highest_criticality(area_findings)
        else:
            situacao = "Sem achado automatico relevante nos dados analisados"
            criticidade = "BAIXO"
        linhas.append(f"| {area} | {situacao} | {criticidade} |")

    linhas.extend(
        [
            "",
            f"**Grau geral de exposicao fiscal:** {result.nivel_geral.value.upper()}",
            f"**Pontuacao total:** {result.pontuacao_total}",
        ]
    )
    return "\n".join(linhas)


def _render_parecer_tecnico(result: AuditResult) -> str:
    if not result.achados:
        return (
            "Nao foram identificados achados automaticos de risco relevante com base nos "
            "dados extraidos do balancete. A avaliacao considerou os grupos de "
            "disponibilidades, clientes e recebiveis, adiantamentos, obrigacoes tributarias, "
            "obrigacoes trabalhistas, movimentacao com socios, resultado e patrimonio liquido."
        )

    blocos = []
    for finding in sorted(result.achados, key=lambda item: item.pontuacao, reverse=True):
        blocos.append(_render_achado_operational_template(finding))
    return "\n\n".join(blocos)


def _render_achado_operational_template(finding) -> str:
    evidencia = finding.evidencia or {}
    conta = _first_available(
        evidencia,
        ("conta", "conta_relacionada", "grupo", "grupo_contabil"),
        "[VERIFICAR: conta contabil relacionada]",
    )
    saldo = _first_available(
        evidencia,
        ("saldo", "saldo_atual", "valor", "valor_total", "receita", "tributos"),
        "[VERIFICAR: saldo contabil relacionado]",
    )
    movimentacao = _format_evidencia(finding)

    return (
        f"### {finding.codigo} - {finding.titulo}\n\n"
        f"**Conta:** {conta}\n\n"
        f"**Saldo:** {saldo}\n\n"
        f"**Movimentacao:** {movimentacao}\n\n"
        f"**Achado:** {finding.descricao}\n\n"
        f"**Risco identificado:** {_get_risco_identificado_operational_template(finding)}\n\n"
        f"**Impacto potencial:** {_impacto_fiscal_potencial(finding)}\n\n"
        f"**Recomendacao:** {finding.recomendacao or '[VERIFICAR: acao sugerida]'}"
    )


def _render_conclusao_operational_template(result: AuditResult) -> str:
    if not result.achados:
        return (
            "A analise automatica do balancete nao identificou achados relevantes nos testes "
            "de risco executados. O grau geral de exposicao fiscal foi classificado como "
            f"{result.nivel_geral.value.upper()}, considerando a pontuacao total de "
            f"{result.pontuacao_total} ponto(s). Os proximos passos consistem na manutencao "
            "das conciliacoes periodicas e na guarda da documentacao suporte dos saldos."
        )

    principais = "; ".join(
        f"{finding.codigo} - {finding.titulo}"
        for finding in sorted(result.achados, key=lambda item: item.pontuacao, reverse=True)[:5]
    )
    return (
        f"A analise automatica do balancete identificou {len(result.achados)} achado(s), "
        f"com grau geral de exposicao fiscal {result.nivel_geral.value.upper()} e pontuacao "
        f"total de {result.pontuacao_total} ponto(s). Os principais riscos foram: "
        f"{principais}. Os proximos passos consistem em validar os saldos com documentos "
        f"suporte, conciliar as contas relacionadas, revisar obrigacoes acessorias aplicaveis "
        f"e formalizar os ajustes contabeis ou fiscais necessarios."
    )


def _risk_area_map() -> dict[str, tuple[str, ...]]:
    return {
        "Disponibilidades": ("SN-006", "SN-008"),
        "Clientes e recebiveis": ("SN-008", "SN-010"),
        "Adiantamentos": ("SN-005", "SN-011"),
        "Obrigacoes tributarias": ("SN-001", "SN-002"),
        "Obrigacoes trabalhistas": ("SN-003",),
        "Movimentacao com socios": ("SN-004", "SN-005"),
        "Resultado": ("SN-007", "SN-008", "SN-009"),
        "Patrimonio liquido": ("SN-004", "SN-009"),
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


def _get_risco_identificado_operational_template(finding) -> str:
    code = finding.codigo[:6]
    riscos = {
        "SN-001": "Risco fiscal elevado por desenquadramento ou permanencia indevida no regime simplificado.",
        "SN-002": "Risco de divergencia fiscal por carga tributaria incompatvel com a receita contabil.",
        "SN-003": "Risco trabalhista, previdenciario e tributario associado ao Fator R e a composicao da folha.",
        "SN-004": "Risco de distribuicao disfarçada, remuneracao nao tributada ou ausencia de lastro contabil.",
        "SN-005": "Risco de confusao patrimonial, mutuos nao formalizados ou movimentacao indevida com socios.",
        "SN-006": "Risco em disponibilidades por caixa ou banco negativo, conciliacao inadequada ou suprimento nao contabilizado.",
        "SN-007": "Risco operacional e fiscal por despesas excessivas ou sem comprovacao suficiente.",
        "SN-008": "Risco de omissao de receita, cruzamentos fiscais e divergencia entre movimentacao financeira e faturamento.",
        "SN-009": "Risco de continuidade operacional, fragilidade financeira ou prejuizo acumulado relevante.",
        "SN-010": "Risco de credito de realizacao duvidosa, receita sem realizacao ou divergencia fiscal em recebiveis.",
        "SN-011": "Risco de permanencia indevida de adiantamentos ou ausencia de documentacao suporte.",
    }
    return riscos.get(
        code,
        f"Risco {finding.nivel.value.upper()} que exige validacao documental e acompanhamento contabil."
    )


def _impacto_fiscal_potencial(finding) -> str:
    code = finding.codigo[:6]
    impactos = {
        "SN-001": (
            "Exclusao do Simples Nacional com efeitos retroativos; "
            "cobranca de diferencas de IRPJ, CSLL, PIS e COFINS pelo regime geral; "
            "multa de oficio de 75% a 150% (art. 44 da Lei 9.430/96) acrescida de juros SELIC."
        ),
        "SN-002": (
            "Auto de infracao com multa de 75% a 150% sobre os tributos nao recolhidos; "
            "exigencia de declaracoes retificadoras (PGDAS-D, DEFIS); "
            "possivel representacao fiscal quando a divergencia for confirmada."
        ),
        "SN-003": (
            "Migracao compulsoria do Anexo III para o Anexo V do Simples Nacional; "
            "cobranca retroativa da diferenca de aliquota; "
            "aumento da carga tributaria nos periodos subsequentes."
        ),
        "SN-004": (
            "Tributacao dos valores excedentes como rendimento do trabalho (IRPF tabela progressiva ate 27,5%); "
            "INSS patronal de 20% sobre o excedente requalificado como pro-labore; "
            "multa de oficio de 75%; possivel exclusao do Simples Nacional."
        ),
        "SN-005": (
            "Desconsideracao da personalidade juridica (art. 50 do CC c/c art. 135 do CTN); "
            "responsabilizacao solidaria dos socios por tributos devidos; "
            "autuacao por distribuicao disfarçada de lucros."
        ),
        "SN-006": (
            "Arbitramento da base de calculo (art. 148 do CTN) no caso de caixa negativo; "
            "autuacao por omissao de receita com multa qualificada de 150%; "
            "exigencia de conciliacao bancaria e retificacao da escrituracao."
        ),
        "SN-007": (
            "Glosa de despesas nao comprovadas com majoracao do lucro tributavel; "
            "autuacao com multa de 75% sobre o imposto devido; "
            "exigencia de documentacao comprobatoria."
        ),
        "SN-008": (
            "Autuacao por omissao de receita com multa qualificada de 150%; "
            "exclusao do Simples Nacional; "
            "representacao fiscal para fins penais (Lei 8.137/90); "
            "cobranca de tributos acrescidos de juros SELIC."
        ),
        "SN-009": (
            "Questionamento sobre a continuidade da empresa (NBC TG 26 - going concern); "
            "fiscalizacao quanto a efetividade das operacoes e regularidade da escrituracao; "
            "possivel exigencia de recomposicao patrimonial pelos socios."
        ),
        "SN-010": (
            "Possivel divergencia entre contas a receber, notas fiscais emitidas e recebimentos; "
            "necessidade de conciliacao com relatorios auxiliares e validacao de perdas esperadas."
        ),
        "SN-011": (
            "Possivel glosa ou reclassificacao de valores sem documentacao suporte; "
            "necessidade de baixa, comprovacao contratual ou reclassificacao contabil."
        ),
    }
    return impactos.get(
        code,
        "Risco de autuacao fiscal com multa de 75% a 150%, juros SELIC e demais consectarios legais."
    )


def _format_evidencia(finding) -> str:
    if not finding.evidencia:
        return "Nao aplicavel"
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


def _format_user_message(data: dict, cnpj: str = "[CNPJ nao informado]") -> str:
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
            part += f"  - Risco: {a['nivel'].upper()} | Pontuacao: {a['pontuacao']}\n"
            part += f"  - Descricao: {a['descricao']}\n"
            part += f"  - Recomendacao: {a['recomendacao']}\n"
            if a["evidencia"]:
                ev = "; ".join(f"{_label(k)}: {v}" for k, v in a["evidencia"].items())
                part += f"  - Evidencias: {ev}\n"
            parts.append(part)
        achados_text = "\n".join(parts)

    return (
        f"### DADOS DO CASO\n"
        f"Empresa objeto: {data['cliente']} - CNPJ {cnpj}\n"
        f"Periodo analisado: {data['periodo']}\n"
        f"Tipo do relatorio: Parecer tecnico contabil sobre balancete de verificacao\n"
        f"Regime tributario: [VERIFICAR: regime tributario quando existir]\n"
        f"\n### DADOS EXTRAIDOS DO MOTOR DE REGRAS\n"
        f"Pontuacao de risco do motor: {data['pontuacao_total']}\n"
        f"Nivel geral do motor: {data['nivel_geral'].upper()}\n"
        f"\nExplicacao da Pontuacao:\n{explicacao_text}\n"
        f"\nMetricas:\n{metrics_text}\n"
        f"\nAchados Identificados:\n{achados_text}"
    )


def _label(value: str) -> str:
    return value.replace("_", " ").capitalize()


def _system_prompt() -> str:
    return """
Voce deve analisar o balancete disponibilizado e gerar um parecer tecnico contabil em Markdown, seguindo exatamente o template operacional abaixo.

FONTE PRIMARIA
- Use os DADOS EXTRAIDOS DO MOTOR DE REGRAS fornecidos na mensagem do usuario como fonte primaria do relatorio.
- Extraia metricas, pontuacao, nivel geral, explicacao da pontuacao, achados, evidencias e recomendacoes diretamente do motor de regras.
- Nao crie achados, valores, percentuais, contas ou conclusoes que nao estejam nos dados do motor de regras.
- Se algum campo necessario nao estiver nos dados do motor de regras, use [VERIFICAR: dado necessario].

ETAPA 1 - EXTRACAO AUTOMATICA DOS DADOS
Extrair automaticamente:

Identificacao:
- Razao social
- CNPJ
- Periodo
- Regime tributario, quando existir
- Tipo do relatorio

Estrutura contabil:
- Ativo Circulante
- Ativo Nao Circulante
- Passivo Circulante
- Passivo Nao Circulante
- Patrimonio Liquido
- Receitas
- Custos
- Despesas
- Resultado

Para cada conta, considerar:
- Codigo
- Descricao
- Saldo inicial
- Debitos
- Creditos
- Saldo final

ETAPA 2 - EXECUTAR TESTES AUTOMATICOS DE RISCO
Executar os testes abaixo automaticamente, sem depender de nomes exatos das contas.

A. DISPONIBILIDADES
Verificar caixa negativo, banco negativo e caixa elevado sem movimentacao.
Riscos: omissao de receitas, suprimento nao contabilizado, inconsistencia operacional, conciliacao inadequada e emprestimos nao registrados.

B. CLIENTES E RECEBIVEIS
Verificar clientes elevados, clientes sem movimentacao, duplicatas antigas e contas transitorias.
Riscos: receita sem realizacao, credito ficticio e divergencia fiscal.

C. ADIANTAMENTOS
Verificar fornecedores, clientes, empregados e socios.
Riscos: permanencia indevida e falta de documentacao.

D. OBRIGACOES TRIBUTARIAS
Localizar automaticamente contas contendo termos semelhantes a imposto, tributo, simples, IRRF, ISS, ICMS, PIS, COFINS, INSS, FGTS e parcelamento.
Avaliar saldos elevados, ausencia de baixa e crescimento continuo.
Riscos: multas, juros, divida ativa e restricoes fiscais.

E. OBRIGACOES TRABALHISTAS
Verificar salarios, pro-labore, rescisoes e encargos.
Riscos: divergencia com eSocial, DCTFWeb e passivo trabalhista.

F. MOVIMENTACAO COM SOCIOS
Buscar emprestimos, mutuos, adiantamentos e retiradas.
Riscos: distribuicao disfarçada e confusao patrimonial.

G. RESULTADO
Validar receita incompativel, receita sem caixa, despesas excessivas, margem atipica e resultado negativo.
Riscos: inconsistencia operacional e divergencia fiscal.

H. PATRIMONIO LIQUIDO
Verificar PL negativo, prejuizo acumulado e continuidade operacional.
Riscos: necessidade de capitalizacao e fragilidade financeira.

ETAPA 3 - PRIORIZACAO DOS ACHADOS
Classificar cada achado como:
- CRITICO: risco fiscal elevado.
- ALTO: exige validacao imediata.
- MEDIO: necessita monitoramento.
- BAIXO: acompanhamento.

Usar como criterios materialidade, recorrencia e impacto tributario.

ETAPA 4 - GERAR O RELATORIO
O output final deve ter somente estas secoes:

1. Resumo Executivo
Incluir uma tabela Markdown com as colunas: Area, Situacao, Criticidade.

2. Parecer Tecnico
Para cada achado, usar obrigatoriamente os campos:
- Titulo
- Conta
- Saldo
- Movimentacao
- Achado
- Risco identificado
- Impacto potencial, considerando Receita Federal, obrigacoes acessorias e cruzamentos fiscais
- Recomendacao

3. Conclusao
Gerar sintese dos principais riscos, grau geral de exposicao fiscal e proximos passos.
Encerrar obrigatoriamente com o paragrafo:
"Este parecer foi elaborado exclusivamente com base no balancete disponibilizado, sem validacao por documentos auxiliares, extratos, obrigacoes acessorias ou documentacao suporte."

REGRA FINAL
O sistema deve funcionar para qualquer plano de contas, detectando padroes automaticamente sem depender de nomes exatos das contas.

REGRAS DE SEGURANCA
- Nao invente informacoes.
- Quando algum dado necessario estiver ausente, use [VERIFICAR: dado necessario].
- Nao afirmar fraude.
- Nao acusar irregularidade sem evidencia objetiva.
- Usar linguagem tecnica, formal, analitica e profissional.
- O parecer deve permanecer em Markdown.
""".strip()
