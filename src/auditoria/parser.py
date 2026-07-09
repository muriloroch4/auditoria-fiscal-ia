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

from .config_loader import load_account_map
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

VALID_GRUPOS = frozenset({
    "receita", "despesas", "tributos", "folha", "clientes", "fornecedores",
    "bancos", "caixa", "socios", "adiantamentos", "lucros", "resultado",
    "provisoes", "imobilizado", "despesas_representacao", "despesas_veiculos",
    "custos", "investimentos", "patrimonio_liquido", "patrimonio", "estoque",
    "estoques", "creditos_fiscais", "adiantamentos_clientes", "emprestimos",
    "tributos_a_recolher", "tributos_sobre_receita", "despesas_tributarias",
    "multas_fiscais", "outros",
})

_DOM_COL_CODIGO = 1
_DOM_COL_DESCRICAO = 3
_DOM_COL_SALDO_ANTERIOR = 7
_DOM_COL_DEBITO = 9
_DOM_COL_CREDITO = 11
_DOM_COL_SALDO_ATUAL = 13
_DOM_LINHA_EMPRESA = 0
_DOM_LINHA_CNPJ = 1
_DOM_LINHA_PERIODO = 2
_DOM_LINHA_HEADER = 6
_DOM_LINHA_DADOS = 7
_DOM_MIN_COLUNAS = 14
_DOM_MIN_SEGMENTOS_FOLHA = 5
_CNPJ_RE = re.compile(r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}")
_CODE_RE = re.compile(r"^\d+(?:\.\d+)*$")


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


def _read_trial_balance_rows(rows: Iterable[str], cliente: str, periodo: str, cnpj: str = "") -> TrialBalance:
    content = "".join(list(rows))
    delimiter = _detect_csv_delimiter(content)
    reader = csv.DictReader(StringIO(content), delimiter=delimiter)
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
    return _read_trial_balance_records(records, cliente=cliente, periodo=periodo, cnpj=cnpj, source_name="CSV")


def _detect_csv_delimiter(content: str) -> str:
    first_line = content.splitlines()[0] if content else ""
    candidates = [";", ",", "\t", "|"]
    counts = {d: first_line.count(d) for d in candidates}
    best = max(counts, key=lambda delimiter: counts[delimiter])
    return best if counts[best] > 0 else ";"


def _read_trial_balance_records(
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
        _row_to_account(row, line_number)
        for line_number, row in enumerate(normalized_records, start=2)
        if any((value or "").strip() for value in row.values())
    ]
    if not accounts:
        raise ValueError(f"{source_name} sem contas para analise.")

    return TrialBalance(cliente=cliente, periodo=periodo, contas=accounts, cnpj=cnpj)


