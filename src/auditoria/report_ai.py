from __future__ import annotations

import logging
from datetime import datetime

from .models import AuditResult
from .utils import format_brl

_logger = logging.getLogger(__name__)


_VERIFY_ACCOUNTANT = "[VERIFICAR: nome completo do contador responsavel e CRC ativo]"
_VERIFY_CNPJ = "[VERIFICAR: CNPJ da empresa objeto]"
_VERIFY_PURPOSE = "[VERIFICAR: finalidade do parecer]"
_VERIFY_DOCUMENTS = "[VERIFICAR: demonstracoes e documentos disponibilizados]"
_VERIFY_LOCATION = "[VERIFICAR: local de emissao]"


_PACEF_TEMPLATE = """\
# PARECER TECNICO CONTABIL No. [VERIFICAR: numero/ano]

## RESUMO EXECUTIVO
{resumo_executivo}

---

## 1. IDENTIFICACAO

- **Perito/Contador responsavel:** {contador_responsavel}
- **Contratante:** {cliente}
- **CNPJ da empresa objeto:** {cnpj}
- **Objeto:** Parecer tecnico contabil sobre conformidade, riscos e achados identificados no balancete do periodo {periodo}.
- **Questao tecnica central:** [VERIFICAR: questao tecnica central a ser respondida]
- **Finalidade do parecer:** {finalidade}
- **Periodo contabil analisado:** {periodo}
- **Data de emissao:** {data_atual}
- **Vigencia:** [VERIFICAR: vigencia ou evento de validade do parecer]

Este parecer foi elaborado com base na NBC PG 100 (R1) de 2018 (Estrutura Conceitual), na NBC PG 200 de [VERIFICAR: ano da norma] (independencia), na NBC TA 700 (R1) de [VERIFICAR: ano da norma] (formacao da opiniao), na NBC TG 26 (R3) de [VERIFICAR: ano da norma] = CPC 26 R1 (Apresentacao das Demonstracoes Financeiras) e na Resolucao CFC 1.244/2009 (requisitos formais do laudo e parecer tecnico).

---

## 2. ESCOPO E LIMITACOES

{escopo_limitacoes}

---

## 3. FATOS E ACHADOS

{fatos_achados}

---

## 4. FUNDAMENTACAO TECNICA

{fundamentacao_tecnica}

---

## 5. AJUSTES E IMPACTOS IDENTIFICADOS

{ajustes_impactos}

---

## 6. CONCLUSAO / OPINIAO

{conclusao_opiniao}

---

## 7. ASSINATURA

- **Local e data:** {_local}, {data_atual}
- **Nome:** {contador_responsavel}
- **CRC:** [VERIFICAR: numero do CRC]
- **Especializacao:** [VERIFICAR: especializacao, certificacao de perito contabil CFC quando aplicavel]
- **Rubrica e carimbo:** [VERIFICAR: rubrica, carimbo ou assinatura digital reconhecida conforme exigencia do contratante]

O arquivo de trabalho e a memoria de calculo devem ser preservados pelo prazo aplicavel de guarda documental, observada a Resolucao CFC 1.530/2018, conforme definido nos controles internos do responsavel tecnico.
""".strip()


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
                "Falha ao gerar relatorio via IA. Usando relatorio padrao.",
                exc_info=True,
            )
    return _generate_local_report(result)


def _generate_ai_report(result: AuditResult, *, api_key: str | None = None) -> str:
    from .ai_client import call_openrouter

    prompt_data = _build_prompt_data(result)
    user_message = _format_user_message(prompt_data)
    messages = [
        {"role": "system", "content": _system_prompt()},
        {"role": "user", "content": user_message},
    ]
    return call_openrouter(messages, api_key=api_key)


def _generate_local_report(result: AuditResult) -> str:
    now = datetime.now().strftime("%d/%m/%Y %H:%M")

    return _PACEF_TEMPLATE.format(
        cliente=result.cliente,
        cnpj=_VERIFY_CNPJ,
        contador_responsavel=_VERIFY_ACCOUNTANT,
        finalidade=_VERIFY_PURPOSE,
        periodo=result.periodo,
        data_atual=now,
        _local=_VERIFY_LOCATION,
        resumo_executivo=_render_resumo_executivo(result),
        escopo_limitacoes=_render_escopo_limitacoes(result),
        fatos_achados=_render_fatos_achados(result),
        fundamentacao_tecnica=_render_fundamentacao_tecnica(),
        ajustes_impactos=_render_ajustes_impactos(result),
        conclusao_opiniao=_render_conclusao_opiniao(result),
    )


