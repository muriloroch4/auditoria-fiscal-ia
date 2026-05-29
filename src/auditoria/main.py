from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .audit import run_quarterly_audit
from .parser import read_trial_balance
from .serializers import audit_result_to_dict


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = _parse_args()
    balance = read_trial_balance(args.balancete, cliente=args.cliente, periodo=args.periodo, cnpj=args.cnpj)
    result = run_quarterly_audit(balance)
    payload = audit_result_to_dict(result)

    if args.markdown:
        from .report_ai import generate_markdown_report

        output = generate_markdown_report(result, use_ai=not args.no_ai, api_key=args.openrouter_key, cnpj=args.cnpj)
    else:
        output = json.dumps(payload, ensure_ascii=False, indent=2)

    if args.saida:
        output_path = Path(args.saida)
        output_path.write_text(output, encoding="utf-8")
        print(f"Resultado salvo em: {output_path}")
        return

    print(output)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pre-auditoria fiscal trimestral para Simples Nacional servicos.")
    parser.add_argument("balancete", help="Caminho do CSV ou XLSX do balancete.")
    parser.add_argument("--cliente", required=True, help="Nome do cliente analisado.")
    parser.add_argument("--periodo", required=True, help='Periodo analisado. Exemplo: "2026-T1".')
    parser.add_argument("--cnpj", default="", help="CNPJ da empresa. Exemplo: 00.000.000/0001-00.")
    parser.add_argument("--saida", help="Arquivo de saida (JSON por padrao, Markdown com --markdown).")
    parser.add_argument("--markdown", action="store_true", help="Gerar relatorio Markdown em vez de JSON.")
    parser.add_argument("--no-ai", action="store_true", help="Desabilitar IA no relatorio Markdown.")
    parser.add_argument("--openrouter-key", help="Chave da API OpenRouter (ou use OPENROUTER_API_KEY).")
    return parser.parse_args()


if __name__ == "__main__":
    main()
