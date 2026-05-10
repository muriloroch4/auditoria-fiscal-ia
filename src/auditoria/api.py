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
from urllib.parse import urlparse
from pathlib import Path

from .audit import run_quarterly_audit
from .parser import read_trial_balance_upload
from .report_ai import generate_markdown_report
from .serializers import audit_result_to_dict

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UploadedFile:
    filename: str
    content: bytes


class AuditApiHandler(BaseHTTPRequestHandler):
    use_ai: bool = True
    api_key: str | None = None
    ai_api_key: str | None = None
    max_upload_bytes: int = 10 * 1024 * 1024

    def do_GET(self) -> None:
        path = urlparse(self.path).path

        if path == "/":
            self._send_html(_index_html())
            return

        if path == "/health":
            self._send_json({"status": "ok"})
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
            )
            result = run_quarterly_audit(balance)
            report = generate_markdown_report(result, use_ai=self.use_ai, api_key=self.ai_api_key)
            self._send_json(audit_result_to_dict(result, report_markdown=report))
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


def run_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    use_ai: bool = True,
    api_key: str | None = None,
    ai_api_key: str | None = None,
) -> None:
    AuditApiHandler.use_ai = use_ai
    AuditApiHandler.api_key = api_key
    AuditApiHandler.ai_api_key = ai_api_key
    server = ThreadingHTTPServer((host, port), AuditApiHandler)
    logger.info("Servidor iniciado em http://%s:%d", host, port)
    if use_ai:
        logger.info("Geracao de relatorio via IA: habilitada.")
    else:
        logger.info("Geracao de relatorio via IA: desabilitada (modo padrao).")
    if api_key:
        logger.info("Autenticacao por API key: habilitada.")
    server.serve_forever()


def main() -> None:
    args = _parse_args()
    _setup_logging(args.verbose)
    run_server(
        host=args.host,
        port=args.port,
        use_ai=args.use_ai,
        api_key=args.api_key or os.environ.get("AUDIT_API_KEY"),
        ai_api_key=args.openrouter_api_key,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="API local para pre-auditoria fiscal.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-ai", action="store_false", dest="use_ai", default=True, help="Desabilitar IA e usar relatorio padrao.")
    parser.add_argument("--api-key", help="Chave da API para autenticacao (ou use AUDIT_API_KEY).")
    parser.add_argument("--openrouter-api-key", help="Chave OpenRouter para relatorio por IA (ou use OPENROUTER_API_KEY).")
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


