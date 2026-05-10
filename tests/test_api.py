import io
import json
import unittest
import unittest.mock
import zipfile
from http import HTTPStatus
from io import BytesIO
from textwrap import dedent
from xml.sax.saxutils import escape

from src.auditoria.api import AuditApiHandler, UploadedFile


class FakeRfile:
    def __init__(self, data: bytes):
        self._data = data
        self._pos = 0

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            result = self._data[self._pos:]
            self._pos = len(self._data)
        else:
            result = self._data[self._pos:self._pos + size]
            self._pos += size
        return result


class FakeWfile:
    def __init__(self):
        self._buf = BytesIO()

    def write(self, data: bytes) -> None:
        self._buf.write(data)

    def getvalue(self) -> bytes:
        return self._buf.getvalue()


class TestableAuditApiHandler(AuditApiHandler):
    """A version of AuditApiHandler that can be used without a real socket."""

    def __init__(self, api_key: str | None = None, max_upload_bytes: int = 10 * 1024 * 1024):
        self.client_address = ("127.0.0.1", 8000)
        self.api_key = api_key
        self.ai_api_key = None
        self.max_upload_bytes = max_upload_bytes
        self.rfile = FakeRfile(b"")
        self.wfile = FakeWfile()
        self._response_code = None
        self._response_headers: dict[str, str] = {}
        self.headers: dict[str, str] = {}
        self.path = "/"

    def send_response(self, code: int) -> None:
        self._response_code = code

    def send_header(self, keyword: str, value: str) -> None:
        self._response_headers[keyword] = value

    def end_headers(self) -> None:
        pass


def _csv_trial_balance() -> bytes:
    return dedent(
        """\
        codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual
        1.1.1;Banco Conta Movimento;bancos;0;50000;48000;2000
        2.1.1;Simples Nacional a Recolher;tributos;0;0;2000;2000
        3.1.1;Receita de Servicos;receita;0;0;100000;100000
        4.1.1;Pro Labore;folha;0;10000;0;-10000
        4.2.1;Despesas Administrativas;despesas;0;20000;0;-20000
        """
    ).encode("utf-8")


def _xlsx_trial_balance() -> bytes:
    rows = [
        ["codigo", "conta", "grupo", "saldo_anterior", "debito", "credito", "saldo_atual"],
        ["1.1.1", "Banco Conta Movimento", "bancos", "0", "50000", "48000", "2000"],
        ["2.1.1", "Simples Nacional a Recolher", "tributos", "0", "0", "2000", "2000"],
        ["3.1.1", "Receita de Servicos", "receita", "0", "0", "100000", "100000"],
        ["4.1.1", "Pro Labore", "folha", "0", "10000", "0", "-10000"],
        ["4.2.1", "Despesas Administrativas", "despesas", "0", "20000", "0", "-20000"],
    ]
    output = BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _content_types_xml())
        archive.writestr("_rels/.rels", _root_rels_xml())
        archive.writestr("xl/workbook.xml", _workbook_xml())
        archive.writestr("xl/_rels/workbook.xml.rels", _workbook_rels_xml())
        archive.writestr("xl/worksheets/sheet1.xml", _sheet_xml(rows))
    return output.getvalue()


def _content_types_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '</Types>'
    )


def _root_rels_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '</Relationships>'
    )


def _workbook_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Balancete" sheetId="1" r:id="rId1"/></sheets>'
        '</workbook>'
    )


def _workbook_rels_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '</Relationships>'
    )


def _sheet_xml(rows: list[list[str]]) -> str:
    row_xml = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for col_index, value in enumerate(row):
            ref = f"{_column_name(col_index)}{row_index}"
            cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>')
        row_xml.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(row_xml)}</sheetData>'
        '</worksheet>'
    )


def _column_name(index: int) -> str:
    name = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _build_multipart_form(fields: dict[str, str | tuple[str, bytes, str]]) -> tuple[bytes, str]:
    """Build a multipart/form-data body.

    fields: {name: value} where value is str for text fields,
            or (filename, content, content_type) for file fields.
    Returns (body_bytes, content_type).
    """
    boundary = "----TestBoundary123456"
    lines: list[bytes] = []

    for name, value in fields.items():
        lines.append(f"--{boundary}".encode())
        if isinstance(value, str):
            lines.append(f'Content-Disposition: form-data; name="{name}"'.encode())
            lines.append(b"")
            lines.append(value.encode("utf-8"))
        else:
            filename, content, content_type = value
            lines.append(f'Content-Disposition: form-data; name="{name}"; filename="{filename}"'.encode())
            lines.append(f"Content-Type: {content_type}".encode())
            lines.append(b"")
            lines.append(content)

    lines.append(f"--{boundary}--".encode())
    lines.append(b"")

    body = b"\r\n".join(lines)
    content_type = f"multipart/form-data; boundary={boundary}"
    return body, content_type


