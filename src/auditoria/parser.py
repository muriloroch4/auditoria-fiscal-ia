from __future__ import annotations

import csv
import subprocess
import tempfile
import unicodedata
import re
import zipfile
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation
from io import BytesIO, StringIO
from pathlib import Path
from xml.etree import ElementTree

from .models import LedgerAccount, TrialBalance


REQUIRED_COLUMNS = {
    "codigo",
    "conta",
    "grupo",
    "saldo_anterior",
    "debito",
    "credito",
    "saldo_atual",
}


def read_trial_balance(path: str | Path, cliente: str, periodo: str) -> TrialBalance:
    source = Path(path)
    suffix = source.suffix.lower()

    if suffix == ".csv":
        return read_trial_balance_csv(source, cliente=cliente, periodo=periodo)
    if suffix == ".xlsx":
        return read_trial_balance_xlsx(source, cliente=cliente, periodo=periodo)
    if suffix == ".xls":
        return read_trial_balance_xls_bytes(source.read_bytes(), cliente=cliente, periodo=periodo)

    raise ValueError("Formato nao suportado. Envie um arquivo .csv ou .xlsx.")


def read_trial_balance_upload(filename: str, content: bytes, cliente: str, periodo: str) -> TrialBalance:
    suffix = Path(filename).suffix.lower()

    if suffix == ".csv":
        text = content.decode("utf-8-sig", errors="replace")
        return read_trial_balance_csv_text(text, cliente=cliente, periodo=periodo)
    if suffix == ".xlsx":
        return read_trial_balance_xlsx_bytes(content, cliente=cliente, periodo=periodo)
    if suffix == ".xls":
        return read_trial_balance_xls_bytes(content, cliente=cliente, periodo=periodo)

    raise ValueError("Formato nao suportado. Envie um arquivo .csv ou .xlsx.")


def read_trial_balance_csv(path: str | Path, cliente: str, periodo: str) -> TrialBalance:
    source = Path(path)

    with source.open("r", encoding="utf-8-sig", newline="") as file:
        return _read_trial_balance_rows(file, cliente=cliente, periodo=periodo)


def read_trial_balance_csv_text(content: str, cliente: str, periodo: str) -> TrialBalance:
    return _read_trial_balance_rows(StringIO(content), cliente=cliente, periodo=periodo)


def read_trial_balance_xlsx(path: str | Path, cliente: str, periodo: str) -> TrialBalance:
    return read_trial_balance_xlsx_bytes(Path(path).read_bytes(), cliente=cliente, periodo=periodo)


def read_trial_balance_xlsx_bytes(content: bytes, cliente: str, periodo: str) -> TrialBalance:
    records = _xlsx_records(content)
    return _read_trial_balance_records(records, cliente=cliente, periodo=periodo, source_name="XLSX")


def read_trial_balance_xls_bytes(content: bytes, cliente: str, periodo: str) -> TrialBalance:
    with tempfile.TemporaryDirectory() as temp_dir:
        source = Path(temp_dir) / "balancete.xls"
        converted = Path(temp_dir) / "balancete.xlsx"
        source.write_bytes(content)
        _convert_xls_to_xlsx(source, converted)
        return read_trial_balance_xlsx(converted, cliente=cliente, periodo=periodo)


def _read_trial_balance_rows(rows: Iterable[str], cliente: str, periodo: str) -> TrialBalance:
    reader = csv.DictReader(rows, delimiter=";")
    if not reader.fieldnames:
        raise ValueError("CSV vazio ou sem cabecalho.")

    headers = [_normalize_header(field) for field in reader.fieldnames]
    missing = REQUIRED_COLUMNS.difference(headers)
    if missing:
        columns = ", ".join(sorted(missing))
        raise ValueError(f"CSV sem colunas obrigatorias: {columns}")

    records = [
        {_normalize_header(key): value for key, value in row.items()}
        for row in reader
    ]
    return _read_trial_balance_records(records, cliente=cliente, periodo=periodo, source_name="CSV")


def _read_trial_balance_records(
    records: Iterable[dict[str, str]],
    cliente: str,
    periodo: str,
    source_name: str,
) -> TrialBalance:
    normalized_records = list(records)
    if normalized_records:
        missing = REQUIRED_COLUMNS.difference(normalized_records[0].keys())
        if missing:
            columns = ", ".join(sorted(missing))
            raise ValueError(f"{source_name} sem colunas obrigatorias: {columns}")

    accounts = [
        _row_to_account(row, line_number)
        for line_number, row in enumerate(normalized_records, start=2)
        if any((value or "").strip() for value in row.values())
    ]
    if not accounts:
        raise ValueError(f"{source_name} sem contas para analise.")

    return TrialBalance(cliente=cliente, periodo=periodo, contas=accounts)