def _index_html() -> str:
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Auditoria Fiscal IA</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f4f6fa;
      --text: #172033;
      --muted: #5b6475;
      --line: #d9deea;
      --panel: #ffffff;
      --accent: #1f7a6d;
      --accent-strong: #145c52;
      --accent-light: #d1fae5;
      --danger: #b91c1c;
      --danger-bg: #fee2e2;
      --warn: #a16207;
      --warn-bg: #fef3c7;
      --low: #065f46;
      --low-bg: #d1fae5;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
    }}
    .app {{
      width: min(1200px, calc(100vw - 24px));
      margin: 24px auto;
      display: grid;
      grid-template-columns: 340px 1fr;
      gap: 20px;
      align-items: start;
    }}
    .sidebar {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 24px;
      position: sticky;
      top: 24px;
    }}
    .sidebar h1 {{
      font-size: 22px;
      margin-bottom: 8px;
      color: var(--accent-strong);
    }}
    .sidebar .tagline {{
      color: var(--muted);
      font-size: 13px;
      margin-bottom: 20px;
    }}
    label {{
      display: block;
      margin: 14px 0 6px;
      font-weight: 600;
      font-size: 13px;
    }}
    input[type="text"] {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px 12px;
      font-size: 14px;
    }}
    input[type="text"]:focus {{ outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px rgba(31,122,109,.12); }}
    input[type="file"] {{
      width: 100%;
      padding: 10px;
      font-size: 13px;
      border: 1px dashed var(--line);
      border-radius: 8px;
      background: #fafbfe;
    }}
    .btn {{
      width: 100%;
      margin-top: 20px;
      border: 0;
      border-radius: 8px;
      padding: 12px;
      background: var(--accent);
      color: #fff;
      font-weight: 700;
      font-size: 14px;
      cursor: pointer;
    }}
    .btn:hover {{ background: var(--accent-strong); }}
    .btn:disabled {{ opacity: .6; cursor: wait; }}

    .main {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 12px;
      min-height: 500px;
      display: flex;
      flex-direction: column;
    }}
    .main-header {{
      padding: 18px 24px;
      border-bottom: 1px solid var(--line);
      display: flex;
      align-items: center;
      gap: 12px;
    }}
    .main-header h2 {{ font-size: 16px; }}
    .score {{ display: flex; gap: 8px; flex-wrap: wrap; margin-left: auto; }}
    .pill {{
      border-radius: 999px;
      padding: 5px 12px;
      font-size: 12px;
      font-weight: 700;
    }}
    .pill.alto {{ background: var(--danger-bg); color: var(--danger); }}
    .pill.medio {{ background: var(--warn-bg); color: var(--warn); }}
    .pill.baixo {{ background: var(--low-bg); color: var(--low); }}
    .pill.info {{ background: var(--accent-light); color: var(--accent-strong); }}

    .report {{
      padding: 24px;
      flex: 1;
      overflow-y: auto;
    }}
    .report-empty {{
      display: flex;
      align-items: center;
      justify-content: center;
      height: 400px;
      color: var(--muted);
      font-size: 15px;
    }}

    .md h1 {{ font-size: 22px; color: var(--accent-strong); margin: 0 0 8px; padding-bottom: 8px; border-bottom: 2px solid var(--accent); }}
    .md h2 {{ font-size: 16px; color: var(--accent); margin: 24px 0 10px; padding: 6px 12px; background: rgba(31,122,109,.08); border-radius: 6px; }}
    .md h3 {{ font-size: 14px; color: var(--text); margin: 18px 0 8px; }}
    .md p {{ margin: 8px 0; font-size: 13.5px; }}
    .md ul {{ margin: 6px 0 10px 20px; font-size: 13.5px; }}
    .md li {{ margin: 3px 0; }}
    .md table {{ border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 13px; }}
    .md th {{ background: var(--accent); color: #fff; text-align: left; padding: 7px 12px; font-size: 12px; }}
    .md td {{ padding: 7px 12px; border-bottom: 1px solid var(--line); }}
    .md tr:nth-child(even) td {{ background: #f8fafc; }}
    .md blockquote {{ border-left: 3px solid var(--accent); background: #f0fdf9; padding: 10px 14px; margin: 10px 0; color: var(--muted); font-style: italic; font-size: 13px; border-radius: 0 6px 6px 0; }}
    .md hr {{ border: none; border-top: 1px solid var(--line); margin: 16px 0; }}
    .md strong {{ color: var(--text); }}
    .md code {{ background: #f1f5f9; padding: 1px 5px; border-radius: 4px; font-size: 12px; }}

    @media (max-width: 860px) {{
      .app {{ grid-template-columns: 1fr; }}
      .sidebar {{ position: static; }}
    }}
  </style>
</head>
<body>
  <div class="app">
    <aside class="sidebar">
      <h1>Auditoria Fiscal IA</h1>
      <p class="tagline">Pre-auditoria para Simples Nacional - Servicos</p>
      <form id="audit-form">
        <label for="cliente">Cliente</label>
        <input type="text" id="cliente" name="cliente" value="Cliente Exemplo" required>
        <label for="periodo">Periodo</label>
        <input type="text" id="periodo" name="periodo" value="2026-T1" required>
        <label for="balancete">Balancete (CSV, XLSX, XLS)</label>
        <input type="file" id="balancete" name="balancete" accept=".csv,.xlsx,.xls,text/csv,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" required>
        <button class="btn" id="submit-button" type="submit">Gerar Auditoria</button>
      </form>
    </aside>
    <div class="main">
      <div class="main-header">
        <h2>Relatorio</h2>
        <div id="score" class="score"></div>
      </div>
      <div id="output" class="report">
        <div class="report-empty">Aguardando upload do balancete.</div>
      </div>
    </div>
  </div>

  <script>
    const form = document.querySelector("#audit-form");
    const output = document.querySelector("#output");
    const score = document.querySelector("#score");
    const button = document.querySelector("#submit-button");

    function renderMarkdown(text) {{
      const lines = text.split("\\n");
      let html = "";
      let i = 0;

      function processInline(t) {{
        return t
          .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
          .replace(/`([^`]+)`/g, "<code>$1</code>");
      }}

      while (i < lines.length) {{
        const line = lines[i];

        if (line.trim() === "") {{ i++; continue; }}
        if (line.trim() === "---") {{ html += "<hr>"; i++; continue; }}

        if (line.startsWith("### ")) {{
          html += "<h3>" + processInline(line.slice(4)) + "</h3>";
          i++;
        }} else if (line.startsWith("## ")) {{
          html += "<h2>" + processInline(line.slice(3)) + "</h2>";
          i++;
        }} else if (line.startsWith("# ")) {{
          html += "<h1>" + processInline(line.slice(2)) + "</h1>";
          i++;
        }} else if (line.startsWith("> ")) {{
          let quote = "";
          while (i < lines.length && lines[i].startsWith("> ")) {{
            quote += (quote ? " " : "") + processInline(lines[i].slice(2));
            i++;
          }}
          html += "<blockquote>" + quote + "</blockquote>";
        }} else if (line.startsWith("- **") && line.includes(":**")) {{
          const m = line.match(/^- \*\*(.+?)\*\*:?\s*(.*)$/);
          if (m) {{
            html += "<p><strong>" + m[1] + ":</strong> " + processInline(m[2]) + "</p>";
          }} else {{
            html += "<p>" + processInline(line.slice(2)) + "</p>";
          }}
          i++;
        }} else if (line.startsWith("- ")) {{
          html += "<ul>";
          while (i < lines.length && lines[i].startsWith("- ")) {{
            html += "<li>" + processInline(lines[i].slice(2)) + "</li>";
            i++;
          }}
          html += "</ul>";
        }} else if (line.startsWith("|") && line.trim().endsWith("|")) {{
          let rows = [];
          while (i < lines.length && lines[i].startsWith("|") && lines[i].trim().endsWith("|")) {{
            const raw = lines[i].trim().slice(1, -1);
            const cells = raw.split("|").map(c => c.trim());
            if (!cells.every(c => /^[-:]+$/.test(c))) {{
              rows.push(cells);
            }}
            i++;
          }}
          if (rows.length > 0) {{
            html += "<table>";
            html += "<thead><tr>" + rows[0].map(c => "<th>" + c + "</th>").join("") + "</tr></thead>";
            if (rows.length > 1) {{
              html += "<tbody>" + rows.slice(1).map((cells, idx) =>
                "<tr>" + cells.map(c => "<td>" + c + "</td>").join("") + "</tr>"
              ).join("") + "</tbody>";
            }}
            html += "</table>";
          }}
        }} else {{
          html += "<p>" + processInline(line) + "</p>";
          i++;
        }}
      }}
      return html;
    }}

    function renderReport(raw) {{
      output.innerHTML = "<div class='md'>" + renderMarkdown(raw) + "</div>";
    }}

    form.addEventListener("submit", async (event) => {{
      event.preventDefault();
      button.disabled = true;
      output.innerHTML = "<div class='report-empty'>Processando...</div>";
      score.innerHTML = "";
      try {{
        const response = await fetch("/api/auditorias", {{ method: "POST", body: new FormData(form) }});
        const data = await response.json();
        if (!response.ok) throw new Error(data.erro || "Falha ao gerar auditoria.");
        score.innerHTML =
          `<span class="pill ${{data.nivel_geral}}">Risco: ${{data.nivel_geral.toUpperCase()}}</span>` +
          `<span class="pill info">Pontuacao: ${{data.pontuacao_total}}</span>` +
          `<span class="pill info">Achados: ${{data.achados.length}}</span>`;
        renderReport(data.relatorio_markdown);
      }} catch (error) {{
        output.innerHTML = `<div class='report'><p style="color:var(--danger)">${{error.message}}</p></div>`;
      }} finally {{
        button.disabled = false;
      }}
    }});
  </script>
</body>
</html>"""


if __name__ == "__main__":
    try:
        main()
    except Exception:
        Path("api_error.log").write_text(traceback.format_exc(), encoding="utf-8")
        raise
