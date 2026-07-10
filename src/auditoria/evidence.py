from __future__ import annotations

from typing import Any

from .models import RiskLevel, RuleFinding


BALANCETE_SOURCE = "balancete_contabil"

_DOCUMENTS_BY_PREFIX: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("SN-001", ("PGDAS-D", "receita bruta acumulada dos ultimos 12 meses", "relatorio de faturamento por competencia")),
    ("SN-002", ("PGDAS-D", "DAS apurado e pago", "livro fiscal de receitas")),
    ("SN-003", ("folha de pagamento", "pro-labore", "eSocial", "PGDAS-D para calculo oficial do Fator R")),
    ("SN-004", ("balancete de verificacao", "razao contabil de lucros", "ata/contrato de distribuicao de lucros")),
    ("SN-005", ("razao das contas de socios", "extratos bancarios", "contrato de mutuo ou instrumento equivalente", "memoria de calculo do IOF", "guia e comprovante de recolhimento do IOF")),
    ("SN-006", ("extratos bancarios", "conciliacao bancaria", "boletim de caixa")),
    ("SN-007", ("razao das despesas", "notas fiscais de servicos tomados", "contratos e comprovantes de pagamento")),
    ("SN-008", ("notas fiscais emitidas", "extratos bancarios", "relatorio de recebimentos")),
    ("SN-009", ("balancete de verificacao", "DRE", "memoria de apropriacao de custos e despesas")),
    ("SN-010", ("razao de clientes", "relatorio de contas a receber", "baixas e comprovantes de recebimento")),
    ("SN-011", ("contratos", "notas fiscais", "razao de adiantamentos", "comprovantes de baixa")),
    ("SN-012", ("guias de tributos", "parcelamentos", "extratos fiscais", "DAS pago")),
    ("SN-013", ("notas fiscais de despesas", "politica de reembolso", "comprovantes de pagamento")),
    ("SN-014", ("folha de pagamento", "provisoes trabalhistas", "eSocial", "relatorio de ferias e 13o salario")),
    ("SN-015", ("inventario de estoque", "notas fiscais de compra e venda", "relatorio de giro de estoque")),
    ("SN-016", ("razao de fornecedores", "duplicatas", "notas fiscais de compra", "pagamentos subsequentes")),
    ("SN-017", ("composicao de creditos fiscais", "documentos fiscais", "memoria de recuperabilidade")),
    ("SN-018", ("memoria de CMV", "inventario", "notas fiscais de compra", "criterio de custo medio")),
    ("SN-019", ("PGDAS-D", "receita acumulada por UF", "apuracao de ICMS/ISS fora do DAS quando aplicavel")),
    ("SN-020", ("relatorio de receitas por natureza", "NFS-e", "NF-e", "PGDAS-D segregado por anexo")),
    ("SN-021", ("DRE", "razao de custos e despesas", "documentos de apropriacao por competencia")),
    ("SN-022", ("boletim de caixa", "comprovantes de entradas e saidas", "conciliacao com bancos")),
    ("SN-023", ("relatorio de contas a receber", "comprovantes de recebimento", "meios de pagamento")),
    ("SN-024", ("NF-e por NCM/CFOP/CST", "PGDAS-D", "memoria de ICMS-ST e ressarcimentos")),
    ("SN-025", ("contratos de prestadores", "notas fiscais de servicos tomados", "comprovantes bancarios", "retencoes aplicaveis")),
    ("AN-DOC-325", ("contratos de prestadores", "notas fiscais de servicos tomados", "comprovantes bancarios", "retencoes aplicaveis")),
    ("AN-DOC-MUTUO", ("razao das contas de socios", "extratos bancarios", "contrato de mutuo ou instrumento equivalente", "memoria de calculo do IOF", "guia e comprovante de recolhimento do IOF")),
    ("AN-COM", ("inventario de estoque", "notas fiscais de compra e venda", "memoria de CMV", "PGDAS-D quando aplicavel")),
    ("AN-", ("JSONs trimestrais consolidados", "balancetes trimestrais", "documentos de suporte dos achados recorrentes")),
)


def structured_finding_evidence(finding: RuleFinding) -> dict[str, Any]:
    return structured_evidence(
        finding.codigo,
        finding.evidencia,
        severity=finding.nivel.value,
        source=BALANCETE_SOURCE,
    )


def structured_evidence(
    code: str,
    extracted_fields: dict[str, Any] | None = None,
    *,
    severity: str | None = None,
    source: str = BALANCETE_SOURCE,
) -> dict[str, Any]:
    normalized_code = str(code or "")
    return {
        "fonte_dado": source,
        "confianca": _confidence(normalized_code, severity),
        "necessita_documento": True,
        "documentos_recomendados": list(_documents_for_code(normalized_code)),
        "campos_extraidos": {str(key): value for key, value in (extracted_fields or {}).items()},
    }


def _confidence(code: str, severity: str | None) -> str:
    if code.startswith(("SN-COMP", "AN-REC")):
        return "media"
    if code.startswith(("SN-003", "SN-017", "SN-019", "SN-020", "SN-024")):
        return "baixa"
    if severity == RiskLevel.ALTO.value:
        return "media"
    return "media"


def _documents_for_code(code: str) -> tuple[str, ...]:
    for prefix, documents in _DOCUMENTS_BY_PREFIX:
        if code.startswith(prefix):
            return documents
    return ("balancete de verificacao", "razao contabil", "documentos de suporte dos lancamentos")