def _row_to_account(row: dict[str, str], line_number: int) -> LedgerAccount:
    return LedgerAccount(
        codigo=_required_text(row, "codigo", line_number),
        conta=_required_text(row, "conta", line_number),
        grupo=_required_text(row, "grupo", line_number).lower(),
        saldo_anterior=_decimal(row["saldo_anterior"], "saldo_anterior", line_number),
        debito=_decimal(row["debito"], "debito", line_number),
        credito=_decimal(row["credito"], "credito", line_number),
        saldo_atual=_decimal(row["saldo_atual"], "saldo_atual", line_number),
    )


def _required_text(row: dict[str, str], field: str, line_number: int) -> str:
    value = (row.get(field) or "").strip()
    if not value:
        raise ValueError(f"Linha {line_number}: campo obrigatorio vazio: {field}")
    return value


def _decimal(value: str, field: str, line_number: int) -> Decimal:
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


def _xlsx_records(content: bytes) -> list[dict[str, str]]:
    with zipfile.ZipFile(BytesIO(content)) as workbook:
        shared_strings = _read_shared_strings(workbook)
        sheet_path = _first_sheet_path(workbook)
        sheet_root = ElementTree.fromstring(workbook.read(sheet_path))

    namespace = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    table_rows: list[list[str]] = []

    for row in sheet_root.findall(".//main:sheetData/main:row", namespace):
        values: dict[int, str] = {}
        max_index = -1
        for cell in row.findall("main:c", namespace):
            col_index = _column_index(cell.attrib.get("r", ""))
            max_index = max(max_index, col_index)
            values[col_index] = _cell_value(cell, shared_strings)

        if max_index >= 0:
            table_rows.append([values.get(index, "") for index in range(max_index + 1)])

    table_rows = [row for row in table_rows if any(value.strip() for value in row)]
    if not table_rows:
        raise ValueError("XLSX vazio ou sem dados na primeira aba.")

    headers = [_normalize_header(value) for value in table_rows[0]]
    missing = REQUIRED_COLUMNS.difference(headers)
    if missing:
        dominio_records = _dominio_records(table_rows)
        if dominio_records is not None:
            return dominio_records
        columns = ", ".join(sorted(missing))
        raise ValueError(f"XLSX sem colunas obrigatorias: {columns}")

    records: list[dict[str, str]] = []
    for row in table_rows[1:]:
        padded = row + [""] * (len(headers) - len(row))
        records.append(dict(zip(headers, padded)))

    return records


def _dominio_records(table_rows: list[list[str]]) -> list[dict[str, str]] | None:
    header_index = _find_dominio_header(table_rows)
    if header_index is None:
        return None

    header = [_normalize_key(value) for value in table_rows[header_index]]
    column_map = {
        "codigo": _index_of(header, "codigo"),
        "classificacao": _index_of(header, "classificacao"),
        "conta": _index_of(header, "descricao da conta"),
        "saldo_anterior": _index_of(header, "saldo anterior"),
        "debito": _index_of(header, "debito"),
        "credito": _index_of(header, "credito"),
        "saldo_atual": _index_of(header, "saldo atual"),
    }
    if any(index is None for index in column_map.values()):
        return None

    raw_accounts = []
    for row in table_rows[header_index + 1:]:
        classification = _value_at(row, column_map["classificacao"])
        description = _value_at(row, column_map["conta"])
        if not classification or not description:
            continue
        if not re.match(r"^\d+(\.\d+)*$", classification):
            continue

        raw_accounts.append(
            {
                "codigo": _value_at(row, column_map["codigo"]),
                "classificacao": classification,
                "conta": description,
                "saldo_anterior": _value_at(row, column_map["saldo_anterior"]),
                "debito": _value_at(row, column_map["debito"]),
                "credito": _value_at(row, column_map["credito"]),
                "saldo_atual": _value_at(row, column_map["saldo_atual"]),
            }
        )

    leaf_accounts = [
        account
        for index, account in enumerate(raw_accounts)
        if not _has_child_account(account["classificacao"], raw_accounts[index + 1:])
    ]

    records = []
    for account in leaf_accounts:
        group = _dominio_group(account["classificacao"], account["conta"])
        if not group:
            continue
        records.append(
            {
                "codigo": account["codigo"],
                "conta": account["conta"],
                "grupo": group,
                "saldo_anterior": account["saldo_anterior"],
                "debito": account["debito"],
                "credito": account["credito"],
                "saldo_atual": account["saldo_atual"],
            }
        )

    return records


