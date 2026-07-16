from __future__ import annotations

from typing import Any

from .consultivo import consultivo_for_code


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
