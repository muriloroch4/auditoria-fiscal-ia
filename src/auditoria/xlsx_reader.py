from __future__ import annotations

import re
import zipfile
from io import BytesIO
from xml.etree import ElementTree


def xlsx_table_rows(content: bytes) -> list[list[str]]:
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
