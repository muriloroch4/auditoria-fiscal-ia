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
    regime_tributario: str | None = None
    max_upload_bytes: int = 10 * 1024 * 1024

    def do_GET(self) -> None:
        path = urlparse(self.path).path

        if path == "/":
            self._send_html(_index_html())
            return

        if path == "/health":
            self._send_json({"status": "ok"})
            return

        if path == "/api/auditorias/schema":
            self._send_json(_schema_v2_definition())
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
            result = run_quarterly_audit(balance, regime_tributario=self.regime_tributario or "Simples Nacional")
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


def run_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    api_key: str | None = None,
    regime_tributario: str | None = None,
) -> None:
    AuditApiHandler.api_key = api_key
    AuditApiHandler.regime_tributario = regime_tributario
    server = ThreadingHTTPServer((host, port), AuditApiHandler)
    logger.info("Servidor iniciado em http://%s:%d", host, port)
    logger.info("Regime tributario: %s", regime_tributario or "Simples Nacional (padrao)")
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
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="API local para pre-auditoria fiscal.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--api-key", help="Chave da API para autenticacao (ou use AUDIT_API_KEY).")
    parser.add_argument("--regime-tributario", default=None, help="Regime tributario (padrao: Simples Nacional).")
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


def _schema_v2_definition() -> dict:
    return {
        "_schema_version": "2.0.0",
        "descricao": "Schema de saída da pré-auditoria fiscal — Simples Nacional (serviços)",
        "meta": {
            "versao_schema": "2.0.0",
            "versao_regras": "str",
            "conjunto_regras": "str",
            "data_analise": "str (ISO 8601)",
            "total_contas_analisadas": "int",
            "total_regras_verificadas": "int",
            "total_regras_acionadas": "int",
        },
        "identificacao": {
            "cliente": "str",
            "cnpj": "str",
            "regime_tributario": "str",
            "periodo": "str",
        },
        "risco": {
            "nivel_geral": "str (alto | medio | baixo)",
            "pontuacao_total": "int",
            "modalidade_opiniao_sugerida": "str (adversa | com_ressalva | sem_ressalva)",
            "classificacao": {
                "achados_alto": "int",
                "achados_medio": "int",
                "achados_baixo": "int",
                "achados_compostos": "int",
            },
            "explicacao_pontuacao": ["str"],
        },
        "metricas": {
            "receita_servicos": {"valor": "float", "formatado": "str"},
            "deducoes_receita": {"valor": "float", "formatado": "str"},
            "tributos_a_recolher": {"valor": "float", "formatado": "str"},
            "tributos_registrados": {"valor": "float", "formatado": "str"},
            "folha_pro_labore": {"valor": "float", "formatado": "str"},
            "despesas_operacionais": {"valor": "float", "formatado": "str"},
            "lucros_distribuidos": {"valor": "float", "formatado": "str"},
            "lucro_apurado_base": {"valor": "float", "formatado": "str"},
            "caixa_e_bancos": {"valor": "float", "formatado": "str"},
            "clientes_recebiveis": {"valor": "float", "formatado": "str"},
            "adiantamentos": {"valor": "float", "formatado": "str"},
            "fornecedores": {"valor": "float", "formatado": "str"},
            "estoques": {"valor": "float", "formatado": "str"},
            "creditos_fiscais": {"valor": "float", "formatado": "str"},
            "emprestimos": {"valor": "float", "formatado": "str"},
            "patrimonio_liquido": {"valor": "float", "formatado": "str"},
            "origem_lucro_apurado": "str",
            "indicadores_derivados": {
                "carga_tributaria_efetiva_percentual": "str",
                "percentual_deducoes_sobre_receita": "str",
                "percentual_folha_sobre_receita": "str",
                "percentual_despesas_sobre_receita": "str",
                "endividamento_bancario_sobre_receita": "str",
                "resultado_positivo": "bool",
            },
        },
        "achados": [
            {
                "codigo": "str",
                "titulo": "str",
                "nivel": "str (alto | medio | baixo)",
                "pontuacao": "int",
                "descricao": "str",
                "evidencia": "dict",
                "recomendacao": "str",
                "normas_aplicaveis": ["str"],
            }
        ],
        "contexto_regime": {
            "regime": "str",
            "faixa_receita_estimada": "str",
            "aliquota_efetiva_esperada": "str",
            "fator_r_calculado": "str | None",
            "fator_r_threshold": "str",
            "sublimite_risco": "bool",
            "observacoes": ["str"],
        },
    }


