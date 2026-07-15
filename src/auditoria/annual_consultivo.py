from __future__ import annotations

from typing import Any

from .consultivo import consultivo_for_code


def build_annual_consultivo(
    risk: dict[str, Any],
    totals: dict[str, Any],
    quarters: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    evolution: dict[str, Any],
) -> dict[str, Any]:
    return {
        "leitura_cliente": _annual_consultivo_leitura_cliente(risk, totals, findings, evolution),
        "proximos_passos": _annual_next_steps(risk, quarters, findings, evolution),
        "plano_acao_anual": [_annual_consultivo_item(finding, evolution) for finding in findings],
    }


def _annual_consultivo_leitura_cliente(
    risk: dict[str, Any],
    totals: dict[str, Any],
    findings: list[dict[str, Any]],
    evolution: dict[str, Any],
) -> str:
    recurrent = evolution.get("achados_recorrentes") or []
    recurrent_text = ", ".join(f"{item['codigo']} ({item['trimestres']} trimestres)" for item in recurrent[:5])
    if not recurrent_text:
        recurrent_text = "sem recorrência material indicada pelo motor"
    main_findings = "; ".join(f"{item['codigo']} - {item['titulo']}" for item in findings[:4]) or "nenhum achado anual adicional"
    return (
        f"A análise anual consolidou receita de {totals['receita_servicos_total']['formatado']} e resultado de "
        f"{totals['lucro_apurado_total']['formatado']}. O risco anual foi classificado como {risk['nivel_geral']}, "
        f"com tendência de {evolution.get('tendencia_risco', 'insuficiente')} e recorrências em {recurrent_text}. "
        f"Principais pontos para orientação ao cliente: {main_findings}."
    )


def _annual_next_steps(
    risk: dict[str, Any],
    quarters: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    evolution: dict[str, Any],
) -> list[str]:
    steps = [
        "validar os achados anuais com balancetes, razões contábeis, documentos fiscais e extratos",
        "registrar responsável e prazo para cada providência do plano de ação anual",
        "acompanhar a baixa das pendências no primeiro fechamento trimestral do próximo exercício",
    ]
    if risk.get("nivel_geral") == "alto":
        steps.insert(0, "priorizar a regularização antes de distribuição de lucros, tomada de crédito ou decisões societárias")
    if len(quarters) < 4:
        steps.append("complementar os trimestres ausentes antes de emitir conclusão anual definitiva")
    if evolution.get("achados_recorrentes"):
        steps.append("criar rotina preventiva para achados recorrentes, evitando repetição nos próximos trimestres")
    if not findings:
        steps.append("manter documentação suporte e conciliações periódicas mesmo sem achados anuais adicionais")
    return steps


def _annual_consultivo_item(finding: dict[str, Any], evolution: dict[str, Any]) -> dict[str, Any]:
    consultive = consultivo_for_code(str(finding.get("codigo") or ""), severity=str(finding.get("nivel") or ""))
    has_consultive_mapping = bool(consultive.get("matched"))
    return {
        "codigo": finding["codigo"],
        "prioridade": annual_priority_label(finding["nivel"]),
        "ponto_atencao": finding["titulo"],
        "o_que_significa": (
            str(consultive.get("o_que_significa") or "")
            if has_consultive_mapping
            else annual_meaning(finding, evolution)
        ),
        "como_solucionar": (
            str(consultive.get("como_solucionar") or "")
            if has_consultive_mapping
            else finding["recomendacao"]
        ),
        "documentos_necessarios": annual_documents_for_finding(finding),
        "responsavel_sugerido": (
            str(consultive.get("responsavel_sugerido") or "")
            if has_consultive_mapping
            else annual_owner(finding)
        ),
        "prazo_sugerido": (
            str(consultive.get("prazo_sugerido") or "")
            if has_consultive_mapping
            else annual_deadline(finding["nivel"])
        ),
    }


def annual_priority_label(level: str) -> str:
    labels = {"alto": "alta", "medio": "media", "baixo": "baixa"}
    return labels.get(str(level).lower(), "media")


