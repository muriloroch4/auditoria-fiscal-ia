from __future__ import annotations

from typing import Any

from .models import RiskLevel, RuleFinding

VERIFY = "[VERIFICAR: dado necessário]"

NORMA_LABELS = {
    "LC 123/2006": "Lei Complementar nº 123/2006",
    "art. 3° LC 123/2006": "Lei Complementar nº 123/2006, art. 3º",
    "art. 14° LC 123/2006": "Lei Complementar nº 123/2006, art. 14",
    "art. 18° LC 123/2006": "Lei Complementar nº 123/2006, art. 18",
    "art. 20 LC 123/2006": "Lei Complementar nº 123/2006, art. 20",
    "art. 47° LC 123/2006": "Lei Complementar nº 123/2006, art. 47",
    "Anexo I da LC 123/2006": "Lei Complementar nº 123/2006, Anexo I",
    "Anexo III da LC 123/2006": "Lei Complementar nº 123/2006, Anexo III",
    "Anexos I e III/V da LC 123/2006": "Lei Complementar nº 123/2006, Anexos I e III/V",
    "LC 155/2016": "Lei Complementar nº 155/2016",
    "CPC 16 R1": "NBC TG 16 (R2) = CPC 16 R1",
    "NBC TG 1000": "NBC TG 1000 (R1)",
    "ITG 2000": "ITG 2000 (R1)",
    "Decreto 6.306/2007": "Decreto nº 6.306/2007 (Regulamento do IOF)",
}

BASE_NORMAS = (
    "Resolução CFC n.º 1.244/2009",
    "NBC PG 100 (R1) de 2018",
    "NBC PG 200",
    "NBC TA 700 (R1)",
    "NBC TG 26 (R3) = CPC 26 R1",
    "NBC TG 00 (R2)",
)


def severity_counts(findings: list[RuleFinding]) -> dict[str, int]:
    return {
        "alta": sum(1 for finding in findings if finding.nivel == RiskLevel.ALTO),
        "media": sum(1 for finding in findings if finding.nivel == RiskLevel.MEDIO),
        "baixa": sum(1 for finding in findings if finding.nivel == RiskLevel.BAIXO),
    }


def severity_label(level: RiskLevel) -> str:
    labels = {
        RiskLevel.ALTO: "alta",
        RiskLevel.MEDIO: "media",
        RiskLevel.BAIXO: "baixa",
    }
    return labels.get(level, "baixa")


def severity_text(level: RiskLevel) -> str:
    labels = {
        RiskLevel.ALTO: "alta",
        RiskLevel.MEDIO: "média",
        RiskLevel.BAIXO: "baixa",
    }
    return labels.get(level, "baixa")


def opinion_label(opinion: str) -> str:
    labels = {
        "sem_ressalva": "sem ressalva",
        "com_ressalva": "com ressalva",
        "adversa": "adversa",
        "abstencao_opiniao": "abstenção de opinião",
    }
    return labels.get(opinion, opinion.replace("_", " "))


def sorted_findings(findings: list[RuleFinding]) -> list[RuleFinding]:
    order = {RiskLevel.ALTO: 0, RiskLevel.MEDIO: 1, RiskLevel.BAIXO: 2}
    return sorted(findings, key=lambda finding: (order.get(finding.nivel, 9), -finding.pontuacao, finding.codigo))


def required(value: Any) -> str:
    text = str(value or "").strip()
    return text or VERIFY


def shorten(value: str, limit: int) -> str:
    text = clean_text(value)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def clean_text(value: str) -> str:
    return " ".join(str(value or "").split())


def client_safe_text(value: str) -> str:
    return (
        clean_text(value)
        .replace("possivel sinal de sonegacao fiscal", "risco de receita nao reconhecida ou tratamento fiscal pendente")
        .replace("possível sinal de sonegação fiscal", "risco de receita não reconhecida ou tratamento fiscal pendente")
        .replace("sonegacao fiscal", "risco fiscal")
        .replace("sonegação fiscal", "risco fiscal")
        .replace("omissao de receita", "receita possivelmente nao reconhecida")
        .replace("omissão de receita", "receita possivelmente não reconhecida")
        .replace("fraude", "irregularidade")
    )


def orientacao_por_opiniao(opinion: str) -> str:
    if opinion == "adversa":
        return "regularizar os achados relevantes antes de usar os dados para decisões externas ou fechamento anual"
    if opinion == "com_ressalva":
        return "corrigir, documentar e validar os pontos destacados antes do fechamento definitivo"
    if opinion == "abstencao_opiniao":
        return "obter documentação complementar antes de concluir a análise"
    return "manter a documentação suporte e acompanhar os controles nos próximos trimestres"