def _render_resumo_executivo(result: AuditResult) -> str:
    opinion = _tipo_opiniao(result)
    if not result.achados:
        return (
            f"Em linguagem objetiva, a analise automatizada do balancete de {result.cliente} "
            f"no periodo {result.periodo} nao identificou achados relevantes; a opiniao tecnica "
            f"preliminar e **{opinion}**, condicionada a verificacao dos documentos formais "
            f"indicados neste parecer. A conclusao observa a NBC TA 700 (R1) de [VERIFICAR: ano da norma] "
            f"e a NBC TG 26 (R3) de [VERIFICAR: ano da norma] = CPC 26 R1."
        )

    top = sorted(result.achados, key=lambda f: f.pontuacao, reverse=True)[:3]
    top_text = "; ".join(f"{f.codigo} - {f.titulo}" for f in top)
    return (
        f"Em linguagem objetiva, a analise automatizada do balancete de {result.cliente} "
        f"no periodo {result.periodo} indicou risco **{result.nivel_geral.value.upper()}** "
        f"com {result.pontuacao_total} pontos e {len(result.achados)} achado(s), destacando: "
        f"{top_text}. A opiniao tecnica preliminar e **{opinion}**, considerando as limitacoes "
        f"documentais declaradas e a necessidade de confirmar dados marcados como [VERIFICAR]. "
        f"A conclusao observa a NBC TA 700 (R1) de [VERIFICAR: ano da norma], a NBC TA 705 (R1) "
        f"de [VERIFICAR: ano da norma] e a NBC TA 706 (R1) de [VERIFICAR: ano da norma]."
    )


def _render_escopo_limitacoes(result: AuditResult) -> str:
    return (
        f"**Documentos analisados:** {_VERIFY_DOCUMENTS}. O arquivo processado pelo sistema foi tratado "
        f"como balancete contabil do periodo {result.periodo}; demonstracoes completas como Balanco "
        f"Patrimonial, DRE, DMPL, DFC e Notas Explicativas devem ser identificadas em separado quando "
        f"disponiveis.\n\n"
        "**Procedimentos aplicados:** inspecao documental automatizada do balancete, classificacao por "
        "grupos contabeis, recalculo de indicadores, cruzamento de saldos e procedimentos analiticos "
        "sobre receita, tributos, folha, despesas, caixa, bancos, socios, lucros e resultado. Esses "
        "procedimentos sao compatibilizados com a NBC PG 100 (R1) de 2018 (Estrutura Conceitual), "
        "a NBC TA 700 (R1) de [VERIFICAR: ano da norma] e a Resolucao CFC 1.244/2009.\n\n"
        "**Fora do escopo:** auditoria independente completa, confirmacoes externas, circularizacao "
        "bancaria, exame de contratos integrais, validacao fiscal em portais governamentais, revisao "
        "de notas explicativas completas e procedimentos judiciais. Qualquer uso para processo judicial, "
        "banco, reorganizacao societaria ou outra finalidade depende da finalidade declarada em "
        f"{_VERIFY_PURPOSE}.\n\n"
        "**Responsabilidade e independencia:** a administracao da entidade e responsavel pela integridade "
        "dos documentos e informacoes fornecidas; o responsavel tecnico responde pela opiniao emitida "
        "nos limites do escopo documentado. Declara-se independencia tecnica conforme NBC PG 200 de "
        "[VERIFICAR: ano da norma], sem interesse financeiro informado na empresa objeto; caso exista "
        "relacao economica ou conflito, registrar [VERIFICAR: independencia e ameacas identificadas]."
    )


def _render_fatos_achados(result: AuditResult) -> str:
    metrics = "\n".join(f"- **{_label(key)}:** {value}" for key, value in result.resumo_metricas.items())
    if not result.achados:
        findings = "Nao foram identificados achados relevantes pelo motor de regras no periodo analisado."
    else:
        findings = _render_tabela_achados(result)

    return (
        f"**Metricas extraidas do balancete:**\n{metrics}\n\n"
        f"**Achados objetivos:**\n{findings}\n\n"
        "Os fatos acima devem ser cotejados com os documentos-fonte indicados no escopo. A comparacao "
        "entre pratica adotada e norma aplicavel foi realizada com base na NBC TG 26 (R3) de "
        "[VERIFICAR: ano da norma] = CPC 26 R1, na NBC TG 00 (R2) de [VERIFICAR: ano da norma] "
        "= Estrutura Conceitual CPC e nas normas especificas apontadas em cada achado."
    )