def annual_deadline(level: str) -> str:
    if str(level).lower() == "alto":
        return "imediato, antes do próximo fechamento societário ou fiscal relevante"
    if str(level).lower() == "medio":
        return "até o primeiro fechamento trimestral do próximo exercício"
    return "acompanhar no próximo ciclo anual"


def annual_orientation(value: str) -> str:
    if value == "sem_ressalva":
        return "manter controles e documentação suporte com acompanhamento preventivo"
    if value == "com_ressalva":
        return "regularizar, documentar e validar os pontos destacados antes do próximo fechamento anual"
    if value == "adversa":
        return "priorizar a regularização dos achados relevantes antes de usar os dados para crédito, distribuição de lucros ou decisões societárias"
    if value == "abstencao_opiniao":
        return "obter documentação complementar antes de concluir sobre o exercício"
    return str(value).replace("_", " ")


def annual_meaning(finding: dict[str, Any], evolution: dict[str, Any]) -> str:
    code = str(finding.get("codigo") or "")
    if code.startswith("AN-REC"):
        return "O mesmo tipo de achado apareceu em mais de um trimestre, indicando que o ponto não foi apenas pontual e precisa de rotina de correção."
    if code.startswith("AN-SN-001"):
        return "A receita anual exige acompanhamento do limite do Simples Nacional e validação do enquadramento fiscal."
    if code.startswith("AN-LUC"):
        return "A distribuição de lucros precisa ser conciliada com o resultado anual, lucros acumulados e documentação societária."
    if code.startswith("AN-MAR"):
        return "A margem anual elevada pode indicar despesas, custos ou apropriações de competência não reconhecidos."
    if code.startswith("AN-DOC-MUTUO"):
        return "Saldos finais com sócios exigem contrato, conciliação financeira e validação de IOF quando houver mútuo."
    if code.startswith("AN-COM"):
        return "A operação comercial precisa de validação de estoque, fornecedores, CMV e créditos fiscais."
    if code.startswith("AN-TRIB"):
        return "Há ponto tributário acumulado que deve ser conciliado com DAS, parcelamentos, guias e saldos fiscais."
    if code.startswith("AN-TEND"):
        return f"A evolução anual indica tendência de {evolution.get('tendencia_risco', 'risco não informada')}, exigindo acompanhamento no próximo exercício."
    return str(finding.get("descricao") or "O achado anual requer validação documental e acompanhamento no próximo exercício.")


def annual_documents_for_finding(finding: dict[str, Any]) -> list[str]:
    evidence = finding.get("evidencia") or {}
    docs = evidence.get("documentos_recomendados") or []
    if docs:
        return [str(item) for item in docs]
    consultive = consultivo_for_code(str(finding.get("codigo") or ""), severity=str(finding.get("nivel") or ""))
    if consultive.get("matched") and consultive.get("documentos_necessarios"):
        return [str(item) for item in consultive["documentos_necessarios"]]
    code = str(finding.get("codigo") or "")
    if code.startswith("AN-LUC"):
        return ["balancete anual", "DRE", "razão de lucros", "comprovantes de distribuição"]
    if code.startswith("AN-DOC-MUTUO"):
        return ["razão das contas de sócios", "extratos bancários", "contrato de mútuo", "guia/comprovante de IOF"]
    if code.startswith("AN-COM"):
        return ["inventário", "relatório de estoque", "notas de compra e venda", "memória do CMV"]
    if code.startswith("AN-TRIB"):
        return ["PGDAS-D", "DAS", "parcelamentos", "razão de tributos a recolher"]
    return ["JSONs trimestrais", "balancetes", "razões contábeis", "documentos fiscais e extratos"]


def annual_owner(finding: dict[str, Any]) -> str:
    code = str(finding.get("codigo") or "")
    if code.startswith(("AN-SN", "AN-TRIB")):
        return "Fiscal + contabilidade"
    if code.startswith(("AN-LUC", "AN-DOC-MUTUO")):
        return "Sócios/administradores + contabilidade"
    if code.startswith("AN-COM"):
        return "Cliente/estoque/financeiro + contabilidade"
    return "Cliente + contabilidade"