def _find_dominio_header(table_rows: list[list[str]]) -> int | None:
    for index, row in enumerate(table_rows):
        normalized = {_normalize_key(value) for value in row}
        if {"codigo", "classificacao", "descricao da conta", "saldo anterior", "debito", "credito", "saldo atual"}.issubset(normalized):
            return index
    return None


def _has_child_account(classification: str, following_accounts: list[dict[str, str]]) -> bool:
    prefix = f"{classification}."
    return any(account["classificacao"].startswith(prefix) for account in following_accounts)


def _dominio_group(classification: str, description: str) -> str:
    text = _normalize_key(description)

    if "lucros distribuidos" in text or "distribuicao antecipada de lucros" in text:
        return "lucros"
    if "socio" in text or "socios" in text or "administradores" in text:
        return "socios"
    if classification.startswith("1.1.1.01") or "caixa" in text:
        return "caixa"
    if classification.startswith("1.1.1.02") or text.startswith("banco "):
        return "bancos"
    if classification.startswith("1.1.2") or "duplicatas a receber" in text or "cliente" in text:
        return "clientes"
    if classification.startswith("3.1.1") or "receita de prestacao" in text:
        return "receita"
    if classification.startswith("3.1.2.03"):
        return "tributos"
    if classification.startswith("4.2.2.01") or (
        classification.startswith("4") and ("pro-labore" in text or "salarios" in text or "fgts" in text)
    ):
        return "folha"
    if classification.startswith("4"):
        return "despesas"

    return "outros"


def _convert_xls_to_xlsx(source: Path, converted: Path) -> None:
    script = f"""
$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false
$excel.DisplayAlerts = $false
$excel.AutomationSecurity = 3
$workbook = $excel.Workbooks.Open('{_ps_escape(source)}', 0, $true)
try {{
    $workbook.SaveAs('{_ps_escape(converted)}', 51)
}} finally {{
    if ($workbook) {{ $workbook.Close($false) }}
    if ($excel) {{ $excel.Quit() }}
}}
"""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0 or not converted.exists():
        raise ValueError(
            "Nao foi possivel converter o .xls automaticamente. "
            "Salve o arquivo como .xlsx no Excel e tente novamente."
        )


def _read_shared_strings(workbook: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in workbook.namelist():
        return []

    namespace = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    root = ElementTree.fromstring(workbook.read("xl/sharedStrings.xml"))
    strings = []

    for item in root.findall("main:si", namespace):
        parts = [text.text or "" for text in item.findall(".//main:t", namespace)]
        strings.append("".join(parts))

    return strings


def _first_sheet_path(workbook: zipfile.ZipFile) -> str:
    main_ns = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    rel_ns = {"rel": "http://schemas.openxmlformats.org/package/2006/relationships"}
    relationship_attr = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"

    workbook_root = ElementTree.fromstring(workbook.read("xl/workbook.xml"))
    first_sheet = workbook_root.find("main:sheets/main:sheet", main_ns)
    if first_sheet is None:
        raise ValueError("XLSX sem abas.")

    relationship_id = first_sheet.attrib.get(relationship_attr)
    relationships_root = ElementTree.fromstring(workbook.read("xl/_rels/workbook.xml.rels"))
    for relationship in relationships_root.findall("rel:Relationship", rel_ns):
        if relationship.attrib.get("Id") == relationship_id:
            target = relationship.attrib["Target"].lstrip("/")
            return target if target.startswith("xl/") else f"xl/{target}"

    raise ValueError("Nao foi possivel localizar a primeira aba do XLSX.")


def _cell_value(cell: ElementTree.Element, shared_strings: list[str]) -> str:
    namespace = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    cell_type = cell.attrib.get("t")

    if cell_type == "inlineStr":
        parts = [text.text or "" for text in cell.findall(".//main:t", namespace)]
        return "".join(parts).strip()

    value_node = cell.find("main:v", namespace)
    if value_node is None or value_node.text is None:
        return ""

    value = value_node.text.strip()
    if cell_type == "s":
        index = int(value)
        return shared_strings[index].strip() if index < len(shared_strings) else ""
    if cell_type == "b":
        return "1" if value == "1" else "0"

    return value


def _column_index(cell_ref: str) -> int:
    match = re.match(r"([A-Z]+)", cell_ref.upper())
    if not match:
        return 0

    index = 0
    for char in match.group(1):
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index - 1


def _normalize_header(value: str | None) -> str:
    return (value or "").strip().lower()


def _normalize_key(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.strip().lower().split())


def _index_of(values: list[str], wanted: str) -> int | None:
    try:
        return values.index(wanted)
    except ValueError:
        return None


def _value_at(row: list[str], index: int | None) -> str:
    if index is None or index >= len(row):
        return ""
    return row[index]


def _ps_escape(path: Path) -> str:
    return str(path).replace("'", "''")