def _render_fundamentacao_tecnica() -> str:
    return (
        "- **NBC TG 26 (R3) de [VERIFICAR: ano da norma] = CPC 26 R1:** orienta a apresentacao adequada "
        "das demonstracoes financeiras, incluindo consistencia, materialidade e divulgacoes obrigatorias.\n"
        "- **NBC TG 00 (R2) de [VERIFICAR: ano da norma] = Estrutura Conceitual CPC:** orienta relevancia, "
        "representacao fidedigna, comparabilidade, verificabilidade, tempestividade e compreensibilidade.\n"
        "- **NBC PG 100 (R1) de 2018 (Estrutura Conceitual):** orienta principios eticos, julgamento "
        "profissional e comportamento do contador no trabalho tecnico.\n"
        "- **NBC PG 200 de [VERIFICAR: ano da norma]:** fundamenta independencia e objetividade do "
        "profissional na execucao do parecer.\n"
        "- **NBC TA 700 (R1) de [VERIFICAR: ano da norma]:** fundamenta a formacao da opiniao e a "
        "estrutura conclusiva do parecer.\n"
        "- **NBC TA 705 (R1) de [VERIFICAR: ano da norma]:** fundamenta modificacoes na opiniao quando "
        "os efeitos dos achados sao relevantes.\n"
        "- **NBC TA 706 (R1) de [VERIFICAR: ano da norma]:** fundamenta paragrafo de enfase quando "
        "houver incerteza material ou assunto relevante que nao modifique necessariamente a opiniao.\n"
        "- **Resolucao CFC 1.244/2009:** orienta requisitos formais do laudo e parecer tecnico.\n"
        "- **CPC especifico do tema:** [VERIFICAR: CPC aplicavel, como CPC 47 receita, CPC 06 R2 "
        "arrendamento, CPC 15 combinacao de negocios, CPC 01 impairment ou outro pronunciamento aplicavel]."
    )


