from __future__ import annotations

import io
import re
from pathlib import Path

try:
    from fpdf import FPDF
except ImportError as exc:
    raise ImportError(
        f"Para exportar PDF, instale a biblioteca fpdf2: pip install fpdf2\n"
        f"Erro original: {exc}"
    ) from exc


# --- Palette (matches web preview) ---
CLR_ACCENT = (31, 122, 109)
CLR_ACCENT_LIGHT = (231, 243, 241)
CLR_ACCENT_SOFT = (247, 252, 250)
CLR_TITLE = (23, 32, 51)
CLR_BODY = (50, 50, 50)
CLR_MUTED = (110, 115, 125)
CLR_LINE = (215, 220, 230)
CLR_LINE_LIGHT = (232, 236, 242)
CLR_TABLE_HDR = (31, 122, 109)
CLR_TABLE_HDR_TEXT = (255, 255, 255)
CLR_TABLE_ROW_ALT = (248, 250, 252)
CLR_TABLE_BORDER = (210, 218, 226)
CLR_BADGE_ALTO_BG = (254, 226, 226)
CLR_BADGE_ALTO_TEXT = (185, 28, 28)
CLR_BADGE_MEDIO_BG = (254, 243, 199)
CLR_BADGE_MEDIO_TEXT = (161, 98, 7)
CLR_BADGE_BAIXO_BG = (209, 250, 229)
CLR_BADGE_BAIXO_TEXT = (6, 95, 70)
CLR_QUOTE_BG = (240, 253, 249)
CLR_QUOTE_BORDER = (31, 122, 109)
CLR_FOOTER = (150, 155, 165)
CLR_HEADER_BG = (250, 251, 253)

MARGIN_L = 18
MARGIN_R = 18
MARGIN_T = 24
MARGIN_B = 18
PAGE_W = 210
CONTENT_W = PAGE_W - MARGIN_L - MARGIN_R


class _ReportPDF(FPDF):
    def header(self) -> None:
        self.set_fill_color(*CLR_HEADER_BG)
        self.rect(0, 0, self.w, 26, "F")
        self.set_draw_color(*CLR_ACCENT)
        self.set_line_width(2)
        self.line(0, 26, self.w, 26)
        self.set_xy(MARGIN_L, 7)
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(*CLR_ACCENT)
        self.cell(0, 9, "Auditoria Fiscal IA", ln=True)
        self.set_xy(MARGIN_L, 17)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*CLR_MUTED)
        self.cell(0, 5, "Relatorio de Pre-Auditoria - Uso Interno", ln=True)
        self.set_y(32)

    def footer(self) -> None:
        self.set_y(-16)
        self.set_draw_color(*CLR_LINE_LIGHT)
        self.set_line_width(0.3)
        self.line(MARGIN_L, self.get_y(), PAGE_W - MARGIN_R, self.get_y())
        self.ln(3)
        self.set_font("Helvetica", "I", 7)
        self.set_text_color(*CLR_FOOTER)
        self.cell(0, 8, f"Pagina {self.page_no()}/{{nb}}", align="C")

    def add_main_title(self, text: str) -> None:
        self.set_font("Helvetica", "B", 17)
        self.set_text_color(*CLR_ACCENT)
        self.multi_cell(0, 10, _strip(text))
        self.ln(3)
        self.set_draw_color(*CLR_ACCENT)
        self.set_line_width(1)
        self.line(MARGIN_L, self.get_y(), MARGIN_L + 50, self.get_y())
        self.ln(6)

    def add_section_title(self, text: str) -> None:
        self.ln(8)
        y0 = self.get_y()
        self.set_draw_color(*CLR_ACCENT)
        self.set_line_width(3)
        self.line(MARGIN_L - 3, y0, MARGIN_L - 3, y0 + 10)
        self.set_x(MARGIN_L)
        self.set_font("Helvetica", "B", 12)
        self.set_text_color(*CLR_ACCENT)
        self.cell(0, 10, _strip(text).upper(), ln=True)
        self.ln(1)
        self.set_draw_color(*CLR_LINE_LIGHT)
        self.set_line_width(0.4)
        self.line(MARGIN_L, self.get_y(), PAGE_W - MARGIN_R, self.get_y())
        self.ln(4)

    def add_subsection(self, text: str) -> None:
        self.ln(4)
        self.set_font("Helvetica", "B", 10.5)
        self.set_text_color(*CLR_TITLE)
        self.cell(0, 7, _strip(text), ln=True)
        self.ln(2)

    def add_paragraph(self, text: str) -> None:
        self.set_font("Helvetica", "", 9.5)
        self.set_text_color(*CLR_BODY)
        cleaned = _strip(text)
        if cleaned:
            self.multi_cell(0, 6, cleaned)
        self.ln(2)

    def add_bullet(self, text: str) -> None:
        self.set_font("Helvetica", "", 9.5)
        self.set_text_color(*CLR_BODY)
        x0 = self.get_x()
        self.set_text_color(*CLR_ACCENT)
        self.set_font("Helvetica", "B", 9)
        self.cell(5, 6, "-")
        self.set_text_color(*CLR_BODY)
        self.set_font("Helvetica", "", 9.5)
        self.set_x(x0 + 7)
        self.multi_cell(CONTENT_W - 7, 6, _strip(text))
        self.ln(1)

    def add_table_header(self, labels: list[str]) -> None:
        x0 = self.get_x()
        y0 = self.get_y()
        col_w = CONTENT_W / len(labels)
        self.set_fill_color(*CLR_TABLE_HDR)
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(*CLR_TABLE_HDR_TEXT)
        self.rect(x0, y0, CONTENT_W, 8, "F")
        for idx, label in enumerate(labels):
            self.set_xy(x0 + idx * col_w + 3, y0 + 1.5)
            self.cell(col_w - 6, 5, _strip(label))
        self.set_y(y0 + 8)

    def add_table_row(self, cells: list[str], alt: bool = False) -> None:
        x0 = self.get_x()
        y0 = self.get_y()
        col_w = CONTENT_W / len(cells)
        row_h = 7.5
        if alt:
            self.set_fill_color(*CLR_TABLE_ROW_ALT)
            self.rect(x0, y0, CONTENT_W, row_h, "F")
        self.set_draw_color(*CLR_TABLE_BORDER)
        self.set_line_width(0.2)
        self.rect(x0, y0, CONTENT_W, row_h)
        for idx, cell in enumerate(cells):
            if idx > 0:
                self.line(x0 + idx * col_w, y0, x0 + idx * col_w, y0 + row_h)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(*CLR_BODY)
        for idx, cell in enumerate(cells):
            self.set_xy(x0 + idx * col_w + 3, y0 + 1.5)
            self.cell(col_w - 6, 5, _strip(cell))
        self.set_y(y0 + row_h)

    def add_blockquote(self, text: str) -> None:
        x0 = self.get_x()
        y0 = self.get_y()
        cleaned = _strip(text)
        words = cleaned.split()
        chars_per_line = int(CONTENT_W / 2.4)
        num_lines = max(1, sum(len(w) for w in words) / chars_per_line + 1)
        h = num_lines * 6 + 6
        self.set_fill_color(*CLR_QUOTE_BG)
        self.rect(x0, y0, CONTENT_W, h, "F")
        self.set_draw_color(*CLR_QUOTE_BORDER)
        self.set_line_width(2)
        self.line(x0, y0, x0, y0 + h)
        self.set_x(x0 + 7)
        self.set_y(y0 + 2.5)
        self.set_font("Helvetica", "I", 9)
        self.set_text_color(*CLR_MUTED)
        self.multi_cell(CONTENT_W - 10, 6, cleaned)
        self.ln(6)

    def add_separator(self) -> None:
        self.ln(2)
        self.set_draw_color(*CLR_LINE_LIGHT)
        self.set_line_width(0.5)
        self.line(MARGIN_L, self.get_y(), PAGE_W - MARGIN_R, self.get_y())
        self.ln(2)

    def add_info_line(self, key: str, value: str) -> None:
        self.set_font("Helvetica", "B", 9.5)
        self.set_text_color(*CLR_TITLE)
        self.cell(60, 6.5, f"{_strip(key)}:")
        self.set_font("Helvetica", "", 9.5)
        self.set_text_color(*CLR_BODY)
        self.cell(0, 6.5, f" {_strip(value)}")
        self.ln(6.5)