class APIHealthTest(unittest.TestCase):
    def test_health_endpoint_returns_ok(self):
        handler = TestableAuditApiHandler()
        handler.path = "/health"
        with unittest.mock.patch.object(handler, "_send_json") as mock_send:
            handler.do_GET()
            mock_send.assert_called_once_with({"status": "ok"})

    def test_index_returns_html(self):
        handler = TestableAuditApiHandler()
        handler.path = "/"
        with unittest.mock.patch.object(handler, "_send_html") as mock_send:
            handler.do_GET()
            mock_send.assert_called_once()
            html_content = mock_send.call_args.args[0]
            self.assertIn("Auditoria Fiscal IA", html_content)

    def test_unknown_get_route_returns_404(self):
        handler = TestableAuditApiHandler()
        handler.path = "/unknown"
        with unittest.mock.patch.object(handler, "_send_json") as mock_send:
            handler.do_GET()
            mock_send.assert_called_once()
            self.assertEqual(mock_send.call_args.kwargs.get("status"), HTTPStatus.NOT_FOUND)


class APIAuthTest(unittest.TestCase):
    def test_auth_rejects_missing_key(self):
        handler = TestableAuditApiHandler(api_key="secret")
        handler.headers = {}
        result = handler._check_auth()
        self.assertFalse(result)
        self.assertEqual(handler._response_code, HTTPStatus.UNAUTHORIZED)

    def test_auth_rejects_wrong_key(self):
        handler = TestableAuditApiHandler(api_key="secret")
        handler.headers = {"X-API-Key": "wrong-key"}
        result = handler._check_auth()
        self.assertFalse(result)
        self.assertEqual(handler._response_code, HTTPStatus.UNAUTHORIZED)

    def test_auth_accepts_valid_key(self):
        handler = TestableAuditApiHandler(api_key="secret")
        handler.headers = {"X-API-Key": "secret"}
        result = handler._check_auth()
        self.assertTrue(result)

    def test_no_auth_when_api_key_none(self):
        handler = TestableAuditApiHandler(api_key=None)
        self.assertIsNone(handler.api_key)


