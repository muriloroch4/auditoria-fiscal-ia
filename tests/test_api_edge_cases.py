from __future__ import annotations

import json
import unittest
import unittest.mock
from http import HTTPStatus

from src.auditoria import api
from tests.test_api import FakeRfile, FakeWfile, TestableAuditApiHandler, _build_multipart_form


class APIAuthRouteEdgeTest(unittest.TestCase):
    def test_get_and_post_protected_routes_stop_when_auth_fails(self):
        routes = [
            ("GET", "/api/auditorias"),
            ("GET", "/api/auditorias/anual"),
            ("POST", "/api/auditorias/anual"),
            ("POST", "/api/auditorias/anual-balancetes"),
        ]

        for method, path in routes:
            with self.subTest(method=method, path=path):
                handler = TestableAuditApiHandler(api_key="secret")
                handler.path = path
                handler.headers = {}
                handler.rfile = FakeRfile(b"")
                handler.wfile = FakeWfile()

                if method == "GET":
                    handler.do_GET()
                else:
                    handler.do_POST()

                self.assertEqual(handler._response_code, HTTPStatus.UNAUTHORIZED)

    def test_log_message_delegates_to_logger(self):
        handler = TestableAuditApiHandler()
        with unittest.mock.patch("src.auditoria.api.logger.info") as info:
            handler.log_message("GET %s", "/health")

        info.assert_called_once()


class APIUploadErrorBranchesTest(unittest.TestCase):
    def test_quarterly_upload_unexpected_exception_returns_500(self):
        body, content_type = _build_multipart_form(
            {
                "cliente": "Erro",
                "periodo": "2026-T1",
                "balancete": ("balancete.csv", b"conteudo", "text/csv"),
            }
        )
        handler = TestableAuditApiHandler()
        handler.headers = {"Content-Type": content_type, "Content-Length": str(len(body))}
        handler.rfile = FakeRfile(body)

        with (
            unittest.mock.patch("src.auditoria.api.process_quarterly_upload", side_effect=RuntimeError("falha interna")),
            unittest.mock.patch.object(handler, "_send_json") as send_json,
        ):
            handler._handle_audit_upload()

        self.assertEqual(send_json.call_args.kwargs.get("status"), HTTPStatus.INTERNAL_SERVER_ERROR)
        self.assertIn("falha interna", send_json.call_args.args[0]["erro"])

    def test_annual_upload_rejects_large_invalid_empty_and_long_manifest(self):
        large = TestableAuditApiHandler(max_upload_bytes=10)
        large.headers = {"Content-Length": "1000"}
        with unittest.mock.patch.object(large, "_send_json") as send_json:
            large._handle_annual_upload()
        self.assertEqual(send_json.call_args.kwargs.get("status"), HTTPStatus.REQUEST_ENTITY_TOO_LARGE)

        cases = [
            ("{invalid", "Manifest anual inv"),
            (json.dumps({"trimestres": []}), "lista 'trimestres'"),
            (json.dumps({"trimestres": [{} for _ in range(5)]}), "4 trimestres"),
            (json.dumps(["T1"]), "lista 'trimestres'"),
        ]
        for manifest, expected in cases:
            with self.subTest(manifest=manifest):
                body, content_type = _build_multipart_form({"manifest": manifest})
                handler = TestableAuditApiHandler()
                handler.headers = {"Content-Type": content_type, "Content-Length": str(len(body))}
                handler.rfile = FakeRfile(body)
                with unittest.mock.patch.object(handler, "_send_json") as send_json:
                    handler._handle_annual_upload()

                self.assertEqual(send_json.call_args.kwargs.get("status"), HTTPStatus.BAD_REQUEST)
                self.assertIn(expected, send_json.call_args.args[0]["erro"])

    def test_annual_upload_handles_validation_and_unexpected_errors(self):
        body, content_type = _build_multipart_form({"manifest": json.dumps({"trimestres": [{"field": "b0"}]})})

        for exc, status in ((ValueError("trimestre invalido"), HTTPStatus.BAD_REQUEST), (RuntimeError("boom"), HTTPStatus.INTERNAL_SERVER_ERROR)):
            with self.subTest(exc=type(exc).__name__):
                handler = TestableAuditApiHandler()
                handler.headers = {"Content-Type": content_type, "Content-Length": str(len(body))}
                handler.rfile = FakeRfile(body)

                with (
                    unittest.mock.patch("src.auditoria.api.build_uploaded_annual_payload", side_effect=exc),
                    unittest.mock.patch.object(handler, "_send_json") as send_json,
                ):
                    handler._handle_annual_upload()

                self.assertEqual(send_json.call_args.kwargs.get("status"), status)


