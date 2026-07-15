from __future__ import annotations

import argparse
import logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="API local para pre-auditoria fiscal.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--api-key", help="Chave da API para autenticacao (ou use AUDIT_API_KEY).")
    parser.add_argument("--cors-origin", help="Origem permitida para CORS (ou use AUDIT_CORS_ORIGIN). Padrao: *.")
    parser.add_argument("--regime-tributario", default=None, help="Regime tributario (padrao: Simples Nacional).")
    parser.add_argument(
        "--atividade",
        default="servicos",
        choices=["servicos", "comercio", "comercio_servicos"],
        help="Conjunto de regras do Simples Nacional.",
    )
    parser.add_argument("--db-path", help="Caminho do SQLite local (ou use AUDIT_DB_PATH).")
    parser.add_argument(
        "--allow-unsafe-network",
        action="store_true",
        help="Permite host nao local sem API key ou CORS restrito. Use apenas em ambiente isolado.",
    )
    parser.add_argument("--verbose", action="store_true", help="Ativar logging detalhado.")
    return parser.parse_args()


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def validate_runtime_security(
    host: str,
    api_key: str | None,
    cors_origin: str,
    allow_unsafe_network: bool,
) -> None:
    if is_loopback_host(host) or allow_unsafe_network:
        return

    if not (api_key or "").strip():
        raise ValueError(
            "API exposta em host nao local exige API key. Use --api-key/AUDIT_API_KEY "
            "ou --allow-unsafe-network apenas em ambiente isolado."
        )

    if (cors_origin or "*").strip() == "*":
        raise ValueError(
            "API exposta em host nao local exige CORS restrito. Informe --cors-origin/AUDIT_CORS_ORIGIN "
            "ou --allow-unsafe-network apenas em ambiente isolado."
        )


def is_loopback_host(host: str) -> bool:
    normalized = (host or "").strip().lower()
    return normalized in {"127.0.0.1", "localhost", "::1"}