def _render_ajustes_impactos(result: AuditResult) -> str:
    if not result.achados:
        return (
            "Nao foram propostos ajustes contabeis pelo motor de regras. A aderencia formal as normas "
            "deve ser confirmada mediante exame das demonstracoes completas e notas explicativas, "
            "conforme NBC TG 26 (R3) de [VERIFICAR: ano da norma] = CPC 26 R1.\n\n"
            "| Ajuste | Valor | Norma | Impacto |\n"
            "| :--- | :--- | :--- | :--- |\n"
            "| Nao aplicavel no escopo automatizado | R$ 0,00 | NBC TA 700 (R1) de [VERIFICAR: ano da norma] | Sem impacto identificado no PL, resultado e indices pelo motor de regras |"
        )

    rows = [
        "| Ajuste proposto | Valor em R$ | Norma/fundamento | Correcao necessaria | Impacto em PL, resultado e indices |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]
    for finding in sorted(result.achados, key=lambda f: f.pontuacao, reverse=True):
        rows.append(
            "| "
            f"{finding.codigo} - {finding.titulo} | "
            f"[VERIFICAR: valor contabil do ajuste; evidencias: {_format_evidencia(finding)}] | "
            f"{_get_fundamentacao(finding)}; NBC TA 705 (R1) de [VERIFICAR: ano da norma] | "
            f"{finding.recomendacao or _get_medidas_acao(finding)[0]} | "
            "[VERIFICAR: impacto no patrimonio liquido, resultado, liquidez corrente, endividamento e ROE] |"
        )

    return (
        "\n".join(rows)
        + "\n\n"
        "Quando o valor do ajuste nao estiver demonstrado no balancete processado, o parecer registra "
        "[VERIFICAR: valor contabil do ajuste] para impedir estimativa sem documento suporte, conforme "
        "NBC PG 100 (R1) de 2018 e Resolucao CFC 1.244/2009."
    )


def _render_conclusao_opiniao(result: AuditResult) -> str:
    opinion = _tipo_opiniao(result)
    if opinion == "NAO MODIFICADA":
        conclusion = (
            f"As demonstracoes financeiras apresentam adequadamente, em todos os aspectos relevantes, "
            f"a posicao patrimonial e financeira de {result.cliente} no periodo {result.periodo}, "
            "em conformidade com as praticas contabeis adotadas no Brasil, observada a NBC TG 26 "
            "(R3) de [VERIFICAR: ano da norma] = CPC 26 R1."
        )
    elif opinion == "COM RESSALVA":
        effects = "; ".join(f"{f.codigo} - {f.titulo}" for f in sorted(result.achados, key=lambda f: f.pontuacao, reverse=True)[:5])
        conclusion = (
            f"Exceto pelos efeitos dos achados {effects}, as demonstracoes financeiras apresentam "
            f"adequadamente, em todos os aspectos relevantes, a posicao patrimonial e financeira de "
            f"{result.cliente} no periodo {result.periodo}, em conformidade com as praticas contabeis "
            "adotadas no Brasil, observada a NBC TG 26 (R3) de [VERIFICAR: ano da norma] = CPC 26 R1. "
            "A ressalva e formulada com base na NBC TA 705 (R1) de [VERIFICAR: ano da norma]."
        )
    else:
        conclusion = (
            f"Os achados identificados sao generalizados e relevantes para a leitura das demonstracoes "
            f"de {result.cliente} no periodo {result.periodo}; por esse motivo, a opiniao tecnica "
            "preliminar e adversa, nos termos da NBC TA 705 (R1) de [VERIFICAR: ano da norma], "
            "ate que os ajustes marcados como [VERIFICAR] sejam quantificados e corrigidos."
        )

    emphasis = ""
    if any(f.codigo.startswith("SN-009") for f in result.achados):
        emphasis = (
            "\n\n**Paragrafo de enfase:** ha indicio de prejuizo contabil ou risco de continuidade, "
            "assunto que deve ser destacado conforme NBC TA 706 (R1) de [VERIFICAR: ano da norma], "
            "sem substituir a quantificacao dos ajustes indicados na Secao 5."
        )

    return (
        f"**Tipo de opiniao:** {opinion}.\n\n"
        f"{conclusion}{emphasis}\n\n"
        "A opiniao esta limitada ao escopo da Secao 2, aos documentos efetivamente disponibilizados e "
        "aos dados que nao estejam marcados como [VERIFICAR: dado necessario]."
    )


def _tipo_opiniao(result: AuditResult) -> str:
    high_count = sum(1 for finding in result.achados if finding.nivel.value == "alto")
    if not result.achados:
        return "NAO MODIFICADA"
    if result.pontuacao_total >= 90 or high_count >= 3:
        return "ADVERSA"
    return "COM RESSALVA"


def _render_introducao(result: AuditResult) -> str:
    if not result.achados:
        return (
            "Este parecer tecnico apresenta o diagnostico de conformidade contabil e "
            "fiscal da entidade, fundamentado no cruzamento de dados e aplicacao de "
            "motor de regras sobre o balancete verificado. A analise nao identificou "
            "indicios relevantes de passivos ocultos, inconsistencias operacionais ou "
            "gatilhos de malha fina junto aos orgaos reguladores no periodo analisado."
        )

    high = sum(1 for f in result.achados if f.nivel.value == "alto")
    medium = sum(1 for f in result.achados if f.nivel.value == "medio")
    low = sum(1 for f in result.achados if f.nivel.value == "baixo")

    achados_list = ", ".join(
        f"{f.codigo} ({f.titulo})" for f in sorted(result.achados, key=lambda x: x.pontuacao, reverse=True)
    )

    return (
        f"Este parecer tecnico apresenta o diagnostico de conformidade contabil e "
        f"fiscal da entidade, fundamentado no cruzamento de dados e aplicacao de "
        f"motor de regras sobre o balancete verificado. A analise foca na "
        f"identificacao de passivos ocultos, inconsistencias operacionais e gatilhos "
        f"de malha fina junto aos orgaos reguladores.\n\n"
        f"O nivel de risco apurado foi **{result.nivel_geral.value.upper()}**, com "
        f"pontuacao de **{result.pontuacao_total} pontos**, decorrente de "
        f"**{len(result.achados)} achado(s)**: {high} de risco alto, {medium} de "
        f"risco medio e {low} de risco baixo. As irregularidades identificadas foram: "
        f"{achados_list}."
    )


def _render_tabela_achados(result: AuditResult) -> str:
    if not result.achados:
        return (
            "| Regra Identificada | Evidencia e Analise Tecnica | Fundamentacao e Risco Fiscal |\n"
            "| :--- | :--- | :--- |\n"
            "| _Nenhuma irregularidade identificada neste periodo._ | | |"
        )

    rows = []
    for f in sorted(result.achados, key=lambda x: x.pontuacao, reverse=True):
        regra = f"**{f.codigo}**<br>{f.titulo}"
        evidencia = f"**Valor:** {_format_evidencia(f)}<br><br>{_get_analise_tecnica(f)}"
        fundamentacao = f"{_get_fundamentacao(f)}<br><br>**Impacto:** {_get_risco_fiscal(f)}"
        rows.append(f"| {regra} | {evidencia} | {fundamentacao} |")

    header = "| Regra Identificada | Evidencia e Analise Tecnica | Fundamentacao e Risco Fiscal |\n| :--- | :--- | :--- |"
    return header + "\n" + "\n".join(rows)


def _render_tabela_impactos(result: AuditResult) -> str:
    header = "| Natureza | Descricao das Consequencias |\n| :--- | :--- |"

    linhas = [
        "| **Sansoes Administrativas** | Risco de autuacoes com multas de oficio que podem variar de 75% a 150% sobre tributos nao recolhidos ou bases omitidas. |",
        "| **Regime Tributario** | Possibilidade de exclusao de regimes simplificados (Simples Nacional) e migracao compulsoria para regimes mais onerosos (Lucro Presumido/Real). |",
    ]

    if any(f.codigo.startswith(("SN-006", "SN-008")) for f in result.achados):
        linhas.append(
            "| **Risco Fiscal** | Indicios de omissao de receita passiveis de representacao fiscal para fins penais tributarios, alem de correcao monetaria por SELIC. |"
        )

    if any(f.codigo.startswith("SN-009") for f in result.achados):
        linhas.append(
            "| **Continuidade** | Questionamento sobre a continuidade da empresa (ITG 2000), com risco de dissolucao ou exclusao do Simples Nacional. |"
        )

    return header + "\n" + "\n".join(linhas)


def _render_medidas_diretas(result: AuditResult) -> str:
    if not result.achados:
        return (
            "Nao ha medidas corretivas a serem tomadas neste periodo. "
            "Recomenda-se a manutencao das praticas contabeis e fiscais vigentes."
        )

    blocos = []
    for f in sorted(result.achados, key=lambda x: x.pontuacao, reverse=True):
        acoes = _get_medidas_acao(f)
        bloco = f"**{f.codigo} — {f.titulo}**\n"
        for idx, acao in enumerate(acoes, 1):
            bloco += f"{idx}. {acao}\n"
        blocos.append(bloco)

    return "\n".join(blocos)


def _render_recomendacao_gestao(result: AuditResult) -> str:
    if not result.achados:
        return (
            "A empresa demonstra conformidade adequada com as obrigacoes contabeis "
            "e fiscais. Recomenda-se a manutencao dos controles vigentes, com "
            "realizacao de conciliacoes bancarias mensais, revisao trimestral do "
            "enquadramento tributario e manutencao da documentacao fiscal organizada."
        )

    recomendacoes = {
        "alto": (
            "A situacao de risco elevado exige acoes imediatas de regularizacao. "
            "Recomenda-se revisao integral da escrituracao, implementacao de controles internos "
            "robustos e conciliacao mensal entre dados fiscais, contabeis e bancarios. "
            "A empresa deve instituir um calendario de verificacoes trimestrais para "
            "monitorar os indicadores de risco e evitar a reincidencia das "
            "irregularidades identificadas."
        ),
        "medio": (
            "A empresa apresenta riscos moderados que, se nao corrigidos, podem "
            "evoluir para situacoes de alta exposicao fiscal. Recomenda-se a "
            "implementacao de controles de conciliacao entre faturamento declarado "
            "e movimentacao bancaria, revisao periodica da classificacao fiscal e "
            "formalizacao de todas as operacoes com socios e terceiros. A adocao "
            "de rotinas de verificacao mensal contribuira para a mitigacao dos "
            "riscos identificados."
        ),
        "baixo": (
            "Os riscos identificados sao de baixa intensidade, mas merecem atencao "
            "para evitar agravamento. Recomenda-se o fortalecimento das rotinas "
            "de escrituracao contabil, com conciliacoes regulares e revisao dos "
            "procedimentos de lancamento. Manter a documentacao fiscal atualizada "
            "e realizar auditorias internas periodicas sao praticas que fortalecem "
            "a conformidade da empresa."
        ),
    }
    return recomendacoes.get(result.nivel_geral.value, recomendacoes["baixo"])


def _format_evidencia(finding) -> str:
    if not finding.evidencia:
        return "Nao aplicavel"
    return "; ".join(f"{_label(k)}: {v}" for k, v in finding.evidencia.items())


def _get_analise_tecnica(finding) -> str:
    analises = {
        "SN-001": (
            "A receita bruta acumulada nos ultimos 12 meses atinge ou ultrapassa "
            "o limite establecido para o regime do Simples Nacional. Essa situacao "
            "implica a obrigatoriedade de migracao para regime de tributacao "
            "mais complexo, com impacto direto na carga tributaria da empresa."
        ),
        "SN-001A": (
            "A receita bruta acumulada nos ultimos 12 meses atinge ou ultrapassa "
            "o limite establecido para o regime do Simples Nacional. Essa situacao "
            "implica a obrigatoriedade de migracao para regime de tributacao "
            "mais complexo, com impacto direto na carga tributaria da empresa."
        ),
        "SN-002": (
            "A carga tributaria efetiva representa percentual inferior ao esperado "
            "para a faixa de faturamento declarada. Esse indicador sugere possivel "
            "erro na apuracao do DAS, classificacao fiscal inadequada ou omissao "
            "de guias de recolhimento."
        ),
        "SN-002B": (
            "A carga tributaria efetiva representa percentual inferior ao esperado "
            "para a faixa de faturamento declarada. Esse indicador sugere possivel "
            "erro na apuracao do DAS, classificacao fiscal inadequada ou omissao "
            "de guias de recolhimento."
        ),
        "SN-003": (
            "A proporcao entre folha de pagamento (incluindo pro-labore) e receita "
            "bruta encontra-se abaixo do patamar considerado adequado para empresas "
            "de servicos. Essa relacao compromete o atendimento ao Fator R, podendo "
            "acarretar reclassificacao tributaria para anexo mais oneroso."
        ),
        "SN-004A": (
            "Os valores distribuidos a titulo de lucros ou dividendos superam o "
            "resultado liquido apurado no periodo. Essa discrepancia indica que "
            "recursos foram entregues aos socios sem lastro contbil suficiente, "
            "o que caracteriza remuneracao disfarada sujeita a tributacao."
        ),
        "SN-005": (
            "Contas vinculadas a socios ou administradores apresentam saldos "
            "relevantes em relacao a receita operacional. Essa concentracao pode "
            "indicar emprestimos nao formalizados, adiantamentos sem documentacao "
            "ou confusao entre patrimonio da empresa e dos socios."
        ),
        "SN-006": (
            "O balancete evidencia saldo negativo nas contas de caixa e bancos, "
            "situacao contabilmente improvavel que indica inconsistencias nos "
            "lancamentos. Pode tratar-se de receitas nao registradas, despesas "
            "sem comprovacao ou movimentacoes de socios nao escrituradas."
        ),
        "SN-006A": (
            "O balancete evidencia saldo negativo nas contas de caixa e bancos, "
            "situacao contabilmente improvavel que indica inconsistencias nos "
            "lancamentos. Pode tratar-se de receitas nao registradas, despesas "
            "sem comprovacao ou movimentacoes de socios nao escrituradas."
        ),
        "SN-007": (
            "As despesas operacionais representam proporcao elevada em relacao a "
            "receita bruta, sugerindo possiveis lancamentos sem documentacao "
            "idonea ou despesas sem nexo com a atividade da empresa."
        ),
        "SN-008": (
            "Houve movimentacao financeira relevante (entradas em conta) sem "
            "receita correspondente declarada no PGDAS. Essa divergencia entre "
            "fluxo bancario e faturamento fiscal configura indicio de omissao "
            "de receita, com alto risco de cruzamento pela e-Financeira."
        ),
        "SN-008A": (
            "Houve movimentacao financeira relevante (entradas em conta) sem "
            "receita correspondente declarada no PGDAS. Essa divergencia entre "
            "fluxo bancario e faturamento fiscal configura indicio de omissao "
            "de receita, com alto risco de cruzamento pela e-Financeira."
        ),
        "SN-009": (
            "A empresa registrou prejuizo contabil com ausencia ou insuficiencia "
            "de receita. Essa situacao indica despesas registradas sem contrapartida "
            "de faturamento, levantando questionamentos sobre a efetividade da "
            "atividade economica no periodo e a continuidade da empresa."
        ),
        "SN-009A": (
            "A empresa registrou prejuizo contabil com ausencia ou insuficiencia "
            "de receita. Essa situacao indica despesas registradas sem contrapartida "
            "de faturamento, levantando questionamentos sobre a efetividade da "
            "atividade economica no periodo e a continuidade da empresa."
        ),
        "SN-009B": (
            "A empresa registrou prejuizo contabil com ausencia ou insuficiencia "
            "de receita. Essa situacao indica despesas registradas sem contrapartida "
            "de faturamento, levantando questionamentos sobre a efetividade da "
            "atividade economica no periodo e a continuidade da empresa."
        ),
    }
    return analises.get(
        finding.codigo,
        f"O achado {finding.codigo} aponta inconsistencia nas metricas contabeis "
        f"que requer investigacao tecnica detalhada."
    )


def _get_fundamentacao(finding) -> str:
    fundamentacoes = {
        "SN-001": (
            "Lei Complementar 123/2006, Art. 19 (limites do Simples Nacional); "
            "Art. 44 da Lei 9.430/96 (multa por desenquadramento)."
        ),
        "SN-001A": (
            "Lei Complementar 123/2006, Art. 19 (limites do Simples Nacional); "
            "Art. 44 da Lei 9.430/96 (multa por desenquadramento)."
        ),
        "SN-002": (
            "Lei Complementar 123/2006 (regime de apuracao do Simples Nacional); "
            "Art. 82 da Lei 9.430/96 (multa de 75% por infracao)."
        ),
        "SN-002B": (
            "Lei Complementar 123/2006 (regime de apuracao do Simples Nacional); "
            "Art. 82 da Lei 9.430/96 (multa de 75% por infracao)."
        ),
        "SN-003": (
            "Lei Complementar 123/2006, Art. 18, par. 17 (Fator R); "
            "IN RFB 1.700/2017 (classificacao por anexos)."
        ),
        "SN-004A": (
            "Lei 9.249/95, Art. 10 (distribuicao de lucros isenta); "
            "Art. 43 da Lei 9.430/96 (tributacao de valores sem lastro)."
        ),
        "SN-005": (
            "Art. 50 do Codigo Civil (confusao patrimonial); "
            "Art. 43 do CTN (disponibilidade economica); "
            "ITG 2000 (R1) — Escrituracao Contabil."
        ),
        "SN-006": (
            "Art. 281 do RIR/2018 (presuncao de omissao de receita); "
            "Art. 47 da Lei 9.430/96; "
            "ITG 2000 (R1) — Escrituracao Contabil."
        ),
        "SN-006A": (
            "Art. 281 do RIR/2018 (presuncao de omissao de receita); "
            "Art. 47 da Lei 9.430/96; "
            "ITG 2000 (R1) — Escrituracao Contabil."
        ),
        "SN-007": (
            "Art. 299 do RIR/2018 (despesas necessarias a atividade); "
            "Art. 338 do RIR/2018 (comprovacao documental)."
        ),
        "SN-008": (
            "IN RFB 1.919/2019 (e-Financeira); "
            "Art. 281 do RIR/2018; Art. 82 da Lei 9.430/96."
        ),
        "SN-008A": (
            "IN RFB 1.919/2019 (e-Financeira); "
            "Art. 281 do RIR/2018; Art. 82 da Lei 9.430/96."
        ),
        "SN-009": (
            "ITG 2000 (R1) — Continuidade; "
            "Art. 188 da Lei 6.404/76; "
            "NBC TG 26 (demonstracoes contabeis)."
        ),
        "SN-009A": (
            "ITG 2000 (R1) — Continuidade; "
            "Art. 188 da Lei 6.404/76; "
            "NBC TG 26 (demonstracoes contabeis)."
        ),
        "SN-009B": (
            "ITG 2000 (R1) — Continuidade; "
            "Art. 188 da Lei 6.404/76; "
            "NBC TG 26 (demonstracoes contabeis)."
        ),
    }
    return fundamentacoes.get(
        finding.codigo,
        "Fundamentacao especifica pendente de vinculacao normativa: [VERIFICAR: norma contabil aplicavel]."
    )


def _get_risco_fiscal(finding) -> str:
    return f"Risco {finding.nivel.value.upper()} de autuacao fiscal."


def _get_medidas_acao(finding) -> list[str]:
    base_code = finding.codigo[:6]
    acoes_map = {
        "SN-001": [
            "Levantar o faturamento acumulado dos ultimos 12 meses e "
            "avaliar a posicao em relacao ao limite do Simples Nacional.",
            "Caso o limite tenha sido ultrapassado, comunicar a RFB e "
            "iniciar a migracao para o regime de tributacao adequado.",
        ],
        "SN-002": [
            "Revisar a classificacao fiscal de todas as notas emitidas e "
            "verificar a corretude dos calculos do DAS por anexo.",
            "Emitir guias complementares caso identificadas diferencas "
            "entre o faturamento declarado e os valores recolhidos.",
        ],
        "SN-003": [
            "Calcular o Fator R (folha de pagamento dividida pela receita) "
            "e avaliar a necessidade de ajuste no pro-labore dos socios.",
            "Documentar a proporcao de folha e justificar o enquadramento "
            "no anexo aplicavel, ou reclassificar para anexo V se necessario.",
        ],
        "SN-004": [
            "Conciliar os valores distribuidos com o resultado liquido "
            "do periodo e identificar eventuais excedentes sem lastro.",
            "Formalizar os excedentes como mutuo contratual, adiantamento "
            "de lucro futuro ou remuneracao de socios com retencao de IRPF.",
        ],
        "SN-005": [
            "Classificar a natureza de cada saldo em contas de socios "
            "(mutuo, adiantamento, reembolso) e formalizar com contratos.",
            "Reconciliar as movimentacoes entre empresa e socios, "
            "elaborando demonstrativo de contas correntes.",
        ],
        "SN-006": [
            "Conciliar os saldos de caixa e bancos com os extratos "
            "bancarios e identificar lancamentos divergentes ou omissoes.",
            "Regularizar as inconsistencias com lancamentos de ajuste, "
            "complementando receitas ou corrigindo despesas nao documentadas.",
        ],
        "SN-007": [
            "Auditar as despesas lancadas e verificar a existencia de "
            "documentacao fiscal idonea para cada item despesa.",
            "Eliminar lancamentos sem comprovacao e formalizar contratos "
            "de servicos de terceiros onde aplicavel.",
        ],
        "SN-008": [
            "Conciliar as entradas bancarias com o faturamento declarado "
            "no PGDAS e identificar receitas nao escrituradas.",
            "Emitir notas fiscais complementares e recolher o DAS em "
            "atraso com as multas e juros devidos.",
        ],
        "SN-009": [
            "Investigar as causas do prejuizo contabil, separando despesas "
            "operacionais de nao operacionais e verificando receitas omitidas.",
            "Avaliar a viabilidade economica da continuidade do negocio "
            "e documentar o plano de recuperacao, conforme ITG 2000.",
        ],
    }
    return acoes_map.get(
        base_code,
        [
            f"Analisar tecnicamente o achado {finding.codigo} e documentar "
            "as causas raiz da inconsistencia.",
            f"Implementar controles contabeis preventivos para evitar a "
            f"recorrencia do achado {finding.codigo} nos proximos periodos.",
        ],
    )


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


def _format_user_message(data: dict) -> str:
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
        f"Empresa objeto: {data['cliente']} - CNPJ [VERIFICAR: CNPJ da empresa objeto]\n"
        f"Responsavel pelo parecer: [VERIFICAR: nome completo e CRC ativo]\n"
        f"Periodo analisado: {data['periodo']}\n"
        f"Documentos disponiveis: [VERIFICAR: Balanco Patrimonial, DRE, DMPL, DFC, Notas Explicativas e datas]\n"
        f"Questao tecnica central: [VERIFICAR: o que deve ser opinado]\n"
        f"Finalidade do parecer: [VERIFICAR: processo judicial, banco, reorganizacao societaria ou outro]\n"
        f"Pontuacao de risco do motor: {data['pontuacao_total']}\n"
        f"Nivel geral do motor: {data['nivel_geral'].upper()}\n"
        f"\nExplicacao da Pontuacao:\n{explicacao_text}\n"
        f"\nMetricas:\n{metrics_text}\n"
        f"\nAchados Identificados:\n{achados_text}"
    )