def _row_to_account(row: dict[str, str], line_number: int) -> LedgerAccount:
    codigo = _required_text(row, "codigo", line_number)
    conta = _required_text(row, "conta", line_number)
    grupo = _required_text(row, "grupo", line_number).lower()
    mapped_by_code = _mapped_grupo_from_config(codigo, conta, allow_description=False)
    inferred = _infer_grupo_from_conta(codigo, conta)
    mapped_by_description = _mapped_grupo_from_config(codigo, conta, allow_description=True)
    mapped_group = inferred or mapped_by_code or mapped_by_description

    if grupo not in VALID_GRUPOS:
        grupo = mapped_group or "outros"
    elif grupo == "outros" and mapped_group:
        grupo = mapped_group

    return LedgerAccount(
        codigo=codigo,
        conta=conta,
        grupo=grupo,
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
    table_rows = _xlsx_table_rows(content)
    return _records_from_table_rows(table_rows, source_name="XLSX")


def _xlsx_table_rows(content: bytes) -> list[list[str]]:
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

    return table_rows


def _records_from_table_rows(table_rows: list[list[str]], source_name: str) -> list[dict[str, str]]:
    headers = [_normalize_header(value) for value in table_rows[0]]
    missing = REQUIRED_COLUMNS.difference(headers)
    if missing:
        dominio_records = _dominio_records(table_rows)
        if dominio_records is not None:
            return dominio_records
        columns = ", ".join(sorted(missing))
        raise ValueError(f"{source_name} sem colunas obrigatorias: {columns}")

    records: list[dict[str, str]] = []
    for row in table_rows[1:]:
        padded = row + [""] * (len(headers) - len(row))
        records.append(dict(zip(headers, padded)))

    return records


def _csv_table_rows(content: str) -> list[list[str]]:
    delimiter = _detect_csv_delimiter(content)
    return [row for row in csv.reader(StringIO(content), delimiter=delimiter)]


def is_dominio_format(table_rows: list[list[str]]) -> bool:
    try:
        if len(table_rows) <= _DOM_LINHA_HEADER:
            return False
        if max((len(row) for row in table_rows), default=0) < _DOM_MIN_COLUNAS:
            return False

        empresa = _dominio_cell(table_rows, _DOM_LINHA_EMPRESA, 1)
        cnpj = _dominio_cell(table_rows, _DOM_LINHA_CNPJ, 1)
        periodo = _dominio_cell(table_rows, _DOM_LINHA_PERIODO, 1)
        header_index = _dominio_header_index(table_rows)

        if _normalize_key(empresa) in ("", "nan", "none"):
            return False
        if not _CNPJ_RE.search(cnpj):
            return False
        if not _looks_like_periodo(periodo):
            return False
        if header_index is None:
            return False
        return True
    except (IndexError, KeyError, TypeError):
        return False


def _dominio_extract_metadata(table_rows: list[list[str]]) -> dict[str, str]:
    return {
        "cliente": _dominio_cell(table_rows, _DOM_LINHA_EMPRESA, 1).strip(),
        "cnpj": _dominio_cell(table_rows, _DOM_LINHA_CNPJ, 1).strip(),
        "periodo": _dominio_cell(table_rows, _DOM_LINHA_PERIODO, 1).strip(),
    }


def _dominio_is_leaf(codigo: str) -> bool:
    codigo = (codigo or "").strip()
    if not _CODE_RE.match(codigo):
        return False
    return len(codigo.split(".")) >= _DOM_MIN_SEGMENTOS_FOLHA


def parse_dominio_balancete(
    content: bytes,
    filename: str = "balancete",
    *,
    cliente_override: str | None = None,
    periodo_override: str | None = None,
    cnpj_override: str | None = None,
) -> TrialBalance:
    table_rows = _dominio_table_rows(content, filename)
    if not is_dominio_format(table_rows):
        raise ValueError(f"O arquivo '{filename}' nao foi reconhecido como balancete Dominio.")

    metadata = _dominio_extract_metadata(table_rows)
    contas: list[LedgerAccount] = []

    header_index = _dominio_header_index(table_rows)
    data_start = (header_index + 1) if header_index is not None else _DOM_LINHA_DADOS

    for row in table_rows[data_start:]:
        codigo = _value_at(row, _DOM_COL_CODIGO).strip()
        descricao = _value_at(row, _DOM_COL_DESCRICAO).strip()
        if not codigo or not descricao or not _dominio_is_leaf(codigo):
            continue

        contas.append(
            LedgerAccount(
                codigo=codigo,
                conta=descricao,
                grupo=_dominio_group(codigo, descricao),
                saldo_anterior=_dominio_decimal(_value_at(row, _DOM_COL_SALDO_ANTERIOR)),
                debito=_dominio_decimal(_value_at(row, _DOM_COL_DEBITO)),
                credito=_dominio_decimal(_value_at(row, _DOM_COL_CREDITO)),
                saldo_atual=_dominio_decimal(_value_at(row, _DOM_COL_SALDO_ATUAL)),
            )
        )

    if not contas:
        raise ValueError(
            f"Nenhuma conta folha encontrada em '{filename}'. "
            f"Esperado codigo com {_DOM_MIN_SEGMENTOS_FOLHA}+ segmentos."
        )

    return TrialBalance(
        cliente=cliente_override or metadata["cliente"],
        periodo=periodo_override or metadata["periodo"],
        cnpj=cnpj_override or metadata["cnpj"],
        contas=contas,
    )


def _dominio_table_rows(content: bytes, filename: str) -> list[list[str]]:
    suffix = Path(filename).suffix.lower()
    if suffix in (".xlsx", ".xlsm"):
        return _xlsx_table_rows(content)

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1", errors="replace")
    return _csv_table_rows(text)


def _dominio_cell(rows: list[list[str]], row: int, col: int) -> str:
    if row >= len(rows) or col >= len(rows[row]):
        return ""
    value = rows[row][col]
    return "" if value is None else str(value)


def _looks_like_periodo(value: str) -> bool:
    text = _normalize_key(value)
    if re.search(r"\d{2}/\d{2}/\d{4}", value):
        return True
    return bool(re.search(r"(q[1-4]|[1-4]\s*(?:o|º|°)?\s*trim|jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez).{0,20}20\d{2}", text))


def _dominio_header_index(table_rows: list[list[str]]) -> int | None:
    fixed_codigo = _normalize_key(_dominio_cell(table_rows, _DOM_LINHA_HEADER, _DOM_COL_CODIGO))
    fixed_descricao = _normalize_key(_dominio_cell(table_rows, _DOM_LINHA_HEADER, _DOM_COL_DESCRICAO))
    if "classifica" in fixed_codigo and "descri" in fixed_descricao:
        return _DOM_LINHA_HEADER
    return _find_dominio_header(table_rows)


def _dominio_decimal(value: str) -> Decimal:
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
        for account in raw_accounts
        if _dominio_is_leaf(account["classificacao"])
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
    c = (classification or "").strip()
    text = _normalize_key(description)
    mapped_group = _mapped_grupo_from_config(c, description, allow_description=False)
    if mapped_group:
        return mapped_group

    if "lucros distribuidos" in text or "distribuicao antecipada de lucros" in text:
        return "lucros"

    if c.startswith("1.1.1"):
        if any(k in text for k in ("cliente", "duplicata", "receber")):
            return "clientes"
        if any(k in text for k in ("banco", "conta corrente", "aplicacao", "poupanca", "cdb", "lci", "lca", "rdbi", "fundo", "tesouro")):
            return "bancos"
        return "caixa"
    if c.startswith("1.1.2"):
        if any(k in text for k in ("caixa", "banco", "conta corrente", "aplicacao", "poupanca")):
            return "bancos"
        return "clientes"
    if c.startswith("1.1.3"):
        if c.startswith("1.1.3.01"):
            return "bancos"
        if c.startswith(("1.1.3.02", "1.1.3.03")):
            return "clientes"
        if any(k in text for k in ("adiantamento", "adiantamentos")):
            return "adiantamentos"
        if any(k in text for k in ("recuperar", "compensar", "credito", "inss", "pis", "cofins", "irrf", "csll", "icms", "iss")):
            return "creditos_fiscais"
        return "outros"
    if c.startswith("1.1.40"):
        return "estoques"
    if c.startswith("1.1.4"):
        if "lucro" in text:
            return "lucros"
        return "investimentos"
    if c.startswith("1.1.5"):
        return "estoques"
    if c.startswith(("1.1.6", "1.1.7", "1.1.8", "1.1.9")):
        return "outros"

    if c.startswith("1.1.10.1"):
        if any(k in text for k in ("banco", "conta corrente", "aplicacao", "poupanca", "cdb", "lci", "lca", "rdbi", "fundo", "tesouro")):
            return "bancos"
        return "caixa"
    if c.startswith("1.1.10.2"):
        if any(k in text for k in ("caixa", "fundo fixo", "pequena caixa")):
            return "caixa"
        return "bancos"
    if c.startswith("1.1.10"):
        return "bancos"
    if c.startswith("1.1.20"):
        return "clientes"
    if c.startswith("1.1.30.5"):
        return "adiantamentos"
    if c.startswith("1.1.30.8"):
        return "creditos_fiscais"
    if c.startswith("1.1.30.9"):
        return "outros"
    if c.startswith("1.1.30"):
        parts = c.split(".")
        sub = parts[3] if len(parts) > 3 else ""
        if sub.startswith("5"):
            return "adiantamentos"
        if sub.startswith("8"):
            return "creditos_fiscais"
        return "outros"
    if c.startswith("1.1"):
        return "outros"

    if c.startswith("1.2.10"):
        return "outros"
    if c.startswith("1.2.20"):
        return "patrimonio"
    if c.startswith(("1.2.30", "1.2.40")):
        return "imobilizado"
    if c.startswith("1.2.1"):
        if "cliente" in text or "duplicata" in text or "receber" in text:
            return "clientes"
        return "outros"
    if c.startswith("1.2.2"):
        if "banco" in text or "aplicacao" in text:
            return "bancos"
        if any(k in text for k in ("tributo", "recuperar", "compensar", "credito", "inss", "pis", "cofins", "irrf", "csll", "icms", "iss")):
            return "creditos_fiscais"
        return "outros"
    if c.startswith("1.2.3"):
        return "investimentos"
    if c.startswith(("1.2.4", "1.2.5")):
        return "imobilizado"
    if c.startswith("1.2.6"):
        return "outros"
    if c.startswith(("1.3.3", "1.3")):
        return "outros"
    if c.startswith(("1.2.30", "1.2.40", "1.2")):
        return "imobilizado"

    if c.startswith("2.1.10"):
        return "fornecedores"
    if c.startswith("2.1.20"):
        return "folha"
    if c.startswith("2.1.70"):
        return "provisoes"
    if c.startswith("2.1.1"):
        return "emprestimos"
    if c.startswith("2.1.2"):
        return "emprestimos"
    if c.startswith("2.1.3"):
        return "fornecedores"
    if c.startswith("2.1.4"):
        return "tributos_a_recolher"
    if c.startswith("2.1.5"):
        if c.startswith(("2.1.5.04", "2.1.5.05", "2.1.5.06")):
            return "tributos_a_recolher"
        if c.startswith("2.1.5.03"):
            return "provisoes"
        if any(k in text for k in ("inss", "fgts", "previdencia", "contribuicao social", "imposto", "tributo", "simples", "irrf", "iss", "pis", "cofins")):
            return "tributos_a_recolher"
        if any(k in text for k in ("salario", "ordenado", "pro-labore", "rescis", "ferias", "13")):
            return "folha"
        return "folha"
    if c.startswith("2.1.6"):
        if c.startswith("2.1.6.01") or any(k in text for k in ("adiantamento de cliente", "adiantamentos de clientes", "cliente")):
            return "adiantamentos_clientes"
        if any(k in text for k in ("socio", "administrador", "pessoa ligada", "mutuo")):
            return "socios"
        return "outros"
    if c.startswith("2.1.7"):
        return "lucros"
    if c.startswith(("2.1.30", "2.1.40")):
        return "tributos_a_recolher"
    if c.startswith("2.1.50.1"):
        return "folha"
    if c.startswith("2.1.50.2"):
        return "tributos_a_recolher"
    if c.startswith("2.1.50"):
        if any(k in text for k in ("inss", "fgts", "previdencia", "contribuicao social")):
            return "tributos_a_recolher"
        if any(k in text for k in ("salario", "ordenado", "pro-labore", "rescis", "ferias", "13")):
            return "folha"
        return "folha"
    if c.startswith("2.1.60.1"):
        return "adiantamentos_clientes"
    if c.startswith("2.1.60.6"):
        return "socios"
    if c.startswith("2.1.60"):
        if any(k in text for k in ("socio", "administrador", "pessoa ligada", "mutuo")):
            return "socios"
        return "outros"
    if c.startswith("2.1.70"):
        return "provisoes"
    if c.startswith("2.1"):
        if "fornecedor" in text:
            return "fornecedores"
        if any(k in text for k in ("inss", "fgts", "simples", "irrf", "iss", "icms", "pis", "cofins", "tributo", "imposto")):
            return "tributos_a_recolher"
        if any(k in text for k in ("salario", "pro-labore", "ferias", "rescis")):
            return "folha"
        return "outros"

    if c.startswith("2.2.1.08"):
        return "fornecedores"
    if c.startswith(("2.2.1.09", "2.2.1.15", "2.2.1.16")):
        return "tributos_a_recolher"
    if c.startswith("2.2.1.10"):
        return "adiantamentos_clientes"
    if c.startswith(("2.2.11.3", "2.2")):
        return "emprestimos"

    if c.startswith(("2.3.10", "2.3.20", "2.3.30", "2.3.40")):
        return "patrimonio"
    if c.startswith("2.3.50"):
        return "resultado"
    if c.startswith("2.3"):
        return "patrimonio"

    if c.startswith("3.1.2"):
        if any(k in text for k in ("simples", "imposto", "tributo", "iss", "icms", "pis", "cofins")):
            return "tributos_sobre_receita"
        return "receita"
    if c.startswith(("3.1.1", "3.1.10", "3.1")):
        if c.startswith("3.1.20"):
            return "tributos_sobre_receita"
        return "receita"
    if c.startswith("3.2"):
        return "receita"

    if c.startswith("4.1"):
        return "custos"
    if c.startswith("4.2.1.01"):
        return "folha"
    if c.startswith("4.2.1.05"):
        return "despesas_representacao"
    if c.startswith(("4.2.1.11", "4.2.1.12", "4.2.2.03")):
        return "despesas_tributarias"
    if c.startswith("4.2.2.01"):
        return "folha"
    if c.startswith("4.2.2.05"):
        return "despesas"
    if c.startswith("4.2.3"):
        return "despesas"
    if c.startswith(("4.2.20.100", "4.2.20.200")):
        return "folha"
    if c.startswith("4.2.20.300.007"):
        return "multas_fiscais"
    if c.startswith("4.2.20.300"):
        return "despesas_tributarias"
    if c.startswith(("4.2.20.400", "4.2.20.500")):
        if any(k in text for k in ("representacao", "viagem", "hospedagem", "brinde", "alimentacao")):
            return "despesas_representacao"
        if any(k in text for k in ("combustivel", "ipva", "pedagio", "veiculo", "manutencao")):
            return "despesas_veiculos"
        return "despesas"
    if c.startswith(("4.2", "4.3", "4")):
        if any(k in text for k in ("pro-labore", "salario", "ordenado", "ferias", "fgts", "13")):
            return "folha"
        if "provisao" in text or "provisoes" in text:
            return "provisoes"
        if any(k in text for k in ("representacao", "viagem", "hospedagem")):
            return "despesas_representacao"
        if any(k in text for k in ("veiculo", "combustivel", "manutencao")):
            return "despesas_veiculos"
        if any(k in text for k in ("imposto", "taxa", "tributo", "inss", "fgts")):
            return "despesas_tributarias"
        return "despesas"

    if "socio" in text or "socios" in text or "administradores" in text:
        return "socios"
    if "adiantamento" in text or "adiantamentos" in text:
        return "adiantamentos"
    if "caixa" in text:
        return "caixa"
    if text.startswith("banco ") or "conta corrente" in text:
        return "bancos"
    if "duplicatas a receber" in text or "cliente" in text:
        return "clientes"
    if "estoque" in text:
        return "estoques"
    if "imobilizado" in text or "imovel" in text or "veiculo" in text:
        return "imobilizado"
    if "fornecedor" in text:
        return "fornecedores"
    if "receita" in text:
        return "receita"
    if any(k in text for k in ("imposto", "tributo", "simples", "irrf", "iss", "icms", "pis", "cofins", "inss", "fgts")):
        return "tributos"
    if any(k in text for k in ("pro-labore", "salario", "ordenado", "ferias", "rescis")):
        return "folha"
    if "provisao" in text or "provisoes" in text:
        return "provisoes"
    if any(k in text for k in ("representacao", "viagem", "hospedagem")):
        return "despesas_representacao"
    if any(k in text for k in ("veiculo", "combustivel", "manutencao")):
        return "despesas_veiculos"
    if "despesa" in text:
        return "despesas"

    return "outros"


def _infer_grupo_from_conta(codigo: str, conta: str) -> str | None:
    text = _normalize_key(conta)

    if "provisao" in text or "provisoes" in text or "ferias" in text or "13" in text:
        return "provisoes"
    if "imovel" in text or "imoveis" in text or "imobilizado" in text:
        return "imobilizado"
    if "veiculo" in text:
        return "imobilizado"
    if "fornecedor" in text:
        return "fornecedores"
    if "representacao" in text or "viagem" in text or "hospedagem" in text or "alimentacao" in text:
        return "despesas_representacao"
    if "combustivel" in text or "manutencao veicular" in text or "estacionamento" in text:
        return "despesas_veiculos"
    if "custo" in text:
        return "custos"
    if "investimento" in text or "aplicacao" in text:
        return "investimentos"
    if "capital social" in text or "reserva" in text or "prejuizo" in text or "lucro acumulado" in text:
        return "patrimonio_liquido"
    if any(k in text for k in ("imposto", "tributo", "simples", "irrf", "iss", "icms", "pis", "cofins", "inss", "fgts")):
        if codigo.startswith("2."):
            return "tributos_a_recolher"
        if codigo.startswith("3."):
            return "tributos_sobre_receita"
        if codigo.startswith("4."):
            return "despesas_tributarias"
        return "tributos"
    if "despesa" in text:
        return "despesas"

    return None


def _mapped_grupo_from_config(codigo: str, conta: str, *, allow_description: bool = True) -> str | None:
    try:
        mappings = load_account_map().get("mapeamentos", [])
    except Exception:
        return None

    code = str(codigo or "").strip()
    text = _normalize_key(conta)
    code_parts = "".join(char if char.isdigit() else " " for char in code).split()

    for mapping in mappings:
        if not isinstance(mapping, dict):
            continue

        group = str(mapping.get("grupo") or "").strip().lower()
        if group not in VALID_GRUPOS:
            continue

        exact_codes = {str(value).strip() for value in mapping.get("codigos_exatos", [])}
        if code and code in exact_codes:
            return group

        prefixes = [str(value).strip() for value in mapping.get("prefixos", []) if str(value).strip()]
        if code and any(code.startswith(prefix) for prefix in prefixes):
            return group

        segments = {str(value).strip() for value in mapping.get("segmentos_codigo", []) if str(value).strip()}
        if segments and any(segment in code_parts for segment in segments):
            return group

        if allow_description:
            descriptions = [
                _normalize_key(str(value))
                for value in mapping.get("descricoes_contem", [])
                if str(value).strip()
            ]
            if text and any(pattern and pattern in text for pattern in descriptions):
                return group

    return None


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
