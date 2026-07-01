from __future__ import annotations

import argparse
import json
import logging
import os
import traceback
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse
from pathlib import Path

from .audit import run_quarterly_audit
from .parser import read_trial_balance_upload
from .serializers import audit_result_to_dict

logger = logging.getLogger(__name__)
_STATIC_DIR = Path(__file__).with_name("static")


@dataclass(frozen=True)
class UploadedFile:
    filename: str
    content: bytes


class AuditApiHandler(BaseHTTPRequestHandler):
    use_ai: bool = True
    api_key: str | None = None
    ai_api_key: str | None = None
    regime_tributario: str | None = None
    atividade: str = "servicos"
    max_upload_bytes: int = 10 * 1024 * 1024

    def do_GET(self) -> None:
        path = urlparse(self.path).path

        if path == "/":
            self._send_html(_index_html())
            return

        if path.startswith("/static/"):
            self._send_static(path)
            return

        if path == "/health":
            self._send_json({"status": "ok"})
            return

        if path == "/api/auditorias/schema":
            self._send_json(_schema_summary_definition())
            return

        logger.warning("Rota não encontrada: GET %s", path)
        self._send_json({"erro": "Rota não encontrada."}, status=HTTPStatus.NOT_FOUND)

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_cors_headers()
        self.end_headers()

    def _send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-API-Key")

    def do_POST(self) -> None:
        path = urlparse(self.path).path

        if path == "/api/auditorias":
            if self.api_key and not self._check_auth():
                return
            self._handle_audit_upload()
            return

        logger.warning("Rota não encontrada: POST %s", path)
        self._send_json({"erro": "Rota não encontrada."}, status=HTTPStatus.NOT_FOUND)

    def _check_auth(self) -> bool:
        provided = self.headers.get("X-API-Key", "")
        if not provided or provided != self.api_key:
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
            balance = read_trial_balance_upload(
                uploaded_file.filename,
                uploaded_file.content,
                cliente=cliente,
                periodo=periodo,
                cnpj=cnpj,
            )
            result = run_quarterly_audit(
                balance,
                regime_tributario=self.regime_tributario or "Simples Nacional",
                atividade=atividade,
            )
            self._send_json(audit_result_to_dict(result))
            logger.info("Auditoria concluida: nivel=%s score=%d achados=%d", result.nivel_geral.value, result.pontuacao_total, len(result.achados))
        except ValueError as exc:
            logger.warning("Erro de validacao: %s", exc)
            self._send_json({"erro": str(exc)}, status=HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            logger.error("Erro inesperado: %s", exc, exc_info=True)
            self._send_json({"erro": f"Erro inesperado: {exc}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def _read_multipart_form(self) -> dict[str, str | UploadedFile]:
        content_type = self.headers.get("Content-Type", "")
        if not content_type.startswith("multipart/form-data"):
            raise ValueError("A API espera multipart/form-data.")

        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length)
        raw_message = (
            f"Content-Type: {content_type}\r\n"
            "MIME-Version: 1.0\r\n"
            "\r\n"
        ).encode("utf-8") + body

        message = BytesParser(policy=policy.default).parsebytes(raw_message)
        form: dict[str, str | UploadedFile] = {}

        for part in message.iter_parts():
            name = part.get_param("name", header="content-disposition")
            if not name:
                continue

            payload = part.get_payload(decode=True) or b""
            filename = part.get_filename()
            if filename:
                form[name] = UploadedFile(filename=filename, content=payload)
                continue

            charset = part.get_content_charset() or "utf-8-sig"
            form[name] = payload.decode(charset, errors="replace")

        return form

    def _send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        content = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._send_cors_headers()
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _send_html(self, content: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self._send_cors_headers()
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_static(self, path: str) -> None:
        requested = unquote(path.removeprefix("/static/"))
        target = (_STATIC_DIR / requested).resolve()
        static_root = _STATIC_DIR.resolve()

        if not target.is_relative_to(static_root) or not target.is_file():
            logger.warning("Arquivo estatico nao encontrado: %s", path)
            self._send_json({"erro": "Arquivo nao encontrado."}, status=HTTPStatus.NOT_FOUND)
            return

        content_type = _static_content_type(target)
        content = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self._send_cors_headers()
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def run_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    api_key: str | None = None,
    regime_tributario: str | None = None,
    atividade: str = "servicos",
) -> None:
    AuditApiHandler.api_key = api_key
    AuditApiHandler.regime_tributario = regime_tributario
    AuditApiHandler.atividade = atividade
    server = ThreadingHTTPServer((host, port), AuditApiHandler)
    logger.info("Servidor iniciado em http://%s:%d", host, port)
    logger.info("Regime tributario: %s", regime_tributario or "Simples Nacional (padrao)")
    logger.info("Atividade/conjunto de regras: %s", atividade)
    if api_key:
        logger.info("Autenticacao por API key: habilitada.")
    server.serve_forever()


def main() -> None:
    args = _parse_args()
    _setup_logging(args.verbose)
    run_server(
        host=args.host,
        port=args.port,
        api_key=args.api_key or os.environ.get("AUDIT_API_KEY"),
        regime_tributario=args.regime_tributario,
        atividade=args.atividade,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="API local para pre-auditoria fiscal.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--api-key", help="Chave da API para autenticacao (ou use AUDIT_API_KEY).")
    parser.add_argument("--regime-tributario", default=None, help="Regime tributario (padrao: Simples Nacional).")
    parser.add_argument(
        "--atividade",
        default="servicos",
        choices=["servicos", "comercio", "comercio_servicos"],
        help="Conjunto de regras do Simples Nacional.",
    )
    parser.add_argument("--verbose", action="store_true", help="Ativar logging detalhado.")
    return parser.parse_args()


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _form_text(form: dict[str, str | UploadedFile], field: str, default: str) -> str:
    value = form.get(field)
    return value.strip() if isinstance(value, str) and value.strip() else default


def _schema_summary_definition() -> dict:
    return {
        "identificacao_empresa": {
            "cnpj": "str",
            "regime_tributario": "str",
            "periodo_analisado": "str",
        },
        "resumo_analise": {
            "empresa": "str",
            "base_analise": "JSON de auditoria trimestral",
            "total_regras_verificadas": "int",
            "total_regras_acionadas": "int",
            "risco_geral": "str (alto | medio | baixo)",
            "pontuacao_total": "int",
            "achados_por_severidade": {
                "alta": "int",
                "media": "int",
                "baixa": "int",
            },
            "principais_pontos": ["str"],
        },
        "principais_achados": [
            {
                "codigo": "str",
                "severidade": "str (alta | media | baixa)",
                "achado": "str",
                "evidencia_identificada": "str | null",
                "impacto_tecnico": "str",
                "pontuacao": "int",
                "norma_fundamento": ["str"],
            }
        ],
        "fundamentacao_tecnica_resumida": {
            "normas_aplicaveis": ["str"],
            "texto_resumido": "str",
            "observacoes_tecnicas": ["str"],
        },
        "conclusao_tecnica": {
            "risco_geral": "str (alto | medio | baixo)",
            "conclusao_sugerida": "str",
            "ressalva_base_json": "bool",
            "necessita_validacao_documental": "bool",
            "texto_conclusivo": "str",
        },
        "recomendacoes_tecnicas": [
            {
                "ordem": "int",
                "descricao": "str",
                "area_relacionada": "str (fiscal | contábil | trabalhista | societária | financeira | documental)",
                "prioridade": "str (alta | media | baixa)",
            }
        ],
        "metadados": {
            "data_analise": "str (ISO 8601)",
            "versao_schema": "str",
            "versao_regras": "str",
            "conjunto_regras": "str (simples_servicos | simples_comercio | simples_comercio_servicos)",
        },
    }


def _index_html() -> str:
    return _read_static_text("index.html")


def _read_static_text(filename: str) -> str:
    return (_STATIC_DIR / filename).read_text(encoding="utf-8")


def _static_content_type(path: Path) -> str:
    if path.suffix == ".css":
        return "text/css; charset=utf-8"
    if path.suffix == ".js":
        return "text/javascript; charset=utf-8"
    if path.suffix == ".svg":
        return "image/svg+xml; charset=utf-8"
    if path.suffix == ".html":
        return "text/html; charset=utf-8"
    return "application/octet-stream"


if __name__ == "__main__":
    try:
        main()
    except Exception:
        Path("api_error.log").write_text(traceback.format_exc(), encoding="utf-8")
        raise

