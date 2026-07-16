from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from .account_classifier import (
    classify_dominio_group as _dominio_group_classification,
    dominio_group as _dominio_group,
    normalize_key as _normalize_key,
)
from .models import LedgerAccount, TrialBalance
from .parser_tables import csv_table_rows, index_of, value_at, xlsx_table_rows

DOM_COL_CODIGO = 1
DOM_COL_DESCRICAO = 3
DOM_COL_SALDO_ANTERIOR = 7
DOM_COL_DEBITO = 9
DOM_COL_CREDITO = 11
DOM_COL_SALDO_ATUAL = 13
DOM_LINHA_EMPRESA = 0
DOM_LINHA_CNPJ = 1
DOM_LINHA_PERIODO = 2
DOM_LINHA_HEADER = 6
DOM_LINHA_DADOS = 7
DOM_MIN_COLUNAS = 14
DOM_MIN_SEGMENTOS_FOLHA = 5
CNPJ_RE = re.compile(r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}")
CODE_RE = re.compile(r"^\d+(?:\.\d+)*$")


def is_dominio_format(table_rows: list[list[str]]) -> bool:
    try:
        if len(table_rows) <= DOM_LINHA_HEADER:
            return False
        if max((len(row) for row in table_rows), default=0) < DOM_MIN_COLUNAS:
            return False

        empresa = dominio_cell(table_rows, DOM_LINHA_EMPRESA, 1)
        cnpj = dominio_cell(table_rows, DOM_LINHA_CNPJ, 1)
        periodo = dominio_cell(table_rows, DOM_LINHA_PERIODO, 1)
        header_index = dominio_header_index(table_rows)

        if _normalize_key(empresa) in ("", "nan", "none"):
            return False
        if not CNPJ_RE.search(cnpj):
            return False
        if not looks_like_periodo(periodo):
            return False
        if header_index is None:
            return False
        return True
    except (IndexError, KeyError, TypeError):
        return False


def dominio_extract_metadata(table_rows: list[list[str]]) -> dict[str, str]:
    return {
        "cliente": dominio_cell(table_rows, DOM_LINHA_EMPRESA, 1).strip(),
        "cnpj": dominio_cell(table_rows, DOM_LINHA_CNPJ, 1).strip(),
        "periodo": dominio_cell(table_rows, DOM_LINHA_PERIODO, 1).strip(),
    }


def dominio_is_leaf(codigo: str) -> bool:
    codigo = (codigo or "").strip()
    if not CODE_RE.match(codigo):
        return False
    return len(codigo.split(".")) >= DOM_MIN_SEGMENTOS_FOLHA


def parse_dominio_balancete(
    content: bytes,
    filename: str = "balancete",
    *,
    cliente_override: str | None = None,
    periodo_override: str | None = None,
    cnpj_override: str | None = None,
) -> TrialBalance:
    table_rows = dominio_table_rows(content, filename)
    if not is_dominio_format(table_rows):
        raise ValueError(f"O arquivo '{filename}' nao foi reconhecido como balancete Dominio.")

    metadata = dominio_extract_metadata(table_rows)
    contas: list[LedgerAccount] = []

    header_index = dominio_header_index(table_rows)
    data_start = (header_index + 1) if header_index is not None else DOM_LINHA_DADOS

    for row in table_rows[data_start:]:
        codigo = value_at(row, DOM_COL_CODIGO).strip()
        descricao = value_at(row, DOM_COL_DESCRICAO).strip()
        if not codigo or not descricao or not dominio_is_leaf(codigo):
            continue

        grupo, origem, confianca, observacao = _dominio_group_classification(codigo, descricao)
        contas.append(
            LedgerAccount(
                codigo=codigo,
                conta=descricao,
                grupo=grupo,
                saldo_anterior=dominio_decimal(value_at(row, DOM_COL_SALDO_ANTERIOR)),
                debito=dominio_decimal(value_at(row, DOM_COL_DEBITO)),
                credito=dominio_decimal(value_at(row, DOM_COL_CREDITO)),
                saldo_atual=dominio_decimal(value_at(row, DOM_COL_SALDO_ATUAL)),
                grupo_original="",
                classificacao_origem=origem,
                classificacao_confianca=confianca,
                classificacao_observacao=observacao,
            )
        )

    if not contas:
        raise ValueError(
            f"Nenhuma conta folha encontrada em '{filename}'. "
            f"Esperado codigo com {DOM_MIN_SEGMENTOS_FOLHA}+ segmentos."
        )

    return TrialBalance(
        cliente=cliente_override or metadata["cliente"],
        periodo=periodo_override or metadata["periodo"],
        cnpj=cnpj_override or metadata["cnpj"],
        contas=contas,
    )