class APIAuditUploadTest(unittest.TestCase):
    def _post_audit(self, api_key: str | None = None, body: bytes = b"", content_type: str = "", headers: dict | None = None):
        handler = TestableAuditApiHandler(api_key=api_key)
        handler.path = "/api/auditorias"
        handler.headers = headers or {}
        if content_type:
            handler.headers["Content-Type"] = content_type
        handler.headers["Content-Length"] = str(len(body))
        handler.rfile = FakeRfile(body)
        handler.wfile = FakeWfile()

        if api_key:
            handler._check_auth_called = True
            if not handler._check_auth():
                return handler

        with unittest.mock.patch.object(handler, "_send_json") as mock_send:
            handler._handle_audit_upload()
            return mock_send

    def test_upload_csv_returns_audit_result(self):
        csv_content = _csv_trial_balance()
        body, content_type = _build_multipart_form({
            "cliente": "Teste CSV",
            "periodo": "2026-T1",
            "balancete": ("balancete.csv", csv_content, "text/csv"),
        })

        handler = TestableAuditApiHandler()
        handler.use_ai = False
        handler.path = "/api/auditorias"
        handler.headers = {"Content-Type": content_type, "Content-Length": str(len(body))}
        handler.rfile = FakeRfile(body)
        handler.wfile = FakeWfile()

        with unittest.mock.patch.object(handler, "_send_json") as mock_send:
            handler._handle_audit_upload()
            mock_send.assert_called_once()
            result = mock_send.call_args.args[0]
            self.assertIn("nivel_geral", result)
            self.assertIn("achados", result)
            self.assertIn("relatorio_markdown", result)

    def test_upload_xlsx_returns_audit_result(self):
        xlsx_content = _xlsx_trial_balance()
        body, content_type = _build_multipart_form({
            "cliente": "Teste XLSX",
            "periodo": "2026-T1",
            "balancete": ("balancete.xlsx", xlsx_content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        })

        handler = TestableAuditApiHandler()
        handler.use_ai = False
        handler.path = "/api/auditorias"
        handler.headers = {"Content-Type": content_type, "Content-Length": str(len(body))}
        handler.rfile = FakeRfile(body)
        handler.wfile = FakeWfile()

        with unittest.mock.patch.object(handler, "_send_json") as mock_send:
            handler._handle_audit_upload()
            mock_send.assert_called_once()
            result = mock_send.call_args.args[0]
            self.assertIn("nivel_geral", result)

    def test_upload_missing_balancete_returns_400(self):
        body, content_type = _build_multipart_form({
            "cliente": "Sem Arquivo",
            "periodo": "2026-T1",
        })

        handler = TestableAuditApiHandler()
        handler.path = "/api/auditorias"
        handler.headers = {"Content-Type": content_type, "Content-Length": str(len(body))}
        handler.rfile = FakeRfile(body)
        handler.wfile = FakeWfile()

        with unittest.mock.patch.object(handler, "_send_json") as mock_send:
            handler._handle_audit_upload()
            mock_send.assert_called_once()
            self.assertEqual(mock_send.call_args.kwargs.get("status"), HTTPStatus.BAD_REQUEST)

    def test_upload_file_too_large_returns_413(self):
        handler = TestableAuditApiHandler(max_upload_bytes=100)
        handler.path = "/api/auditorias"
        handler.headers = {"Content-Type": "multipart/form-data", "Content-Length": "9999"}
        handler.rfile = FakeRfile(b"")
        handler.wfile = FakeWfile()

        with unittest.mock.patch.object(handler, "_send_json") as mock_send:
            handler._handle_audit_upload()
            mock_send.assert_called_once()
            self.assertEqual(mock_send.call_args.kwargs.get("status"), HTTPStatus.REQUEST_ENTITY_TOO_LARGE)

    def test_upload_requires_multipart(self):
        handler = TestableAuditApiHandler()
        handler.path = "/api/auditorias"
        handler.headers = {"Content-Type": "application/json", "Content-Length": "10"}
        handler.rfile = FakeRfile(b'{"test": true}')
        handler.wfile = FakeWfile()

        with unittest.mock.patch.object(handler, "_send_json") as mock_send:
            handler._handle_audit_upload()
            mock_send.assert_called_once()
            self.assertEqual(mock_send.call_args.kwargs.get("status"), HTTPStatus.BAD_REQUEST)

    def test_upload_auth_required_when_api_key_set(self):
        csv_content = _csv_trial_balance()
        body, content_type = _build_multipart_form({
            "cliente": "Auth Test",
            "periodo": "2026-T1",
            "balancete": ("balancete.csv", csv_content, "text/csv"),
        })

        handler = TestableAuditApiHandler(api_key="secret")
        handler.path = "/api/auditorias"
        handler.headers = {"Content-Type": content_type, "Content-Length": str(len(body))}
        handler.rfile = FakeRfile(body)
        handler.wfile = FakeWfile()

        with unittest.mock.patch.object(handler, "_send_json") as mock_send:
            handler.do_POST()
            mock_send.assert_called_once()
            self.assertEqual(mock_send.call_args.kwargs.get("status"), HTTPStatus.UNAUTHORIZED)

    def test_upload_succeeds_with_valid_auth(self):
        csv_content = _csv_trial_balance()
        body, content_type = _build_multipart_form({
            "cliente": "Auth Success",
            "periodo": "2026-T1",
            "balancete": ("balancete.csv", csv_content, "text/csv"),
        })

        handler = TestableAuditApiHandler(api_key="secret")
        handler.use_ai = False
        handler.path = "/api/auditorias"
        handler.headers = {
            "Content-Type": content_type,
            "Content-Length": str(len(body)),
            "X-API-Key": "secret",
        }
        handler.rfile = FakeRfile(body)
        handler.wfile = FakeWfile()

        with unittest.mock.patch.object(handler, "_send_json") as mock_send:
            handler.do_POST()
            mock_send.assert_called_once()
            result = mock_send.call_args.args[0]
            self.assertIn("nivel_geral", result)

    def test_upload_auth_key_is_not_used_as_openrouter_key(self):
        csv_content = _csv_trial_balance()
        body, content_type = _build_multipart_form({
            "cliente": "Auth Separate",
            "periodo": "2026-T1",
            "balancete": ("balancete.csv", csv_content, "text/csv"),
        })

        handler = TestableAuditApiHandler(api_key="local-secret")
        handler.use_ai = True
        handler.path = "/api/auditorias"
        handler.headers = {
            "Content-Type": content_type,
            "Content-Length": str(len(body)),
            "X-API-Key": "local-secret",
        }
        handler.rfile = FakeRfile(body)
        handler.wfile = FakeWfile()

        with unittest.mock.patch("src.auditoria.api.generate_markdown_report", return_value="# OK") as mock_report:
            with unittest.mock.patch.object(handler, "_send_json") as mock_send:
                handler.do_POST()

        mock_report.assert_called_once()
        self.assertIsNone(mock_report.call_args.kwargs["api_key"])
        mock_send.assert_called_once()


class APICORSTest(unittest.TestCase):
    def test_options_returns_no_content_with_cors(self):
        handler = TestableAuditApiHandler()
        handler.path = "/api/auditorias"
        handler.headers = {}
        handler.rfile = FakeRfile(b"")
        handler.wfile = FakeWfile()

        handler.do_OPTIONS()

        self.assertEqual(handler._response_code, HTTPStatus.NO_CONTENT)
        self.assertIn("Access-Control-Allow-Origin", handler._response_headers)
        self.assertEqual(handler._response_headers["Access-Control-Allow-Origin"], "*")

    def test_post_responses_include_cors_headers(self):
        csv_content = _csv_trial_balance()
        body, content_type = _build_multipart_form({
            "cliente": "CORS Test",
            "periodo": "2026-T1",
            "balancete": ("balancete.csv", csv_content, "text/csv"),
        })

        handler = TestableAuditApiHandler()
        handler.use_ai = False
        handler.path = "/api/auditorias"
        handler.headers = {"Content-Type": content_type, "Content-Length": str(len(body))}
        handler.rfile = FakeRfile(body)
        handler.wfile = FakeWfile()

        handler._handle_audit_upload()

        self.assertIn("Access-Control-Allow-Origin", handler._response_headers)
        self.assertEqual(handler._response_headers["Access-Control-Allow-Origin"], "*")


class APIUnknownRouteTest(unittest.TestCase):
    def test_unknown_post_returns_404(self):
        handler = TestableAuditApiHandler()
        handler.path = "/api/unknown"
        handler.headers = {}
        handler.rfile = FakeRfile(b"")
        handler.wfile = FakeWfile()

        with unittest.mock.patch.object(handler, "_send_json") as mock_send:
            handler.do_POST()
            mock_send.assert_called_once()
            self.assertEqual(mock_send.call_args.kwargs.get("status"), HTTPStatus.NOT_FOUND)


class MultipartFormTest(unittest.TestCase):
    def test_build_and_parse_text_fields(self):
        body, content_type = _build_multipart_form({
            "cliente": "Teste",
            "periodo": "2026-T1",
        })

        handler = TestableAuditApiHandler()
        handler.headers = {"Content-Type": content_type, "Content-Length": str(len(body))}
        handler.rfile = FakeRfile(body)

        form = handler._read_multipart_form()

        self.assertEqual(form["cliente"], "Teste")
        self.assertEqual(form["periodo"], "2026-T1")

    def test_build_and_parse_file_field(self):
        file_content = b"codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual\n"
        body, content_type = _build_multipart_form({
            "balancete": ("test.csv", file_content, "text/csv"),
            "cliente": "Teste",
        })

        handler = TestableAuditApiHandler()
        handler.headers = {"Content-Type": content_type, "Content-Length": str(len(body))}
        handler.rfile = FakeRfile(body)

        form = handler._read_multipart_form()

        self.assertIsInstance(form["balancete"], UploadedFile)
        self.assertEqual(form["balancete"].filename, "test.csv")
        self.assertEqual(form["balancete"].content, file_content)
        self.assertEqual(form["cliente"], "Teste")

    def test_non_multipart_raises_value_error(self):
        handler = TestableAuditApiHandler()
        handler.headers = {"Content-Type": "application/json", "Content-Length": "0"}
        handler.rfile = FakeRfile(b"")

        with self.assertRaises(ValueError):
            handler._read_multipart_form()


if __name__ == "__main__":
    unittest.main()
