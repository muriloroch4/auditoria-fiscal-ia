from __future__ import annotations

import json
import logging
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from .api_helpers import json_default

logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).with_name("static")


def index_html() -> str:
    return read_static_text("index.html")


def read_static_text(filename: str) -> str:
    return (STATIC_DIR / filename).read_text(encoding="utf-8")


def send_json_response(
    handler: BaseHTTPRequestHandler,
    payload: Any,
    send_cors_headers: Callable[[], None],
    status: HTTPStatus = HTTPStatus.OK,
) -> None:
    content = json.dumps(payload, ensure_ascii=False, indent=2, default=json_default).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    send_cors_headers()
    handler.send_header("Content-Length", str(len(content)))
    handler.end_headers()
    handler.wfile.write(content)


def send_html_response(
    handler: BaseHTTPRequestHandler,
    content: str,
    send_cors_headers: Callable[[], None],
    status: HTTPStatus = HTTPStatus.OK,
) -> None:
    encoded = content.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    send_cors_headers()
    handler.send_header("Content-Length", str(len(encoded)))
    handler.end_headers()
    handler.wfile.write(encoded)


def send_static_response(
    handler: BaseHTTPRequestHandler,
    path: str,
    send_cors_headers: Callable[[], None],
    send_json: Callable[[Any, HTTPStatus], None],
) -> None:
    requested = unquote(path.removeprefix("/static/"))
    target = (STATIC_DIR / requested).resolve()
    static_root = STATIC_DIR.resolve()

    if not target.is_relative_to(static_root) or not target.is_file():
        logger.warning("Arquivo estatico nao encontrado: %s", path)
        send_json({"erro": "Arquivo nao encontrado."}, HTTPStatus.NOT_FOUND)
        return

    content = target.read_bytes()
    handler.send_response(HTTPStatus.OK)
    handler.send_header("Content-Type", static_content_type(target))
    send_cors_headers()
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("Content-Length", str(len(content)))
    handler.end_headers()
    handler.wfile.write(content)


def static_content_type(path: Path) -> str:
    if path.suffix == ".css":
        return "text/css; charset=utf-8"
    if path.suffix == ".js":
        return "text/javascript; charset=utf-8"
    if path.suffix == ".svg":
        return "image/svg+xml; charset=utf-8"
    if path.suffix == ".html":
        return "text/html; charset=utf-8"
    return "application/octet-stream"
