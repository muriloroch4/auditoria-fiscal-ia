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

    if args.anual:
        payloads = [json.loads(Path(path).read_text(encoding="utf-8")) for path in args.anual]
        from .annual import build_annual_comparison, generate_annual_markdown_report

        annual_payload = build_annual_comparison(payloads)
        if args.markdown:
            output = generate_annual_markdown_report(annual_payload)
        else:
            output = json.dumps(annual_payload, ensure_ascii=False, indent=2)
        _write_or_print(output, args.saida)
        return

    if not args.balancete:
        raise SystemExit("Informe o caminho do balancete ou use --anual com JSONs trimestrais.")
    if not args.cliente or not args.periodo:
        raise SystemExit("Para análise trimestral, informe --cliente e --periodo.")

    balance = read_trial_balance(args.balancete, cliente=args.cliente, periodo=args.periodo, cnpj=args.cnpj)
    result = run_quarterly_audit(balance, atividade=args.atividade)
    payload = audit_result_to_dict(result)

    if args.markdown:
        from .report_ai import generate_markdown_report

        output = generate_markdown_report(result, use_ai=not args.no_ai, api_key=args.openrouter_key, cnpj=args.cnpj)
    else:
        output = json.dumps(payload, ensure_ascii=False, indent=2)

    _write_or_print(output, args.saida)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pré-auditoria fiscal trimestral e parecer anual comparativo.")
    parser.add_argument("balancete", nargs="?", help="Caminho do CSV ou XLSX do balancete trimestral.")
    parser.add_argument("--anual", nargs="+", help="JSONs trimestrais para consolidar o parecer anual comparativo.")
    parser.add_argument("--cliente", help="Nome do cliente analisado.")
    parser.add_argument("--periodo", help='Período analisado. Exemplo: "2026-T1".')
    parser.add_argument("--cnpj", default="", help="CNPJ da empresa. Exemplo: 00.000.000/0001-00.")
    parser.add_argument(
        "--atividade",
        default="servicos",
        choices=["servicos", "comercio", "comercio_servicos"],
        help="Conjunto de regras: servicos, comercio ou comercio_servicos.",
    )
    parser.add_argument("--saida", help="Arquivo de saída (JSON por padrão, Markdown com --markdown).")
    parser.add_argument("--markdown", action="store_true", help="Gerar relatório Markdown em vez de JSON.")
    parser.add_argument("--no-ai", action="store_true", help="Desabilitar IA no relatório Markdown.")
    parser.add_argument("--openrouter-key", help="Chave da API OpenRouter (ou use OPENROUTER_API_KEY).")
    return parser.parse_args()


def _write_or_print(output: str, output_path: str | None) -> None:
    if output_path:
        path = Path(output_path)
        path.write_text(output, encoding="utf-8")
        print(f"Resultado salvo em: {path}")
        return

    print(output)


if __name__ == "__main__":
    main()