def _strip(text: str) -> str:
    from .utils import sanitize_for_latin1

    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"#+\s*", "", text)
    text = re.sub(r"^\s*[-*]\s*", "", text, flags=re.MULTILINE)
    text = text.replace("|", "").replace("---", "").replace("___", "").replace("`", "")
    return sanitize_for_latin1(text)


def markdown_to_pdf(markdown_text: str, output: str | Path | io.BytesIO) -> None:
    pdf = _ReportPDF()
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=MARGIN_B)
    pdf.set_margins(MARGIN_L, MARGIN_T, MARGIN_R)

    lines = markdown_text.splitlines()
    i = 0
    in_table = False
    table_rows: list[list[str]] = []

    def _flush_table() -> None:
        if not table_rows:
            return
        headers = table_rows[0]
        pdf.add_table_header(headers)
        for idx, row in enumerate(table_rows[1:]):
            while len(row) < len(headers):
                row.append("")
            pdf.add_table_row(row[:len(headers)], alt=(idx % 2 == 0))
        table_rows.clear()
        pdf.ln(3)

    while i < len(lines):
        raw = lines[i]
        line = raw.strip()
        i += 1

        if not line or line.startswith("---"):
            _flush_table()
            in_table = False
            continue

        if line.startswith("| ---") or line.startswith("|---"):
            continue

        if line.startswith("|") and line.endswith("|"):
            in_table = True
            cells = [c.strip() for c in line.strip("|").split("|")]
            table_rows.append(cells)
            continue
        elif in_table:
            _flush_table()
            in_table = False

        if line.startswith("# ") and not line.startswith("## "):
            pdf.add_main_title(line[2:])
        elif line.startswith("### "):
            pdf.add_subsection(line[4:])
        elif line.startswith("## "):
            pdf.add_section_title(line[3:])
        elif line.startswith("> "):
            quote_lines = []
            while line.startswith("> "):
                quote_lines.append(line[2:])
                if i < len(lines):
                    line = lines[i].strip()
                    i += 1
                else:
                    line = ""
            if line:
                i -= 1
            pdf.add_blockquote("\n".join(quote_lines))
        elif line.startswith("- **") and ":" in line:
            inner = line[2:].strip()
            key, _, val = inner.partition(":")
            pdf.add_info_line(key, val)
        elif line.startswith("- "):
            pdf.add_bullet(line[2:])
        else:
            pdf.add_paragraph(line)

    _flush_table()

    if isinstance(output, io.BytesIO):
        pdf.output(output)
    else:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        pdf.output(str(output))