def dominio_table_rows(content: bytes, filename: str) -> list[list[str]]:
    suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if suffix in (".xlsx", ".xlsm"):
        return xlsx_table_rows(content)

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1", errors="replace")
    return csv_table_rows(text)


def dominio_cell(rows: list[list[str]], row: int, col: int) -> str:
    if row >= len(rows) or col >= len(rows[row]):
        return ""
    value = rows[row][col]
    return "" if value is None else str(value)


def looks_like_periodo(value: str) -> bool:
    text = _normalize_key(value)
    if re.search(r"\d{2}/\d{2}/\d{4}", value):
        return True
    return bool(re.search(r"(q[1-4]|[1-4]\s*(?:o|º|°)?\s*trim|jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez).{0,20}20\d{2}", text))


def dominio_header_index(table_rows: list[list[str]]) -> int | None:
    fixed_codigo = _normalize_key(dominio_cell(table_rows, DOM_LINHA_HEADER, DOM_COL_CODIGO))
    fixed_descricao = _normalize_key(dominio_cell(table_rows, DOM_LINHA_HEADER, DOM_COL_DESCRICAO))
    if "classifica" in fixed_codigo and "descri" in fixed_descricao:
        return DOM_LINHA_HEADER
    return find_dominio_header(table_rows)


def dominio_decimal(value: str) -> Decimal:
    normalized = (value or "").strip().replace("\u2212", "-")
    if not normalized or _normalize_key(normalized) in ("nan", "none"):
        return Decimal("0")
    if "," in normalized:
        normalized = normalized.replace(".", "").replace(",", ".")
    normalized = normalized.replace(" ", "")
    try:
        return Decimal(normalized)
    except InvalidOperation as exc:
        raise ValueError(f"Valor numerico invalido no balancete Dominio: {value}") from exc


def dominio_records(table_rows: list[list[str]]) -> list[dict[str, str]] | None:
    header_index = find_dominio_header(table_rows)
    if header_index is None:
        return None

    header = [_normalize_key(value) for value in table_rows[header_index]]
    column_map = {
        "codigo": index_of(header, "codigo"),
        "classificacao": index_of(header, "classificacao"),
        "conta": index_of(header, "descricao da conta"),
        "saldo_anterior": index_of(header, "saldo anterior"),
        "debito": index_of(header, "debito"),
        "credito": index_of(header, "credito"),
        "saldo_atual": index_of(header, "saldo atual"),
    }
    if any(index is None for index in column_map.values()):
        return None

    raw_accounts = []
    for row in table_rows[header_index + 1:]:
        classification = value_at(row, column_map["classificacao"])
        description = value_at(row, column_map["conta"])
        if not classification or not description:
            continue
        if not re.match(r"^\d+(\.\d+)*$", classification):
            continue

        raw_accounts.append(
            {
                "codigo": value_at(row, column_map["codigo"]),
                "classificacao": classification,
                "conta": description,
                "saldo_anterior": value_at(row, column_map["saldo_anterior"]),
                "debito": value_at(row, column_map["debito"]),
                "credito": value_at(row, column_map["credito"]),
                "saldo_atual": value_at(row, column_map["saldo_atual"]),
            }
        )

    leaf_accounts = [
        account
        for account in raw_accounts
        if dominio_is_leaf(account["classificacao"])
    ]

    records = []
    for account in leaf_accounts:
        group = _dominio_group(account["classificacao"], account["conta"])
        if not group:
            continue
        records.append(
            {
                "codigo": account["classificacao"],
                "conta": account["conta"],
                "grupo": group,
                "saldo_anterior": account["saldo_anterior"],
                "debito": account["debito"],
                "credito": account["credito"],
                "saldo_atual": account["saldo_atual"],
            }
        )

    return records


def find_dominio_header(table_rows: list[list[str]]) -> int | None:
    for index, row in enumerate(table_rows):
        normalized = {_normalize_key(value) for value in row}
        if {"codigo", "classificacao", "descricao da conta", "saldo anterior", "debito", "credito", "saldo atual"}.issubset(normalized):
            return index
    return None
