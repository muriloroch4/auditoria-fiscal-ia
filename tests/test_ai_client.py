from __future__ import annotations

import json
import os
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from src.auditoria import ai_client


class FakeHTTPResponse:
    def __init__(self, status: int, payload: dict | str):
        self.status = status
        self._raw = payload if isinstance(payload, str) else json.dumps(payload)

    def read(self) -> bytes:
        return self._raw.encode("utf-8")


class FakeHTTPSConnection:
    instances: list["FakeHTTPSConnection"] = []
    next_response = FakeHTTPResponse(
        200,
        {"choices": [{"message": {"content": "relatorio gerado"}}]},
    )

    def __init__(self, host: str, timeout: int, context) -> None:
        self.host = host
        self.timeout = timeout
        self.context = context
        self.closed = False
        self.request_args = None
        FakeHTTPSConnection.instances.append(self)

    def request(self, method: str, url: str, body: bytes, headers: dict[str, str]) -> None:
        self.request_args = (method, url, body, headers)

    def getresponse(self) -> FakeHTTPResponse:
        return FakeHTTPSConnection.next_response

    def close(self) -> None:
        self.closed = True


class AIClientTest(unittest.TestCase):
    def setUp(self) -> None:
        FakeHTTPSConnection.instances.clear()
        FakeHTTPSConnection.next_response = FakeHTTPResponse(
            200,
            {"choices": [{"message": {"content": "relatorio gerado"}}]},
        )

    def test_extract_content_requires_choices_and_content(self):
        self.assertEqual(
            ai_client._extract_content({"choices": [{"message": {"content": "ok"}}]}),
            "ok",
        )
        with self.assertRaisesRegex(ValueError, "sem choices"):
            ai_client._extract_content({})
        with self.assertRaisesRegex(ValueError, "sem conteudo"):
            ai_client._extract_content({"choices": [{"message": {}}]})

    def test_api_error_uses_openrouter_error_payload_or_raw_body(self):
        structured = ai_client._api_error(
            json.dumps({"error": {"message": "limite excedido", "type": "rate_limit"}}),
            429,
        )
        self.assertIsInstance(structured, ConnectionError)
        self.assertIn("rate_limit", str(structured))
        self.assertIn("limite excedido", str(structured))

        raw = ai_client._api_error("erro sem json", 500)
        self.assertIn("unknown", str(raw))
        self.assertIn("erro sem json", str(raw))

    def test_call_openrouter_sends_payload_and_closes_connection(self):
        with (
            unittest.mock.patch.object(ai_client, "_load_env_file"),
            unittest.mock.patch.object(ai_client.ssl, "create_default_context", return_value=object()),
            unittest.mock.patch.object(ai_client, "HTTPSConnection", FakeHTTPSConnection),
        ):
            content = ai_client.call_openrouter(
                [{"role": "user", "content": "Gerar"}],
                api_key="secret",
                model="modelo-teste",
                max_tokens=123,
                timeout=7,
            )

        self.assertEqual(content, "relatorio gerado")
        conn = FakeHTTPSConnection.instances[0]
        self.assertTrue(conn.closed)
        method, url, body, headers = conn.request_args
        self.assertEqual(method, "POST")
        self.assertEqual(url, "/api/v1/chat/completions")
        self.assertEqual(headers["Authorization"], "Bearer secret")
        self.assertEqual(headers["Host"], "openrouter.ai")
        payload = json.loads(body.decode("utf-8"))
        self.assertEqual(payload["model"], "modelo-teste")
        self.assertEqual(payload["max_tokens"], 123)
        self.assertEqual(payload["temperature"], 0.3)

    def test_call_openrouter_raises_for_missing_key_and_api_error(self):
        with (
            unittest.mock.patch.object(ai_client, "_load_env_file"),
            unittest.mock.patch.dict(os.environ, {}, clear=True),
        ):
            with self.assertRaisesRegex(ValueError, "OPENROUTER_API_KEY"):
                ai_client.call_openrouter([{"role": "user", "content": "x"}])

        FakeHTTPSConnection.next_response = FakeHTTPResponse(
            401,
            {"error": {"message": "token invalido", "type": "auth"}},
        )
        with (
            unittest.mock.patch.object(ai_client, "_load_env_file"),
            unittest.mock.patch.object(ai_client.ssl, "create_default_context", return_value=object()),
            unittest.mock.patch.object(ai_client, "HTTPSConnection", FakeHTTPSConnection),
        ):
            with self.assertRaisesRegex(ConnectionError, "token invalido"):
                ai_client.call_openrouter([{"role": "user", "content": "x"}], api_key="bad")

        self.assertTrue(FakeHTTPSConnection.instances[-1].closed)

    def test_load_env_file_reads_once_and_preserves_existing_environment(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_module = Path(tmpdir) / "pkg" / "src" / "auditoria" / "ai_client.py"
            fake_module.parent.mkdir(parents=True)
            env_path = Path(tmpdir) / "pkg" / ".env"
            env_path.write_text(
                "OPENROUTER_API_KEY=from-file\n"
                "OPENROUTER_MODEL='modelo-env'\n"
                "# comentario\n"
                "INVALIDA\n",
                encoding="utf-8",
            )

            ai_client._ENV_LOADED = False
            with (
                unittest.mock.patch.object(ai_client, "__file__", str(fake_module)),
                unittest.mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "already"}, clear=True),
            ):
                ai_client._load_env_file()
                self.assertEqual(os.environ["OPENROUTER_API_KEY"], "already")
                self.assertEqual(os.environ["OPENROUTER_MODEL"], "modelo-env")
                ai_client._load_env_file()

        ai_client._ENV_LOADED = False

    def test_is_api_key_configured_accepts_explicit_or_environment_key(self):
        with (
            unittest.mock.patch.object(ai_client, "_load_env_file"),
            unittest.mock.patch.dict(os.environ, {}, clear=True),
        ):
            self.assertFalse(ai_client.is_api_key_configured())
            self.assertTrue(ai_client.is_api_key_configured(" explicit "))

        with (
            unittest.mock.patch.object(ai_client, "_load_env_file"),
            unittest.mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "env-key"}, clear=True),
        ):
            self.assertTrue(ai_client.is_api_key_configured())


if __name__ == "__main__":
    unittest.main()
