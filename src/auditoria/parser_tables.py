from __future__ import annotations

import csv
from io import StringIO
from pathlib import Path

from .xlsx_reader import xlsx_table_rows as _xlsx_table_rows


def detect_csv_delimiter(content: str) -> str:
    first_line = content.splitlines()[0] if content else ""
    candidates = [";", ",", "\t", "|"]
    counts = {d: first_line.count(d) for d in candidates}
    best = max(counts, key=lambda delimiter: counts[delimiter])
    return best if counts[best] > 0 else ";"


def csv_table_rows(content: str) -> list[list[str]]:
    delimiter = detect_csv_delimiter(content)
    return [row for row in csv.reader(StringIO(content), delimiter=delimiter)]


def xlsx_table_rows(content: bytes) -> list[list[str]]:
    return _xlsx_table_rows(content)


def normalize_header(value: str | None) -> str:
    return (value or "").strip().lower()


def index_of(values: list[str], wanted: str) -> int | None:
    try:
        return values.index(wanted)
    except ValueError:
        return None


def value_at(row: list[str], index: int | None) -> str:
    if index is None or index >= len(row):
        return ""
    return row[index]


def ps_escape(path: Path) -> str:
    return str(path).replace("'", "''")
