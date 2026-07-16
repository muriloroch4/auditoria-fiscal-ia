from __future__ import annotations

import tempfile
from io import StringIO
from pathlib import Path

from .account_classifier import (
    VALID_GRUPOS,
    dominio_group as _dominio_group,
    normalize_key as _normalize_key,
)
from .dominio_parser import (
    CNPJ_RE as _CNPJ_RE,
    CODE_RE as _CODE_RE,
    DOM_COL_CODIGO as _DOM_COL_CODIGO,
    DOM_COL_CREDITO as _DOM_COL_CREDITO,
    DOM_COL_DEBITO as _DOM_COL_DEBITO,
    DOM_COL_DESCRICAO as _DOM_COL_DESCRICAO,
    DOM_COL_SALDO_ANTERIOR as _DOM_COL_SALDO_ANTERIOR,
    DOM_COL_SALDO_ATUAL as _DOM_COL_SALDO_ATUAL,
    DOM_LINHA_CNPJ as _DOM_LINHA_CNPJ,
    DOM_LINHA_DADOS as _DOM_LINHA_DADOS,
    DOM_LINHA_EMPRESA as _DOM_LINHA_EMPRESA,
    DOM_LINHA_HEADER as _DOM_LINHA_HEADER,
    DOM_LINHA_PERIODO as _DOM_LINHA_PERIODO,
    DOM_MIN_COLUNAS as _DOM_MIN_COLUNAS,
    DOM_MIN_SEGMENTOS_FOLHA as _DOM_MIN_SEGMENTOS_FOLHA,
    dominio_cell as _dominio_cell,
    dominio_decimal as _dominio_decimal,
    dominio_extract_metadata as _dominio_extract_metadata,
    dominio_header_index as _dominio_header_index,
    dominio_is_leaf as _dominio_is_leaf,
    dominio_records as _dominio_records,
    dominio_table_rows as _dominio_table_rows,
    find_dominio_header as _find_dominio_header,
    is_dominio_format,
    looks_like_periodo as _looks_like_periodo,
    parse_dominio_balancete,
)
from .models import TrialBalance
from .parser_records import (
    REQUIRED_COLUMNS,
    decimal_value as _decimal,
    read_trial_balance_records as _read_trial_balance_records,
    read_trial_balance_rows as _read_trial_balance_rows,
    records_from_table_rows as _records_from_table_rows,
    required_text as _required_text,
    row_to_account as _row_to_account,
)
from .parser_tables import (
    csv_table_rows as _csv_table_rows,
    detect_csv_delimiter as _detect_csv_delimiter,
    index_of as _index_of,
    normalize_header as _normalize_header,
    value_at as _value_at,
    xlsx_table_rows as _xlsx_table_rows,
)
from .xls_converter import convert_xls_to_xlsx as _convert_xls_to_xlsx


def read_trial_balance(path: str | Path, cliente: str, periodo: str, cnpj: str = "") -> TrialBalance:
    source = Path(path)
    suffix = source.suffix.lower()

    if suffix == ".csv":
        return read_trial_balance_csv(source, cliente=cliente, periodo=periodo, cnpj=cnpj)
    if suffix == ".xlsx":
        return read_trial_balance_xlsx(source, cliente=cliente, periodo=periodo, cnpj=cnpj)
    if suffix == ".xls":
        return read_trial_balance_xls_bytes(source.read_bytes(), cliente=cliente, periodo=periodo, cnpj=cnpj)

    raise ValueError("Formato nao suportado. Envie um arquivo .csv ou .xlsx.")


def read_trial_balance_upload(
    filename: str,
    content: bytes,
    cliente: str = "",
    periodo: str = "",
    cnpj: str = "",
) -> TrialBalance:
    suffix = Path(filename).suffix.lower()

    if suffix == ".csv":
        text = content.decode("utf-8-sig", errors="replace")
        table_rows = _csv_table_rows(text)
        if is_dominio_format(table_rows):
            return parse_dominio_balancete(
                content,
                filename=filename,
                cliente_override=cliente or None,
                periodo_override=periodo or None,
                cnpj_override=cnpj or None,
            )
        return read_trial_balance_csv_text(text, cliente=cliente, periodo=periodo, cnpj=cnpj)

    if suffix == ".xlsx":
        table_rows = _xlsx_table_rows(content)
        if is_dominio_format(table_rows):
            return parse_dominio_balancete(
                content,
                filename=filename,
                cliente_override=cliente or None,
                periodo_override=periodo or None,
                cnpj_override=cnpj or None,
            )
        return _read_trial_balance_records(
            _records_from_table_rows(table_rows, source_name="XLSX"),
            cliente=cliente,
            periodo=periodo,
            cnpj=cnpj,
            source_name="XLSX",
        )

    if suffix == ".xls":
        try:
            text = content.decode("utf-8-sig", errors="strict")
            table_rows = _csv_table_rows(text)
            if is_dominio_format(table_rows):
                return parse_dominio_balancete(
                    content,
                    filename=filename,
                    cliente_override=cliente or None,
                    periodo_override=periodo or None,
                    cnpj_override=cnpj or None,
                )
        except UnicodeDecodeError:
            pass
        return read_trial_balance_xls_bytes(content, cliente=cliente, periodo=periodo, cnpj=cnpj)

    raise ValueError("Formato nao suportado. Envie um arquivo .csv ou .xlsx.")


def read_trial_balance_csv(path: str | Path, cliente: str, periodo: str, cnpj: str = "") -> TrialBalance:
    source = Path(path)

    with source.open("r", encoding="utf-8-sig", newline="") as file:
        return _read_trial_balance_rows(file, cliente=cliente, periodo=periodo, cnpj=cnpj)


def read_trial_balance_csv_text(content: str, cliente: str, periodo: str, cnpj: str = "") -> TrialBalance:
    return _read_trial_balance_rows(StringIO(content), cliente=cliente, periodo=periodo, cnpj=cnpj)


def read_trial_balance_xlsx(path: str | Path, cliente: str, periodo: str, cnpj: str = "") -> TrialBalance:
    return read_trial_balance_xlsx_bytes(Path(path).read_bytes(), cliente=cliente, periodo=periodo, cnpj=cnpj)


def read_trial_balance_xlsx_bytes(content: bytes, cliente: str, periodo: str, cnpj: str = "") -> TrialBalance:
    records = _xlsx_records(content)
    return _read_trial_balance_records(records, cliente=cliente, periodo=periodo, cnpj=cnpj, source_name="XLSX")


def read_trial_balance_xls_bytes(content: bytes, cliente: str, periodo: str, cnpj: str = "") -> TrialBalance:
    with tempfile.TemporaryDirectory() as temp_dir:
        source = Path(temp_dir) / "balancete.xls"
        converted = Path(temp_dir) / "balancete.xlsx"
        source.write_bytes(content)
        _convert_xls_to_xlsx(source, converted)
        return read_trial_balance_xlsx(converted, cliente=cliente, periodo=periodo, cnpj=cnpj)


def _xlsx_records(content: bytes) -> list[dict[str, str]]:
    table_rows = _xlsx_table_rows(content)
    return _records_from_table_rows(table_rows, source_name="XLSX")