def _label(value: str) -> str:
    return value.replace("_", " ").capitalize()


def _system_prompt() -> str:
    return (
        "Voce e contador com CRC ativo e experiencia em pareceres tecnicos formais. "
        "Sua tarefa e redigir um parecer tecnico contabil completo, seguindo estrutura "
        "ABNT NBR 14724 adaptada para documentos contabeis e as normas do CFC.\n\n"
        "REGRAS OBRIGATORIAS\n"
        "- NUNCA usar expressoes como \"salvo melhor juizo\", \"a meu ver\" ou "
        "\"consulte um especialista\". O parecer e a opiniao tecnica qualificada.\n"
        "- SEMPRE citar a norma completa com numero e ano quando o ano estiver disponivel. "
        "Use obrigatoriamente NBC PG 100 (R1) de 2018 (Estrutura Conceitual), "
        "NBC TA 700 (R1) (formacao da opiniao), NBC TG 26 (R3) = CPC 26 R1 "
        "(Apresentacao das DFs), NBC PG 200 (independencia), NBC TA 705 (R1), "
        "NBC TA 706 (R1), Resolucao CFC 1.244/2009 e ABNT NBR 14724.\n"
        "- SEMPRE incluir paragrafo de responsabilidade e escopo, indicando o que foi "
        "e o que nao foi analisado.\n"
        "- Se algum dado estiver ausente, inserir [VERIFICAR: dado necessario]. Nunca inventar.\n"
        "- Fonte normativa prioritaria: Resolucao CFC 1.244/2009, NBC PG 200, "
        "NBC TA 700 (R1), NBC TA 705 (R1), NBC TA 706 (R1), NBC TG 26 (R3) = CPC 26 R1 "
        "e NBC PG 100 (R1) de 2018.\n"
        "- Formato obrigatorio: titulo, identificacao das partes, objeto, escopo, "
        "metodologia, fundamentacao, conclusao, data, assinatura e CRC.\n\n"
        "FRAMEWORK P.A.C.E.F - SIGA NA ORDEM\n"
        "1. PROBLEMATIZACAO: identifique questao tecnica central, solicitante, finalidade, "
        "periodo, documentos, conflitos normativos e incerteza material para eventual "
        "paragrafo de enfase conforme NBC TA 706 (R1).\n"
        "2. APURACAO: redija as 7 secoes: IDENTIFICACAO; ESCOPO E LIMITACOES; FATOS E "
        "ACHADOS; FUNDAMENTACAO TECNICA; AJUSTES E IMPACTOS IDENTIFICADOS; "
        "CONCLUSAO/OPINIAO; ASSINATURA.\n"
        "3. CONFORMIDADE: mencione Resolucao CFC 1.244/2009, NBC PG 200, NBC TA 700 "
        "(R1), NBC TA 705 (R1), NBC TA 706 (R1), NBC TG 26 (R3) = CPC 26 R1, ABNT "
        "NBR 14724 e guarda por 5 anos conforme Resolucao CFC 1.530/2018.\n"
        "4. EXECUCAO: descreva coleta dos documentos, procedimentos analiticos, "
        "recalculos, revisao interna e versao definitiva.\n"
        "5. FECHAMENTO: entregue parecer completo nas 7 secoes, resumo executivo em "
        "linguagem leiga, checklist final, tipo de opiniao definido (nao modificada, "
        "com ressalva ou adversa), paragrafo de enfase quando aplicavel e ajustes "
        "quantificados; quando faltar valor, use [VERIFICAR: valor do ajuste]."
    )
