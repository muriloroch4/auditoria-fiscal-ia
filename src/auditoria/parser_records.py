from __future__ import annotations

import csv
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation
from io import StringIO

from .account_classifier import classify_group as _classify_group
from .dominio_parser import dominio_records
from .models import LedgerAccount, TrialBalance
from .parser_tables import detect_csv_delimiter, normalize_header

REQUIRED_COLUMNS = {
    "codigo",
    "conta",
    "grupo",
    "saldo_anterior",
    "debito",
    "credito",
    "saldo_atual",
}


def read_trial_balance_rows(rows: Iterable[str], cliente: str, periodo: str, cnpj: str = "") -> TrialBalance:
    content = "".join(list(rows))
    delimiter = detect_csv_delimiter(content)
    reader = csv.DictReader(StringIO(content), delimiter=delimiter)
    if not reader.fieldnames:
        raise ValueError("CSV vazio ou sem cabecalho.")

    headers = [normalize_header(field) for field in reader.fieldnames]
    missing = REQUIRED_COLUMNS.difference(headers)
    if missing:
        columns = ", ".join(sorted(missing))
        raise ValueError(f"CSV sem colunas obrigatorias: {columns}")

    records = [
        {normalize_header(key): value for key, value in row.items()}
        for row in reader
    ]
    return read_trial_balance_records(records, cliente=cliente, periodo=periodo, cnpj=cnpj, source_name="CSV")


def read_trial_balance_records(
    records: Iterable[dict[str, str]],
    cliente: str,
    periodo: str,
    cnpj: str,
    source_name: str,
) -> TrialBalance:
    normalized_records = list(records)
    if normalized_records:
        missing = REQUIRED_COLUMNS.difference(normalized_records[0].keys())
        if missing:
            columns = ", ".join(sorted(missing))
            raise ValueError(f"{source_name} sem colunas obrigatorias: {columns}")

    accounts = [
        row_to_account(row, line_number)
        for line_number, row in enumerate(normalized_records, start=2)
        if any((value or "").strip() for value in row.values())
    ]
    if not accounts:
        raise ValueError(f"{source_name} sem contas para analise.")

    return TrialBalance(cliente=cliente, periodo=periodo, contas=accounts, cnpj=cnpj)


def row_to_account(row: dict[str, str], line_number: int) -> LedgerAccount:
    codigo = required_text(row, "codigo", line_number)
    conta = required_text(row, "conta", line_number)
    grupo_original = required_text(row, "grupo", line_number).lower()
    grupo, origem, confianca, observacao = _classify_group(codigo, conta, grupo_original)

    return LedgerAccount(
        codigo=codigo,
        conta=conta,
        grupo=grupo,
        saldo_anterior=decimal_value(row["saldo_anterior"], "saldo_anterior", line_number),
        debito=decimal_value(row["debito"], "debito", line_number),
        credito=decimal_value(row["credito"], "credito", line_number),
        saldo_atual=decimal_value(row["saldo_atual"], "saldo_atual", line_number),
        grupo_original=grupo_original,
        classificacao_origem=origem,
        classificacao_confianca=confianca,
        classificacao_observacao=observacao,
    )


def required_text(row: dict[str, str], field: str, line_number: int) -> str:
    value = (row.get(field) or "").strip()
    if not value:
        raise ValueError(f"Linha {line_number}: campo obrigatorio vazio: {field}")
    return value


def decimal_value(value: str, field: str, line_number: int) -> Decimal:
    normalized = (value or "").strip()
    if not normalized:
        return Decimal("0")

    if "," in normalized:
        normalized = normalized.replace(".", "").replace(",", ".")
    else:
        normalized = normalized.replace(" ", "")

    try:
        return Decimal(normalized)
    except InvalidOperation as exc:
        raise ValueError(f"Linha {line_number}: valor invalido em {field}: {value}") from exc


def records_from_table_rows(table_rows: list[list[str]], source_name: str) -> list[dict[str, str]]:
    headers = [normalize_header(value) for value in table_rows[0]]
    missing = REQUIRED_COLUMNS.difference(headers)
    if missing:
        dominio_result = dominio_records(table_rows)
        if dominio_result is not None:
            return dominio_result
        columns = ", ".join(sorted(missing))
        raise ValueError(f"{source_name} sem colunas obrigatorias: {columns}")

    records: list[dict[str, str]] = []
    for row in table_rows[1:]:
        padded = row + [""] * (len(headers) - len(row))
        records.append(dict(zip(headers, padded)))

    return records
