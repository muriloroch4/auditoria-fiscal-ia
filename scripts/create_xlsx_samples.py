from __future__ import annotations

import csv
import zipfile
from io import StringIO
from pathlib import Path
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"


def main() -> None:
    convert_csv_to_xlsx(
        SAMPLES / "modelo_balancete_regras.csv",
        SAMPLES / "modelo_balancete_regras.xlsx",
    )
    convert_csv_to_xlsx(
        SAMPLES / "exemplo_balancete_todas_regras.csv",
        SAMPLES / "exemplo_balancete_todas_regras.xlsx",
    )


def convert_csv_to_xlsx(input_path: Path, output_path: Path) -> None:
    rows = list(csv.reader(StringIO(input_path.read_text(encoding="utf-8-sig")), delimiter=";"))
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types_xml())
        archive.writestr("_rels/.rels", root_rels_xml())
        archive.writestr("xl/workbook.xml", workbook_xml())
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml())
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml(rows))


def sheet_xml(rows: list[list[str]]) -> str:
    row_xml = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for col_index, value in enumerate(row):
            ref = f"{column_name(col_index)}{row_index}"
            cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>')
        row_xml.append(f'<row r="{row_index}">{"".join(cells)}</row>')

    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(row_xml)}</sheetData>'
        '</worksheet>'
    )


def column_name(index: int) -> str:
    name = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def content_types_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '</Types>'
    )


def root_rels_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '</Relationships>'
    )


def workbook_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Balancete" sheetId="1" r:id="rId1"/></sheets>'
        '</workbook>'
    )


def workbook_rels_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '</Relationships>'
    )


if __name__ == "__main__":
    main()