class APIStoredAnnualEdgeTest(unittest.TestCase):
    def test_audit_list_handles_invalid_query_and_storage_failure(self):
        handler = TestableAuditApiHandler()
        with unittest.mock.patch.object(handler, "_send_json") as send_json:
            handler._handle_audit_list({"ano": ["abc"]})
        self.assertEqual(send_json.call_args.kwargs.get("status"), HTTPStatus.BAD_REQUEST)

        handler = TestableAuditApiHandler()
        with (
            unittest.mock.patch.object(handler, "_storage", side_effect=RuntimeError("db indisponivel")),
            unittest.mock.patch.object(handler, "_send_json") as send_json,
        ):
            handler._handle_audit_list({})
        self.assertEqual(send_json.call_args.kwargs.get("status"), HTTPStatus.INTERNAL_SERVER_ERROR)

    def test_saved_annual_generation_validates_cnpj_year_body_and_sources(self):
        scenarios = [
            ({}, b"", "Informe o CNPJ", HTTPStatus.BAD_REQUEST),
            ({"cnpj": ["12.345.678/0001-90"]}, b"", "Informe o ano", HTTPStatus.BAD_REQUEST),
            ({}, b"[1, 2]", "objeto", HTTPStatus.BAD_REQUEST),
        ]

        for query, body, expected, status in scenarios:
            with self.subTest(expected=expected):
                handler = TestableAuditApiHandler()
                handler.headers = {"Content-Length": str(len(body))}
                handler.rfile = FakeRfile(body)
                with unittest.mock.patch.object(handler, "_send_json") as send_json:
                    handler._handle_saved_annual_generation(query)

                self.assertEqual(send_json.call_args.kwargs.get("status"), status)
                self.assertIn(expected, send_json.call_args.args[0]["erro"])

        handler = TestableAuditApiHandler()
        handler.headers = {"Content-Length": "0"}
        handler.rfile = FakeRfile(b"")
        fake_storage = unittest.mock.Mock()
        fake_storage.annual_sources.return_value = []
        with (
            unittest.mock.patch.object(handler, "_storage", return_value=fake_storage),
            unittest.mock.patch.object(handler, "_send_json") as send_json,
        ):
            handler._handle_saved_annual_generation({"cnpj": ["12.345.678/0001-90"], "ano": ["2026"]})

        self.assertEqual(send_json.call_args.kwargs.get("status"), HTTPStatus.NOT_FOUND)

    def test_saved_annual_generation_handles_value_and_unexpected_errors(self):
        body = json.dumps({"cnpj": "12.345.678/0001-90", "ano": 2026}).encode("utf-8")
        for exc, status in ((ValueError("payload invalido"), HTTPStatus.BAD_REQUEST), (RuntimeError("boom"), HTTPStatus.INTERNAL_SERVER_ERROR)):
            with self.subTest(exc=type(exc).__name__):
                handler = TestableAuditApiHandler()
                handler.headers = {"Content-Length": str(len(body))}
                handler.rfile = FakeRfile(body)
                fake_storage = unittest.mock.Mock()
                fake_storage.annual_sources.return_value = [{"payload": "ok"}]

                with (
                    unittest.mock.patch.object(handler, "_storage", return_value=fake_storage),
                    unittest.mock.patch("src.auditoria.api.build_annual_comparison", side_effect=exc),
                    unittest.mock.patch.object(handler, "_send_json") as send_json,
                ):
                    handler._handle_saved_annual_generation({})

                self.assertEqual(send_json.call_args.kwargs.get("status"), status)

    def test_latest_annual_validates_query_not_found_and_unexpected_error(self):
        scenarios = [
            ({}, "Informe o CNPJ", HTTPStatus.BAD_REQUEST),
            ({"cnpj": ["12.345.678/0001-90"]}, "Informe o ano", HTTPStatus.BAD_REQUEST),
        ]
        for query, expected, status in scenarios:
            with self.subTest(expected=expected):
                handler = TestableAuditApiHandler()
                with unittest.mock.patch.object(handler, "_send_json") as send_json:
                    handler._handle_latest_annual(query)
                self.assertEqual(send_json.call_args.kwargs.get("status"), status)
                self.assertIn(expected, send_json.call_args.args[0]["erro"])

        fake_storage = unittest.mock.Mock()
        fake_storage.latest_annual_audit.return_value = None
        handler = TestableAuditApiHandler()
        with (
            unittest.mock.patch.object(handler, "_storage", return_value=fake_storage),
            unittest.mock.patch.object(handler, "_send_json") as send_json,
        ):
            handler._handle_latest_annual({"cnpj": ["12.345.678/0001-90"], "ano": ["2026"]})
        self.assertEqual(send_json.call_args.kwargs.get("status"), HTTPStatus.NOT_FOUND)

        handler = TestableAuditApiHandler()
        with (
            unittest.mock.patch.object(handler, "_storage", side_effect=RuntimeError("db")),
            unittest.mock.patch.object(handler, "_send_json") as send_json,
        ):
            handler._handle_latest_annual({"cnpj": ["12.345.678/0001-90"], "ano": ["2026"]})
        self.assertEqual(send_json.call_args.kwargs.get("status"), HTTPStatus.INTERNAL_SERVER_ERROR)

    def test_read_json_body_accepts_empty_blank_and_object_only(self):
        handler = TestableAuditApiHandler()
        handler.headers = {"Content-Length": "0"}
        handler.rfile = FakeRfile(b"")
        self.assertEqual(handler._read_json_body(), {})

        handler.headers = {"Content-Length": "3"}
        handler.rfile = FakeRfile(b"   ")
        self.assertEqual(handler._read_json_body(), {})

        body = b'{"ano": 2026}'
        handler.headers = {"Content-Length": str(len(body))}
        handler.rfile = FakeRfile(body)
        self.assertEqual(handler._read_json_body(), {"ano": 2026})

        body = b"[1]"
        handler.headers = {"Content-Length": str(len(body))}
        handler.rfile = FakeRfile(body)
        with self.assertRaisesRegex(ValueError, "objeto"):
            handler._read_json_body()


