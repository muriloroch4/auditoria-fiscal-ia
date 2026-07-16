from __future__ import annotations

import hmac
import json
import logging
import os
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .annual import build_annual_comparison
from .api_helpers import (
    form_text as _form_text,
    payload_int as _payload_int,
    query_int as _query_int,
    query_text as _query_text,
)
from .api_operations import build_uploaded_annual_payload, process_quarterly_upload
from .api_responses import (
    index_html as _index_html,
    send_html_response as _send_html_response,
    send_json_response as _send_json_response,
    send_static_response as _send_static_response,
)
from .api_runtime import (
    is_loopback_host as _is_loopback_host,
    parse_args as _parse_args,
    setup_logging as _setup_logging,
    validate_runtime_security as _validate_runtime_security,
)
from .http_multipart import UploadedFile, read_multipart_form
from .schema_loader import load_json_schema
from .storage import DB_SCHEMA_VERSION, AuditStorage

logger = logging.getLogger(__name__)


class AuditApiHandler(BaseHTTPRequestHandler):
    use_ai: bool = True
    api_key: str | None = None
    ai_api_key: str | None = None
    cors_origin: str = "*"
    regime_tributario: str | None = None
    atividade: str = "servicos"
    db_path: str | None = None
    max_upload_bytes: int = 10 * 1024 * 1024

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/":
            self._send_html(_index_html())
            return

        if path.startswith("/static/"):
            self._send_static(path)
            return

        if path == "/health":
            self._send_json({"status": "ok"})
            return

        if path in ("/api/auditorias/schema", "/api/auditorias/schema/trimestral"):
            self._send_json(load_json_schema("trimestral"))
            return

        if path == "/api/auditorias/schema/anual":
            self._send_json(load_json_schema("anual"))
            return

        if path == "/api/auditorias":
            if self.api_key and not self._check_auth():
                return
            self._handle_audit_list(query)
            return

        if path == "/api/auditorias/anual":
            if self.api_key and not self._check_auth():
                return
            self._handle_latest_annual(query)
            return

        logger.warning("Rota não encontrada: GET %s", path)
        self._send_json({"erro": "Rota não encontrada."}, status=HTTPStatus.NOT_FOUND)

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_cors_headers()
        self.end_headers()

    def _send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", self.cors_origin or "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-API-Key")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/api/auditorias":
            if self.api_key and not self._check_auth():
                return
            self._handle_audit_upload()
            return

        if path == "/api/auditorias/anual":
            if self.api_key and not self._check_auth():
                return
            self._handle_saved_annual_generation(query)
            return

        if path == "/api/auditorias/anual-balancetes":
            if self.api_key and not self._check_auth():
                return
            self._handle_annual_upload()
            return

        logger.warning("Rota não encontrada: POST %s", path)
        self._send_json({"erro": "Rota não encontrada."}, status=HTTPStatus.NOT_FOUND)

    def _check_auth(self) -> bool:
        provided = self.headers.get("X-API-Key", "")
        if not hmac.compare_digest(provided, self.api_key or ""):
            logger.warning("Falha de autenticação: %s", self.address_string())
            self._send_json({"erro": "Autenticacao necessaria. Envie o header X-API-Key."}, status=HTTPStatus.UNAUTHORIZED)
            return False
        return True

    def log_message(self, format: str, *args) -> None:
        logger.info("%s - %s", self.address_string(), format % args)

    def _handle_audit_upload(self) -> None:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length > self.max_upload_bytes:
                self._send_json(
                    {"erro": f"Arquivo muito grande. Limite: {self.max_upload_bytes // (1024 * 1024)} MB."},
                    status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                )
                return
            form = self._read_multipart_form()
            cliente = _form_text(form, "cliente", "Cliente sem nome")
            periodo = _form_text(form, "periodo", "Periodo nao informado")
            cnpj = _form_text(form, "cnpj", "")
            atividade = _form_text(form, "atividade", self.atividade)
            uploaded_file = form.get("balancete")

            if not isinstance(uploaded_file, UploadedFile) or not uploaded_file.content:
                self._send_json({"erro": "Envie um arquivo no campo 'balancete'."}, status=HTTPStatus.BAD_REQUEST)
                return

            logger.info("Processando auditoria: cliente=%s periodo=%s arquivo=%s", cliente, periodo, uploaded_file.filename)
            outcome = process_quarterly_upload(
                uploaded_file,
                cliente=cliente,
                periodo=periodo,
                cnpj=cnpj,
                atividade=atividade,
                regime_tributario=self.regime_tributario or "Simples Nacional",
                storage=self._storage(),
            )
            self._send_json(outcome.payload)
            logger.info(
                "Auditoria concluida: id=%s nivel=%s score=%d achados=%d",
                outcome.storage_id,
                outcome.risk_level,
                outcome.score,
                outcome.findings_count,
            )
        except ValueError as exc:
            logger.warning("Erro de validacao: %s", exc)
            self._send_json({"erro": str(exc)}, status=HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            logger.error("Erro inesperado: %s", exc, exc_info=True)
            self._send_json({"erro": f"Erro inesperado: {exc}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def _handle_annual_upload(self) -> None:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length > self.max_upload_bytes * 4:
                self._send_json(
                    {"erro": f"Arquivos muito grandes. Limite anual: {(self.max_upload_bytes * 4) // (1024 * 1024)} MB."},
                    status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                )
                return

            form = self._read_multipart_form()
            manifest_text = _form_text(form, "manifest", "")
            if not manifest_text:
                self._send_json({"erro": "Envie o campo 'manifest' com os trimestres."}, status=HTTPStatus.BAD_REQUEST)
                return

            manifest = json.loads(manifest_text)
            quarters = manifest.get("trimestres") if isinstance(manifest, dict) else None
            if not isinstance(quarters, list) or not quarters:
                self._send_json({"erro": "O manifest deve conter a lista 'trimestres'."}, status=HTTPStatus.BAD_REQUEST)
                return
            if len(quarters) > 4:
                self._send_json({"erro": "Informe no máximo 4 trimestres para a análise anual."}, status=HTTPStatus.BAD_REQUEST)
                return

            annual_payload = build_uploaded_annual_payload(
                form,
                quarters,
                default_atividade=self.atividade,
                regime_tributario=self.regime_tributario or "Simples Nacional",
            )
            self._send_json(annual_payload)
            logger.info("Auditoria anual concluida: trimestres=%d", len(quarters))
        except json.JSONDecodeError as exc:
            logger.warning("Manifest anual invalido: %s", exc)
            self._send_json({"erro": "Manifest anual inválido. Envie JSON válido."}, status=HTTPStatus.BAD_REQUEST)
        except ValueError as exc:
            logger.warning("Erro de validacao anual: %s", exc)
            self._send_json({"erro": str(exc)}, status=HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            logger.error("Erro inesperado na auditoria anual: %s", exc, exc_info=True)
            self._send_json({"erro": f"Erro inesperado: {exc}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def _handle_audit_list(self, query: dict[str, list[str]]) -> None:
        try:
            cnpj = _query_text(query, "cnpj")
            ano = _query_int(query, "ano")
            items = self._storage().list_quarterly_audits(cnpj=cnpj, ano=ano)
            self._send_json(
                {
                    "items": items,
                    "total": len(items),
                    "db_schema_version": DB_SCHEMA_VERSION,
                }
            )
        except ValueError as exc:
            self._send_json({"erro": str(exc)}, status=HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            logger.error("Erro ao listar auditorias: %s", exc, exc_info=True)
            self._send_json({"erro": f"Erro inesperado: {exc}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def _handle_saved_annual_generation(self, query: dict[str, list[str]]) -> None:
        try:
            payload = self._read_json_body()
            cnpj = _query_text(query, "cnpj") or str(payload.get("cnpj") or "")
            ano = _query_int(query, "ano") or _payload_int(payload, "ano")
            if not cnpj:
                self._send_json({"erro": "Informe o CNPJ para gerar a análise anual salva."}, status=HTTPStatus.BAD_REQUEST)
                return
            if ano is None:
                self._send_json({"erro": "Informe o ano para gerar a análise anual salva."}, status=HTTPStatus.BAD_REQUEST)
                return

            annual_sources = self._storage().annual_sources(cnpj=cnpj, ano=ano)
            if not annual_sources:
                self._send_json({"erro": "Nenhum trimestre salvo encontrado para o CNPJ e ano informados."}, status=HTTPStatus.NOT_FOUND)
                return

            annual_payload = build_annual_comparison(annual_sources)
            self._storage().save_annual_audit(cnpj=cnpj, ano=ano, payload=annual_payload)
            self._send_json(annual_payload)
            logger.info("Auditoria anual salva gerada: cnpj=%s ano=%s trimestres=%d", cnpj, ano, len(annual_sources))
        except json.JSONDecodeError:
            self._send_json({"erro": "Envie JSON válido no corpo da requisição ou use cnpj/ano na URL."}, status=HTTPStatus.BAD_REQUEST)
        except ValueError as exc:
            logger.warning("Erro de validacao anual salva: %s", exc)
            self._send_json({"erro": str(exc)}, status=HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            logger.error("Erro inesperado ao gerar auditoria anual salva: %s", exc, exc_info=True)
            self._send_json({"erro": f"Erro inesperado: {exc}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def _handle_latest_annual(self, query: dict[str, list[str]]) -> None:
        try:
            cnpj = _query_text(query, "cnpj")
            ano = _query_int(query, "ano")
            if not cnpj:
                self._send_json({"erro": "Informe o CNPJ para consultar a análise anual salva."}, status=HTTPStatus.BAD_REQUEST)
                return
            if ano is None:
                self._send_json({"erro": "Informe o ano para consultar a análise anual salva."}, status=HTTPStatus.BAD_REQUEST)
                return

            payload = self._storage().latest_annual_audit(cnpj=cnpj, ano=ano)
            if payload is None:
                self._send_json({"erro": "Nenhuma análise anual salva encontrada para o CNPJ e ano informados."}, status=HTTPStatus.NOT_FOUND)
                return
            self._send_json(payload)
        except ValueError as exc:
            self._send_json({"erro": str(exc)}, status=HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            logger.error("Erro ao consultar auditoria anual: %s", exc, exc_info=True)
            self._send_json({"erro": f"Erro inesperado: {exc}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def _read_multipart_form(self) -> dict[str, str | UploadedFile]:
        return read_multipart_form(self.headers, self.rfile)

    def _read_json_body(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0") or "0")
        if content_length <= 0:
            return {}

        body = self.rfile.read(content_length)
        if not body.strip():
            return {}
        payload = json.loads(body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("O corpo JSON deve ser um objeto.")
        return payload

    def _storage(self) -> AuditStorage:
        return AuditStorage(self.db_path)

    def _send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        _send_json_response(self, payload, self._send_cors_headers, status)

    def _send_html(self, content: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        _send_html_response(self, content, self._send_cors_headers, status)

    def _send_static(self, path: str) -> None:
        _send_static_response(self, path, self._send_cors_headers, lambda payload, status: self._send_json(payload, status=status))


def run_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    api_key: str | None = None,
    cors_origin: str = "*",
    regime_tributario: str | None = None,
    atividade: str = "servicos",
    db_path: str | None = None,
    allow_unsafe_network: bool = False,
) -> None:
    _validate_runtime_security(host, api_key, cors_origin, allow_unsafe_network)
    AuditApiHandler.api_key = api_key
    AuditApiHandler.cors_origin = cors_origin
    AuditApiHandler.regime_tributario = regime_tributario
    AuditApiHandler.atividade = atividade
    AuditApiHandler.db_path = db_path
    server = ThreadingHTTPServer((host, port), AuditApiHandler)
    logger.info("Servidor iniciado em http://%s:%d", host, port)
    logger.info("Regime tributario: %s", regime_tributario or "Simples Nacional (padrao)")
    logger.info("Atividade/conjunto de regras: %s", atividade)
    logger.info("CORS permitido para: %s", cors_origin)
    logger.info("Banco de dados local: %s", db_path or os.environ.get("AUDIT_DB_PATH") or "data/auditoria.sqlite")
    if api_key:
        logger.info("Autenticacao por API key: habilitada.")
    if allow_unsafe_network:
        logger.warning("Modo de rede inseguro habilitado explicitamente.")
    server.serve_forever()


def main() -> None:
    args = _parse_args()
    _setup_logging(args.verbose)
    run_server(
        host=args.host,
        port=args.port,
        api_key=args.api_key or os.environ.get("AUDIT_API_KEY"),
        cors_origin=args.cors_origin or os.environ.get("AUDIT_CORS_ORIGIN") or "*",
        regime_tributario=args.regime_tributario,
        atividade=args.atividade,
        db_path=args.db_path,
        allow_unsafe_network=args.allow_unsafe_network,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        Path("api_error.log").write_text(traceback.format_exc(), encoding="utf-8")
        raise

