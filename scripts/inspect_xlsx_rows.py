from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree


NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def main() -> None:
    path = Path(sys.argv[1])
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    with zipfile.ZipFile(path) as workbook:
        shared_strings = read_shared_strings(workbook)
        sheet_path = first_sheet_path(workbook)
        sheet_root = ElementTree.fromstring(workbook.read(sheet_path))

    for row in sheet_root.findall(".//m:sheetData/m:row", NS)[:limit]:
        values = []
        for cell in row.findall("m:c", NS):
            value = cell_value(cell, shared_strings)
            if value.strip():
                values.append(f"{cell.attrib.get('r')}={value[:80]}")
        if values:
            print(f"{row.attrib.get('r')}: " + " | ".join(values))


def read_shared_strings(workbook: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in workbook.namelist():
        return []
    root = ElementTree.fromstring(workbook.read("xl/sharedStrings.xml"))
    return ["".join(t.text or "" for t in item.findall(".//m:t", NS)) for item in root.findall("m:si", NS)]


def first_sheet_path(workbook: zipfile.ZipFile) -> str:
    workbook_root = ElementTree.fromstring(workbook.read("xl/workbook.xml"))
    rels_root = ElementTree.fromstring(workbook.read("xl/_rels/workbook.xml.rels"))
    rel_attr = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
    rel_ns = {"rel": "http://schemas.openxmlformats.org/package/2006/relationships"}
    first_sheet = workbook_root.find("m:sheets/m:sheet", NS)
    rel_id = first_sheet.attrib[rel_attr]
    for rel in rels_root.findall("rel:Relationship", rel_ns):
        if rel.attrib["Id"] == rel_id:
            target = rel.attrib["Target"].lstrip("/")
            return target if target.startswith("xl/") else f"xl/{target}"
    raise ValueError("Sheet not found")


def cell_value(cell: ElementTree.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(t.text or "" for t in cell.findall(".//m:t", NS)).strip()

    value_node = cell.find("m:v", NS)
    if value_node is None or value_node.text is None:
        return ""

    value = value_node.text.strip()
    if cell_type == "s" and value:
        return shared_strings[int(value)].strip()
    return value


if __name__ == "__main__":
    main()