class APIRunServerTest(unittest.TestCase):
    def test_run_server_configures_handler_and_starts_threading_server(self):
        fake_server = unittest.mock.Mock()
        with (
            unittest.mock.patch("src.auditoria.api.ThreadingHTTPServer", return_value=fake_server) as server_cls,
            unittest.mock.patch("src.auditoria.api._validate_runtime_security") as validate,
        ):
            api.run_server(
                host="127.0.0.1",
                port=8123,
                api_key="secret",
                cors_origin="http://localhost:3000",
                regime_tributario="Simples Nacional",
                atividade="comercio",
                db_path=":memory:",
                allow_unsafe_network=True,
            )

        validate.assert_called_once_with("127.0.0.1", "secret", "http://localhost:3000", True)
        server_cls.assert_called_once()
        self.assertEqual(api.AuditApiHandler.api_key, "secret")
        self.assertEqual(api.AuditApiHandler.cors_origin, "http://localhost:3000")
        self.assertEqual(api.AuditApiHandler.atividade, "comercio")
        fake_server.serve_forever.assert_called_once()

    def test_main_uses_environment_api_key_and_runtime_args(self):
        args = unittest.mock.Mock(
            verbose=True,
            host="127.0.0.1",
            port=8123,
            api_key=None,
            cors_origin=None,
            regime_tributario="Simples Nacional",
            atividade="servicos",
            db_path=":memory:",
            allow_unsafe_network=False,
        )
        with (
            unittest.mock.patch("src.auditoria.api._parse_args", return_value=args),
            unittest.mock.patch("src.auditoria.api._setup_logging") as setup_logging,
            unittest.mock.patch("src.auditoria.api.run_server") as run_server,
            unittest.mock.patch.dict(api.os.environ, {"AUDIT_API_KEY": "env-secret", "AUDIT_CORS_ORIGIN": "http://app.local"}, clear=True),
        ):
            api.main()

        setup_logging.assert_called_once_with(True)
        run_server.assert_called_once_with(
            host="127.0.0.1",
            port=8123,
            api_key="env-secret",
            cors_origin="http://app.local",
            regime_tributario="Simples Nacional",
            atividade="servicos",
            db_path=":memory:",
            allow_unsafe_network=False,
        )


if __name__ == "__main__":
    unittest.main()
