from __future__ import annotations

import argparse
import json
import logging
import os
import traceback
from dataclasses import dataclass
from decimal import Decimal
from email import policy
from email.parser import BytesParser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from .annual import build_annual_comparison, build_rbt12_context
from .audit import run_quarterly_audit
from .models import AuditResult
from .parser import read_trial_balance_upload
from .schema_loader import load_json_schema
from .serializers import audit_result_to_dict
from .storage import DB_SCHEMA_VERSION, AuditStorage, file_sha256, infer_year_quarter

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
        self.send_header("Access-Control-Allow-Origin", "*")
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
            payload = audit_result_to_dict(result)
            annual_source = _audit_result_to_annual_source(result)
            storage = self._storage()
            storage_id = storage.save_quarterly_audit(
                result,
                payload,
                annual_source,
                filename=uploaded_file.filename,
                file_hash=file_sha256(uploaded_file.content),
                atividade=atividade,
            )

            rbt12_context = _saved_rbt12_context(storage, result.cnpj, result.periodo)
            if rbt12_context.get("dados_suficientes"):
                result = run_quarterly_audit(
                    balance,
                    regime_tributario=self.regime_tributario or "Simples Nacional",
                    atividade=atividade,
                    contexto_rbt12=rbt12_context,
                )
                payload = audit_result_to_dict(result)
                annual_source = _audit_result_to_annual_source(result)
                storage_id = storage.save_quarterly_audit(
                    result,
                    payload,
                    annual_source,
                    filename=uploaded_file.filename,
                    file_hash=file_sha256(uploaded_file.content),
                    atividade=atividade,
                )
            self._send_json(payload)
            logger.info(
                "Auditoria concluida: id=%s nivel=%s score=%d achados=%d",
                storage_id,
                result.nivel_geral.value,
                result.pontuacao_total,
                len(result.achados),
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

            annual_sources = []
            for index, quarter in enumerate(quarters, start=1):
                if not isinstance(quarter, dict):
                    raise ValueError(f"Trimestre {index}: item inválido no manifest.")
                field = str(quarter.get("field") or f"balancete_{index - 1}")
                uploaded_file = form.get(field)
                if not isinstance(uploaded_file, UploadedFile) or not uploaded_file.content:
                    raise ValueError(f"Trimestre {index}: arquivo não encontrado no campo '{field}'.")

                cliente = str(quarter.get("cliente") or "Cliente sem nome")
                periodo = str(quarter.get("periodo") or f"2025-T{index}")
                cnpj = str(quarter.get("cnpj") or "")
                atividade = str(quarter.get("atividade") or self.atividade)

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
                annual_sources.append(_audit_result_to_annual_source(result))

            annual_payload = build_annual_comparison(annual_sources)
            self._send_json(annual_payload)
            logger.info("Auditoria anual concluida: trimestres=%d", len(annual_sources))
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
            raw_name = part.get_param("name", header="content-disposition")
            if not isinstance(raw_name, str) or not raw_name:
                continue
            name = raw_name

            raw_payload = part.get_payload(decode=True)
            payload = raw_payload if isinstance(raw_payload, bytes) else b""
            filename = part.get_filename()
            if filename:
                form[name] = UploadedFile(filename=filename, content=payload)
                continue

            charset = part.get_content_charset() or "utf-8-sig"
            form[name] = payload.decode(charset, errors="replace")

        return form

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
        content = json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default).encode("utf-8")
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
    db_path: str | None = None,
) -> None:
    AuditApiHandler.api_key = api_key
    AuditApiHandler.regime_tributario = regime_tributario
    AuditApiHandler.atividade = atividade
    AuditApiHandler.db_path = db_path
    server = ThreadingHTTPServer((host, port), AuditApiHandler)
    logger.info("Servidor iniciado em http://%s:%d", host, port)
    logger.info("Regime tributario: %s", regime_tributario or "Simples Nacional (padrao)")
    logger.info("Atividade/conjunto de regras: %s", atividade)
    logger.info("Banco de dados local: %s", db_path or os.environ.get("AUDIT_DB_PATH") or "data/auditoria.sqlite")
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
        db_path=args.db_path,
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
    parser.add_argument("--db-path", help="Caminho do SQLite local (ou use AUDIT_DB_PATH).")
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


def _query_text(query: dict[str, list[str]], field: str) -> str:
    values = query.get(field) or []
    value = values[0] if values else ""
    return str(value or "").strip()


def _query_int(query: dict[str, list[str]], field: str) -> int | None:
    value = _query_text(query, field)
    if not value:
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"O parâmetro '{field}' deve ser numérico.") from exc


def _payload_int(payload: dict[str, Any], field: str) -> int | None:
    value = payload.get(field)
    if value in (None, ""):
        return None
    try:
        return int(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"O campo '{field}' deve ser numérico.") from exc


def _saved_rbt12_context(storage: AuditStorage, cnpj: str, periodo: str) -> dict[str, Any]:
    if not cnpj:
        return {}
    ano, _ = infer_year_quarter(periodo)
    sources = storage.annual_sources(cnpj=cnpj, ano=ano)
    return build_rbt12_context(sources)


def _json_default(value):
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _audit_result_to_annual_source(result: AuditResult) -> dict:
    return {
        "identificacao": {
            "cliente": result.cliente,
            "cnpj": result.cnpj,
            "regime_tributario": result.regime_tributario,
            "periodo": result.periodo,
        },
        "risco": {
            "nivel_geral": result.nivel_geral.value,
            "pontuacao_total": result.pontuacao_total,
            "modalidade_opiniao_sugerida": "com_ressalva" if result.achados else "sem_ressalva",
        },
        "metricas": _annual_metric_entries(result),
        "achados": [
            {
                "codigo": finding.codigo,
                "titulo": finding.titulo,
                "nivel": finding.nivel.value,
                "pontuacao": finding.pontuacao,
                "descricao": finding.descricao,
                "evidencia": finding.evidencia,
                "recomendacao": finding.recomendacao,
                "normas_aplicaveis": list(finding.normas_aplicaveis),
            }
            for finding in result.achados
        ],
    }


def _annual_metric_entries(result: AuditResult) -> dict:
    metricas: dict[str, dict] = {}
    for key, value in result.metricas_valores.items():
        if key == "indicadores_derivados" or not isinstance(value, (int, float)):
            continue
        metricas[key] = {
            "valor": value,
            "formatado": result.resumo_metricas.get(key, str(value)),
        }
    return metricas


def _schema_summary_definition() -> dict:
    return load_json_schema("trimestral")


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

