from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .audit import run_quarterly_audit
from .parser import read_trial_balance
from .report_ai import generate_markdown_report


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = _parse_args()
    balance = read_trial_balance(args.balancete, cliente=args.cliente, periodo=args.periodo)
    result = run_quarterly_audit(balance)
    report = generate_markdown_report(result, use_ai=args.use_ai, api_key=args.api_key)

    if args.saida:
        output_path = Path(args.saida)
        output_path.write_text(report, encoding="utf-8")
        print(f"Relatorio gerado em: {output_path}")
        return

    print(report)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pre-auditoria fiscal trimestral para Simples Nacional servicos.")
    parser.add_argument("balancete", help="Caminho do CSV ou XLSX do balancete.")
    parser.add_argument("--cliente", required=True, help="Nome do cliente analisado.")
    parser.add_argument("--periodo", required=True, help='Periodo analisado. Exemplo: "2026-T1".')
    parser.add_argument("--saida", help="Arquivo Markdown de saida.")
    parser.add_argument("--no-ai", action="store_false", dest="use_ai", default=True, help="Desabilitar IA e usar relatorio padrao.")
    parser.add_argument("--api-key", help="Chave da API OpenRouter (ou use OPENROUTER_API_KEY).")
    return parser.parse_args()


if __name__ == "__main__":
    main()
