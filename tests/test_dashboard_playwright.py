import struct
import tempfile
import threading
import unittest
import zlib
from http.server import ThreadingHTTPServer
from pathlib import Path

from src.auditoria.api import AuditApiHandler

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - optional local dependency.
    PlaywrightError = Exception
    sync_playwright = None


@unittest.skipIf(sync_playwright is None, "Playwright nao instalado.")
class DashboardPlaywrightTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.TemporaryDirectory()
        AuditApiHandler.api_key = None
        AuditApiHandler.cors_origin = "*"
        AuditApiHandler.regime_tributario = None
        AuditApiHandler.atividade = "servicos"
        AuditApiHandler.db_path = str(Path(cls.tmpdir.name) / "auditoria.sqlite")
        AuditApiHandler.max_upload_bytes = 10 * 1024 * 1024
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), AuditApiHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join(timeout=5)
        cls.server.server_close()
        cls.tmpdir.cleanup()

    def test_dashboard_upload_and_print_document_render(self):
        sample = Path("samples/balancete_simples_servicos.csv").resolve()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                try:
                    page = browser.new_page(viewport={"width": 1440, "height": 1000})
                    page.goto(self.base_url, wait_until="networkidle")
                    page.fill("#cliente", "Cliente Playwright")
                    page.fill("#cnpj", "12.345.678/0001-90")
                    page.fill("#periodo", "2026-T1")
                    page.set_input_files("#balancete", str(sample))
                    page.click("#submit-button")
                    page.wait_for_selector(".risk-panel", timeout=15000)

                    risk_text = page.locator(".risk-panel").inner_text().lower()
                    self.assertIn("risco", risk_text)
                    self.assertGreater(page.locator(".visual-card").count(), 0)
                    self.assertLessEqual(
                        page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth"),
                        2,
                    )
                    self.assert_png_not_blank(page.screenshot(full_page=False))

                    print_html = page.evaluate("buildPrintDocumentHtml(normalizeAuditPayload(lastData))")
                    self.assertIn("pdf-document", print_html)
                    self.assertIn("Leitura para o cliente", print_html)
                    self.assertIn("Plano de ação consultivo", print_html)

                    print_page = browser.new_page(viewport={"width": 1120, "height": 1580})
                    try:
                        print_page.set_content(
                            f"""<!doctype html>
                            <html lang="pt-BR">
                              <head>
                                <meta charset="utf-8">
                                <link rel="stylesheet" href="{self.base_url}/static/styles.css">
                              </head>
                              <body><main class="print-page">{print_html}</main></body>
                            </html>""",
                            wait_until="networkidle",
                        )
                        self.assertTrue(print_page.locator(".pdf-document").is_visible())
                        self.assertGreater(print_page.locator(".pdf-summary-card").count(), 0)
                        self.assertGreater(print_page.locator(".pdf-visual-card").count(), 0)
                        self.assert_png_not_blank(print_page.locator(".pdf-document").screenshot())
                    finally:
                        print_page.close()
                finally:
                    browser.close()
        except PlaywrightError as exc:
            self.skipTest(f"Playwright Chromium indisponivel: {exc}")

    def assert_png_not_blank(self, png: bytes) -> None:
        width, height, colors = _png_sampled_colors(png)
        self.assertGreaterEqual(width, 320)
        self.assertGreaterEqual(height, 240)
        self.assertGreater(len(colors), 12)


def _png_sampled_colors(png: bytes) -> tuple[int, int, set[tuple[int, ...]]]:
    if not png.startswith(b"\x89PNG\r\n\x1a\n"):
        raise AssertionError("Screenshot nao e PNG valido.")

    offset = 8
    width = height = bit_depth = color_type = None
    payload = bytearray()
    while offset < len(png):
        length = struct.unpack(">I", png[offset : offset + 4])[0]
        kind = png[offset + 4 : offset + 8]
        data = png[offset + 8 : offset + 8 + length]
        offset += 12 + length
        if kind == b"IHDR":
            width, height, bit_depth, color_type = struct.unpack(">IIBB", data[:10])
        elif kind == b"IDAT":
            payload.extend(data)
        elif kind == b"IEND":
            break

    if width is None or height is None or bit_depth != 8 or color_type not in (2, 6):
        raise AssertionError("Formato PNG nao suportado para teste visual.")

    channels = 4 if color_type == 6 else 3
    row_size = width * channels
    raw = zlib.decompress(bytes(payload))
    rows: list[bytearray] = []
    cursor = 0
    previous = bytearray(row_size)
    for _ in range(height):
        filter_type = raw[cursor]
        cursor += 1
        current = bytearray(raw[cursor : cursor + row_size])
        cursor += row_size
        _unfilter_png_row(current, previous, filter_type, channels)
        rows.append(current)
        previous = current

    colors: set[tuple[int, ...]] = set()
    step_y = max(1, height // 40)
    step_x = max(1, width // 40)
    for y in range(0, height, step_y):
        row = rows[y]
        for x in range(0, width, step_x):
            index = x * channels
            colors.add(tuple(row[index : index + min(channels, 3)]))
    return width, height, colors


def _unfilter_png_row(row: bytearray, previous: bytearray, filter_type: int, channels: int) -> None:
    for index, value in enumerate(row):
        left = row[index - channels] if index >= channels else 0
        up = previous[index]
        up_left = previous[index - channels] if index >= channels else 0
        if filter_type == 1:
            row[index] = (value + left) & 0xFF
        elif filter_type == 2:
            row[index] = (value + up) & 0xFF
        elif filter_type == 3:
            row[index] = (value + ((left + up) // 2)) & 0xFF
        elif filter_type == 4:
            row[index] = (value + _paeth(left, up, up_left)) & 0xFF
        elif filter_type != 0:
            raise AssertionError(f"Filtro PNG nao suportado: {filter_type}")


def _paeth(left: int, up: int, up_left: int) -> int:
    prediction = left + up - up_left
    distances = (
        (abs(prediction - left), left),
        (abs(prediction - up), up),
        (abs(prediction - up_left), up_left),
    )
    return min(distances, key=lambda item: item[0])[1]