def area_relacionada(code: str) -> str:
    if code.startswith(("SN-001", "SN-002", "SN-008", "SN-012", "SN-017", "SN-019", "SN-020", "SN-024", "SN-026")):
        return "fiscal"
    if code.startswith(("SN-003", "SN-014")):
        return "trabalhista"
    if code.startswith(("SN-004", "SN-005")):
        return "societária"
    if code.startswith(("SN-006", "SN-010", "SN-011", "SN-016", "SN-022", "SN-023", "SN-028")):
        return "financeira"
    if code.startswith(("SN-007", "SN-009", "SN-013", "SN-015", "SN-018", "SN-021", "SN-027")):
        return "contábil"
    return "documental"


def normalize_normas(normas: tuple[str, ...]) -> list[str]:
    normalized: list[str] = []
    for norma in normas:
        label = NORMA_LABELS.get(norma, norma)
        if label:
            append_unique(normalized, label)
    return normalized


def append_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)


def format_evidence(evidence: dict[str, str]) -> str | None:
    if not evidence:
        return None
    text = "; ".join(f"{label(key)}: {value}" for key, value in evidence.items())
    return shorten(text, 320)


def label(value: str) -> str:
    labels = {
        "lucro_apurado": "Lucro apurado",
        "origem_lucro": "Origem do lucro",
        "lucro_disponivel_identificado": "Lucro disponível identificado",
        "lucros_distribuidos": "Lucros distribuídos",
        "saldo_contas_socios": "Saldo de contas de sócios",
        "percentual_receita": "Percentual sobre a receita",
        "limite_percentual_relevancia": "Limite percentual de relevância",
        "limite_absoluto_relevancia": "Limite absoluto de relevância",
        "limite_baixa_materialidade": "Limite de baixa materialidade",
        "classificacao_materialidade": "Classificação de materialidade",
        "codigos_monitorados": "Códigos monitorados",
        "contrato_mutuo": "Contrato de mútuo",
        "iof_recolhido": "IOF recolhido",
        "folha_pro_labore": "Folha e pró-labore",
        "percentual_folha": "Percentual da folha",
        "provisoes": "Provisões",
        "tributos_registrados": "Tributos registrados",
        "saldo_anterior_tributos": "Saldo anterior de tributos",
        "saldo_atual_tributos": "Saldo atual de tributos",
        "receita_trimestre": "Receita do trimestre",
        "receita_anualizada_estimativa": "Receita anualizada estimada",
        "receita_rbt12": "RBT12",
        "limite_anual_simples": "Limite anual do Simples Nacional",
        "percentual_limite_anual": "Percentual do limite anual",
        "base_calculo_limite": "Base de calculo do limite",
        "fator_r_trimestral_estimado": "Fator R trimestral estimado",
        "caixa_bancos": "Caixa e bancos",
        "clientes_recebiveis": "Clientes e recebíveis",
        "adiantamentos_clientes": "Adiantamentos de clientes",
        "saldo_final_clientes_recebiveis": "Saldo final de clientes e recebíveis",
        "movimentacao_clientes_trimestre": "Movimentação de clientes no trimestre",
        "percentual_sobre_receita_trimestral": "Percentual sobre a receita trimestral",
        "limite_calculado_percentual_receita": "Limite calculado pelo percentual da receita",
        "referencia_aplicada": "Referência aplicada",
        "estoques": "Estoques",
        "fornecedores": "Fornecedores",
        "cmv_custos": "CMV/custos",
        "creditos_fiscais": "Créditos fiscais",
        "percentual_cmv_receita": "Percentual do CMV sobre a receita",
        "percentual_sobre_receita": "Percentual sobre a receita",
        "sublimite_anual": "Sublimite anual",
        "receita_total": "Receita total",
        "receita_comercio_identificada": "Receita de comércio identificada",
        "receita_servicos_identificada": "Receita de serviços identificada",
        "receita_nao_segregada_estimativa": "Receita não segregada estimada",
        "margem_lucro": "Margem de lucro",
        "referencia_presuncao": "Referência de presunção",
        "caixa_fisico": "Caixa físico",
        "limite_caixa": "Limite de caixa",
        "limite_alto_caixa": "Limite alto de caixa",
        "receita_minima": "Receita mínima",
        "conta_referencia": "Conta de referencia",
        "servicos_terceiros": "Servicos de terceiros",
        "servicos_terceiros_total": "Servicos de terceiros total",
        "total_despesas": "Total de despesas",
        "despesas_operacionais_total": "Despesas operacionais total",
        "percentual_sobre_despesas": "Percentual sobre despesas",
        "limite_percentual_despesas": "Limite percentual sobre despesas",
        "quantidade_contas_identificadas": "Quantidade de contas identificadas",
        "contas_identificadas": "Contas identificadas",
        "baixa_liquidacao": "Baixa ou liquidacao",
        "validacao_documental": "Validacao documental",
        "criterio_rastreio": "Criterio de rastreio",
        "tipo_achado": "Tipo do achado",
        "limitacao_dados": "Limitacao dos dados",
    }
    return labels.get(value, value.replace("_", " ").capitalize())