def _index_html() -> str:
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Auditoria Fiscal IA</title>
  <style>
    :root {{
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
      position: fixed;
      inset: 24px;
      display: flex;
      gap: 20px;
      max-width: 1280px;
      margin: 0 auto;
    }}
    .sidebar {{
      width: 320px;
      min-width: 240px;
      flex-shrink: 0;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 24px;
      overflow-y: auto;
    }}
    .sidebar h1 {{ font-size: 20px; margin-bottom: 4px; color: var(--accent-strong); }}
    .sidebar .tagline {{ color: var(--muted); font-size: 12px; margin-bottom: 18px; }}
    label {{ display: block; margin: 12px 0 4px; font-weight: 600; font-size: 13px; }}
    input[type="text"] {{ width: 100%; border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px; font-size: 14px; }}
    input[type="text"]:focus {{ outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px rgba(31,122,109,.12); }}
    input[type="file"] {{ width: 100%; padding: 10px; font-size: 13px; border: 1px dashed var(--line); border-radius: 8px; background: #fafbfe; }}
    .btn {{ width: 100%; margin-top: 18px; border: 0; border-radius: 8px; padding: 12px; background: var(--accent); color: #fff; font-weight: 700; font-size: 14px; cursor: pointer; }}
    .btn:hover {{ background: var(--accent-strong); }}
    .btn:disabled {{ opacity: .6; cursor: wait; }}

    .main {{
      flex: 1; height: 100%; min-width: 0; min-height: 0;
      background: var(--panel); border: 1px solid var(--line); border-radius: 12px;
      display: flex; flex-direction: column;
    }}
    .main-header {{
      padding: 14px 20px; border-bottom: 1px solid var(--line);
      display: flex; align-items: center; gap: 10px; flex-shrink: 0; flex-wrap: wrap;
    }}
    .main-header h2 {{ font-size: 15px; }}
    .main-header .actions {{ margin-left: auto; display: flex; gap: 6px; align-items: center; }}
    .pill {{ border-radius: 999px; padding: 4px 10px; font-size: 11px; font-weight: 700; white-space: nowrap; }}
    .pill.alto {{ background: var(--danger-bg); color: var(--danger); }}
    .pill.medio {{ background: var(--warn-bg); color: var(--warn); }}
    .pill.baixo {{ background: var(--low-bg); color: var(--low); }}
    .pill.info {{ background: var(--accent-light); color: var(--accent-strong); }}
    .pill.outline {{ background: transparent; border: 1px solid var(--accent); color: var(--accent); cursor: pointer; }}
    .pill.outline:hover {{ background: var(--accent-light); }}

    .report {{
      padding: 20px; flex: 1; min-height: 0; overflow-y: auto;
    }}
    .report-empty {{
      display: flex; align-items: center; justify-content: center;
      min-height: 300px; color: var(--muted); font-size: 14px;
    }}

    /* Dashboard cards */
    .db-section {{ margin-bottom: 20px; }}
    .db-section-title {{ font-size: 13px; font-weight: 700; color: var(--muted); text-transform: uppercase; letter-spacing: .5px; margin-bottom: 10px; }}

    .risk-hero {{
      display: flex; align-items: center; gap: 20px;
      padding: 20px; border-radius: 10px; border: 1px solid var(--line);
    }}
    .risk-hero.alto {{ background: var(--danger-bg); border-color: #fecaca; }}
    .risk-hero.medio {{ background: var(--warn-bg); border-color: #fde68a; }}
    .risk-hero.baixo {{ background: var(--low-bg); border-color: #a7f3d0; }}
    .risk-icon {{ font-size: 36px; line-height: 1; }}
    .risk-info h3 {{ font-size: 16px; margin-bottom: 2px; }}
    .risk-info p {{ font-size: 13px; color: var(--muted); }}
    .risk-stats {{ display: flex; gap: 20px; margin-left: auto; text-align: center; }}
    .risk-stats div {{ min-width: 50px; }}
    .risk-stats .num {{ font-size: 22px; font-weight: 800; display: block; }}
    .risk-stats .lbl {{ font-size: 11px; color: var(--muted); text-transform: uppercase; }}

    .metric-grid {{
      display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 10px;
    }}
    .metric-card {{
      padding: 14px; border: 1px solid var(--line); border-radius: 8px; background: #fafbfe;
    }}
    .metric-card .label {{ font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: .3px; }}
    .metric-card .value {{ font-size: 18px; font-weight: 700; margin-top: 2px; }}
    .metric-card .detail {{ font-size: 11px; color: var(--muted); margin-top: 4px; }}

    .indicators {{ display: flex; gap: 10px; flex-wrap: wrap; }}
    .indicator-badge {{
      padding: 6px 14px; border-radius: 6px; font-size: 12px; font-weight: 600;
      background: var(--accent-light); color: var(--accent-strong);
    }}
    .indicator-badge.ok {{ background: var(--low-bg); color: var(--low); }}
    .indicator-badge.warn {{ background: var(--warn-bg); color: var(--warn); }}
    .indicator-badge.bad {{ background: var(--danger-bg); color: var(--danger); }}

    .findings-table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
    .findings-table th {{ background: var(--accent); color: #fff; text-align: left; padding: 7px 10px; font-size: 11px; text-transform: uppercase; }}
    .findings-table td {{ padding: 8px 10px; border-bottom: 1px solid var(--line); vertical-align: top; }}
    .findings-table tr:hover td {{ background: #f8fafc; }}
    .finding-code {{ font-weight: 700; font-family: monospace; font-size: 11px; white-space: nowrap; }}
    .finding-peer {{ background: rgba(31,122,109,.06); }}
    .finding-peer .finding-code {{ color: var(--accent-strong); }}

    .ctx-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 8px; }}
    .ctx-item {{ padding: 10px; border: 1px solid var(--line); border-radius: 6px; background: #fafbfe; }}
    .ctx-item .lbl {{ font-size: 10px; color: var(--muted); text-transform: uppercase; }}
    .ctx-item .val {{ font-size: 13px; font-weight: 600; margin-top: 1px; }}
    .ctx-obs {{ margin-top: 8px; padding: 10px 14px; background: #fffbeb; border-left: 3px solid var(--warn); border-radius: 4px; font-size: 12px; color: #78350f; }}

    .explain-box {{
      padding: 14px; border: 1px solid var(--line); border-radius: 8px; background: #fafbfe; font-size: 12px; line-height: 1.6;
    }}
    .explain-box p {{ margin: 4px 0; }}

    .toggle-link {{
      font-size: 12px; color: var(--accent); cursor: pointer; text-decoration: underline; user-select: none;
    }}
    .toggle-link:hover {{ color: var(--accent-strong); }}

    .raw-json {{ font-family: monospace; font-size: 11px; white-space: pre-wrap; background: #f1f5f9; padding: 12px; border-radius: 6px; max-height: 400px; overflow: auto; margin-top: 8px; }}

    @media (max-width: 860px) {{
      .app {{ flex-direction: column; }}
      .sidebar {{ width: auto; }}
      .risk-hero {{ flex-wrap: wrap; }}
      .risk-stats {{ margin-left: 0; }}
      .metric-grid {{ grid-template-columns: repeat(2, 1fr); }}
    }}

    @media print {{
      body {{ background: #fff; }}
      .sidebar, .main-header, .toggle-link, .raw-json {{ display: none !important; }}
      .app, .main, .report {{ display: block; height: auto; overflow: visible; }}
      .main {{ width: 100%; }}
      .report {{ padding: 0; }}
      .risk-hero, .metric-card, .ctx-item, .explain-box {{ break-inside: avoid; }}
      .findings-table tr {{ break-inside: avoid; }}
    }}
  </style>
</head>
<body>
  <div class="app">
    <aside class="sidebar">
      <h1>Auditoria Fiscal IA</h1>
      <p class="tagline">Pré-auditoria para Simples Nacional — Serviços</p>
      <form id="audit-form">
        <label for="cliente">Cliente</label>
        <input type="text" id="cliente" name="cliente" value="Cliente Exemplo" required>
        <label for="cnpj">CNPJ</label>
        <input type="text" id="cnpj" name="cnpj" value="00.000.000/0001-00" placeholder="00.000.000/0001-00">
        <label for="periodo">Período</label>
        <input type="text" id="periodo" name="periodo" value="2026-T1" required>
        <label for="balancete">Balancete (CSV, XLSX, XLS)</label>
        <input type="file" id="balancete" name="balancete" accept=".csv,.xlsx,.xls,text/csv,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" required>
        <button class="btn" id="submit-button" type="submit">Gerar Auditoria</button>
      </form>
    </aside>
    <div class="main">
      <div class="main-header">
        <h2>Dashboard</h2>
        <div id="score" class="actions"></div>
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

    function esc(t) {{
      return String(t).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
    }}

    function fmt(d) {{
      if (d && d.formatado) return esc(d.formatado);
      if (typeof d === "number") return d.toLocaleString("pt-BR");
      return esc(String(d ?? ""));
    }}

    function levelIcon(lvl) {{
      return lvl === "alto" ? "&#9888;" : lvl === "medio" ? "&#9881;" : "&#10003;";
    }}

    function pillHtml(lvl) {{
      return `<span class="pill ${{lvl}}">${{lvl.toUpperCase()}}</span>`;
    }}

    function renderDashboard(data) {{
      const r = data.risco || {{}};
      const m = data.metricas || {{}};
      const ident = data.identificacao || {{}};
      const ctx = data.contexto_regime || {{}};
      const achados = data.achados || [];
      const meta = data.meta || {{}};
      const cls = r.classificacao || {{}};
      const lvl = r.nivel_geral || "desconhecido";
      const opiniao = r.modalidade_opiniao_sugerida || "";

      let html = "";

      /* Risk Hero */
      html += `<div class="risk-hero ${{lvl}}">`;
      html += `<div class="risk-icon">${{levelIcon(lvl)}}</div>`;
      html += `<div class="risk-info"><h3>Risco ${{lvl.toUpperCase()}}</h3>`;
      html += `<p>Opinião sugerida: <strong>${{esc(opiniao.replace("_", " "))}}</strong></p></div>`;
      html += `<div class="risk-stats">`;
      html += `<div><span class="num">${{r.pontuacao_total ?? 0}}</span><span class="lbl">Pontos</span></div>`;
      html += `<div><span class="num">${{achados.length}}</span><span class="lbl">Achados</span></div>`;
      if (meta.total_contas_analisadas) html += `<div><span class="num">${{meta.total_contas_analisadas}}</span><span class="lbl">Contas</span></div>`;
      html += `</div></div>`;

      /* Classification */
      html += `<div class="db-section"><div class="db-section-title">Classificação</div><div style="display:flex;gap:6px;flex-wrap:wrap">`;
      const pairs = [["alto", "alto", cls.achados_alto ?? 0], ["medio", "medio", cls.achados_medio ?? 0], ["baixo", "baixo", cls.achados_baixo ?? 0]];
      for (const [k, cl, n] of pairs) {{
        html += `<span class="pill ${{cl}}">${{k.charAt(0).toUpperCase()+k.slice(1)}}: ${{n}}</span>`;
      }}
      if ((cls.achados_compostos ?? 0) > 0) html += `<span class="pill alto" style="background:#7c1d1d;color:#fff">Compostos: ${{cls.achados_compostos}}</span>`;
      html += `</div></div>`;

      /* Metrics */
      const metricKeys = [
        ["receita_servicos", "Receita de Serviços"],
        ["deducoes_receita", "Deduções da Receita"],
        ["tributos_registrados", "Tributos Registrados"],
        ["tributos_a_recolher", "Tributos a Recolher"],
        ["folha_pro_labore", "Folha / Pro-Labore"],
        ["despesas_operacionais", "Despesas Operacionais"],
        ["lucros_distribuidos", "Lucros Distribuídos"],
        ["lucro_apurado_base", "Lucro Apurado"],
        ["caixa_e_bancos", "Caixa e Bancos"],
        ["clientes_recebiveis", "Clientes / Recebíveis"],
        ["adiantamentos", "Adiantamentos"],
        ["fornecedores", "Fornecedores"],
        ["estoques", "Estoques"],
        ["creditos_fiscais", "Créditos Fiscais"],
        ["emprestimos", "Empréstimos"],
      ];
      html += `<div class="db-section"><div class="db-section-title">Métricas</div><div class="metric-grid">`;
      for (const [key, label] of metricKeys) {{
        const v = m[key];
        if (!v) continue;
        html += `<div class="metric-card"><div class="label">${{esc(label)}}</div><div class="value">${{fmt(v)}}</div>`;
        if (key === "lucro_apurado_base" && m.origem_lucro_apurado) {{
          html += `<div class="detail">${{esc(m.origem_lucro_apurado)}}</div>`;
        }}
        html += `</div>`;
      }}
      html += `</div></div>`;

      /* Derived indicators */
      const ind = m.indicadores_derivados;
      if (ind) {{
        html += `<div class="db-section"><div class="db-section-title">Indicadores Derivados</div><div class="indicators">`;
        const indLabels = [
          ["carga_tributaria_efetiva_percentual", "Carga Tributária"],
          ["percentual_deducoes_sobre_receita", "Deduções / Receita"],
          ["percentual_folha_sobre_receita", "Folha / Receita"],
          ["percentual_despesas_sobre_receita", "Despesas / Receita"],
          ["endividamento_bancario_sobre_receita", "Empréstimos / Receita"],
        ];
        for (const [key, label] of indLabels) {{
          const v = ind[key];
          if (!v) continue;
          html += `<span class="indicator-badge"><strong>${{esc(label)}}:</strong> ${{esc(v)}}</span>`;
        }}
        if (ind.resultado_positivo !== undefined) {{
          const ok = ind.resultado_positivo;
          html += `<span class="indicator-badge ${{ok ? "ok" : "bad"}}"><strong>Resultado:</strong> ${{ok ? "Positivo" : "Negativo"}}</span>`;
        }}
        html += `</div></div>`;
      }}

      /* Contexto Regime */
      if (ctx.regime) {{
        html += `<div class="db-section"><div class="db-section-title">Contexto do Regime</div><div class="ctx-grid">`;
        const ctxItems = [
          ["regime", "Regime"],
          ["faixa_receita_estimada", "Faixa Receita"],
          ["aliquota_efetiva_esperada", "Alíquota Esperada"],
        ];
        for (const [key, label] of ctxItems) {{
          const v = ctx[key];
          if (!v) continue;
          html += `<div class="ctx-item"><div class="lbl">${{esc(label)}}</div><div class="val">${{esc(v)}}</div></div>`;
        }}
        if (ctx.fator_r_calculado) {{
          html += `<div class="ctx-item"><div class="lbl">Fator R</div><div class="val">${{esc(ctx.fator_r_calculado)}} <span style="font-size:11px;color:var(--muted)">(threshold ${{esc(ctx.fator_r_threshold || "28%")}})</span></div></div>`;
        }}
        if (ctx.sublimite_risco) {{
          html += `<div class="ctx-item" style="background:var(--warn-bg);border-color:#fde68a"><div class="lbl">Sublimite</div><div class="val" style="color:var(--warn)">Acima do limite</div></div>`;
        }}
        html += `</div>`;
        if (ctx.observacoes && ctx.observacoes.length) {{
          for (const obs of ctx.observacoes) {{
            html += `<div class="ctx-obs">${{esc(obs)}}</div>`;
          }}
        }}
        html += `</div>`;
      }}

      /* Findings table */
      if (achados.length > 0) {{
        html += `<div class="db-section"><div class="db-section-title">Achados (${{achados.length}})</div>`;
        html += `<p style="font-size:11px;color:var(--muted);margin-bottom:8px">${{meta.total_regras_acionadas ?? achados.length}} achados de ${{meta.total_regras_verificadas ?? "?"}} regras verificadas (conjunto: ${{esc(meta.conjunto_regras || "")}} v${{meta.versao_regras || ""}})</p>`;
        html += `<div style="overflow-x:auto"><table class="findings-table">`;
        html += `<thead><tr><th>Código</th><th>Achado</th><th>Nível</th><th>Descrição</th><th>Recomendação</th></tr></thead><tbody>`;

        const order = {{ "alto": 0, "medio": 1, "baixo": 2 }};
        const sorted = [...achados].sort((a, b) => (order[a.nivel] ?? 9) - (order[b.nivel] ?? 9));

        for (const f of sorted) {{
          const isPeer = f.codigo.startsWith("SN-COMP");
          html += `<tr class="${{isPeer ? "finding-peer" : ""}}">`;
          html += `<td class="finding-code">${{esc(f.codigo)}}</td>`;
          html += `<td><strong>${{esc(f.titulo)}}</strong>${{f.normas_aplicaveis?.length ? '<br><span style="font-size:10px;color:var(--muted)">'+f.normas_aplicaveis.map(x=>esc(x)).join("; ")+'</span>' : ""}}</td>`;
          html += `<td>${{pillHtml(f.nivel)}}</td>`;
          html += `<td style="font-size:11px">${{esc(f.descricao)}}`;
          const ev = f.evidencia;
          if (ev && Object.keys(ev).length) {{
            html += `<br><span style="font-size:10px;color:var(--muted)">${{Object.entries(ev).map(([k,v]) => esc(k)+": "+esc(v)).join(" | ")}}</span>`;
          }}
          html += `</td>`;
          html += `<td style="font-size:11px">${{esc(f.recomendacao)}}</td>`;
          html += `</tr>`;
        }}

        html += `</tbody></table></div></div>`;
      }}

      /* Score explanation */
      if (r.explicacao_pontuacao && r.explicacao_pontuacao.length) {{
        html += `<div class="db-section">`;
        html += `<span class="db-section-title">Explicação da Pontuação</span> `;
        html += `<span id="expl-toggle" class="toggle-link" onclick="document.getElementById('expl-body').style.display=document.getElementById('expl-body').style.display==='none'?'block':'none'">mostrar / ocultar</span>`;
        html += `<div id="expl-body" class="explain-box" style="margin-top:8px;display:none">`;
        for (const line of r.explicacao_pontuacao) {{
          html += `<p>${{esc(line)}}</p>`;
        }}
        html += `</div></div>`;
      }}

      /* Raw JSON toggle */
      html += `<div class="db-section">`;
      html += `<span class="db-section-title">JSON Bruto</span> `;
      html += `<span class="toggle-link" onclick="var e=document.getElementById('raw-json');e.style.display=e.style.display==='none'?'block':'none'">mostrar / ocultar</span>`;
      html += `<div id="raw-json" class="raw-json" style="display:none">${{esc(JSON.stringify(data, null, 2))}}</div>`;
      html += `</div>`;

      output.innerHTML = html;
    }}

    function dashboardFilename(ext) {{
      const ident = lastData?.identificacao || {{}};
      const clean = (value, fallback) => String(value || fallback)
        .replace(/\\s+/g, "_")
        .replace(/[^\\w.-]/g, "_");
      return `auditoria_${{clean(ident.cliente, "cliente")}}_${{clean(ident.periodo, "periodo")}}.${{ext}}`;
    }}

    function printDashboardPdf() {{
      if (!lastData) return;
      const printWindow = window.open("", "_blank");
      if (!printWindow) {{
        window.print();
        return;
      }}

      const ident = lastData.identificacao || {{}};
      const style = document.querySelector("style")?.innerHTML || "";
      const title = `Dashboard de Auditoria - ${{ident.cliente || "cliente"}} - ${{ident.periodo || "periodo"}}`;
      const printCss = `
        @page {{ size: A4; margin: 12mm; }}
        body {{ background: #fff; color: #111827; padding: 0; }}
        .print-page {{ max-width: 100%; margin: 0; }}
        .print-header {{ margin-bottom: 18px; border-bottom: 1px solid #d1d5db; padding-bottom: 10px; }}
        .print-header h1 {{ font-size: 20px; margin: 0 0 4px; }}
        .print-header p {{ margin: 0; color: #4b5563; font-size: 12px; }}
        .report {{ padding: 0; overflow: visible; }}
        .toggle-link, #raw-json, .raw-json {{ display: none !important; }}
        .risk-hero, .metric-card, .ctx-item, .explain-box {{ break-inside: avoid; }}
        .findings-table tr {{ break-inside: avoid; }}
      `;
      const content = output.innerHTML;
      printWindow.document.open();
      printWindow.document.write(`<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <title>${{esc(title)}}</title>
  <style>${{style}}${{printCss}}</style>
</head>
<body>
  <div class="print-page">
    <div class="print-header">
      <h1>${{esc(title)}}</h1>
      <p>Gerado a partir do dashboard de auditoria. Use a opção "Salvar como PDF" do navegador.</p>
    </div>
    <div class="report">${{content}}</div>
  </div>
  <script>
    window.addEventListener("load", function() {{
      setTimeout(function() {{
        window.focus();
        window.print();
      }}, 250);
    }});
  <\\/script>
</body>
</html>`);
      printWindow.document.close();
    }}

    let lastData = null;

    form.addEventListener("submit", async (event) => {{
      event.preventDefault();
      button.disabled = true;
      output.innerHTML = "<div class='report-empty'>Processando...</div>";
      score.innerHTML = "";
      lastData = null;
      try {{
        const response = await fetch("/api/auditorias", {{ method: "POST", body: new FormData(form) }});
        const data = await response.json();
        if (!response.ok) throw new Error(data.erro || "Falha ao gerar auditoria.");
        lastData = data;
        const risco = data.risco || {{}};
        const nivel = risco.nivel_geral || "desconhecido";
        score.innerHTML =
          `<span class="pill ${{nivel}}">Risco: ${{nivel.toUpperCase()}}</span>` +
          `<span class="pill info">Score: ${{risco.pontuacao_total ?? 0}}</span>` +
          `<span class="pill info">Achados: ${{(data.achados || []).length}}</span>` +
          `<button id="download-btn" class="pill outline" style="margin-left:4px">&#11015; JSON</button>` +
          `<button id="pdf-btn" class="pill outline" style="margin-left:4px">&#128462; PDF</button>`;
        document.getElementById("download-btn").addEventListener("click", () => {{
          const blob = new Blob([JSON.stringify(lastData, null, 2)], {{ type: "application/json" }});
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = dashboardFilename("json");
          a.click();
          URL.revokeObjectURL(url);
        }});
        document.getElementById("pdf-btn").addEventListener("click", printDashboardPdf);
        renderDashboard(data);
      }} catch (error) {{
        output.innerHTML = `<div class='report'><p style="color:var(--danger)">${{esc(error.message)}}</p></div>`;
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
