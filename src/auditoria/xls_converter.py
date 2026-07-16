from __future__ import annotations

import subprocess
from pathlib import Path

from .parser_tables import ps_escape


def convert_xls_to_xlsx(source: Path, converted: Path) -> None:
    script = f"""
$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false
$excel.DisplayAlerts = $false
$excel.AutomationSecurity = 3
$workbook = $excel.Workbooks.Open('{ps_escape(source)}', 0, $true)
try {{
    $workbook.SaveAs('{ps_escape(converted)}', 51)
}} finally {{
    if ($workbook) {{ $workbook.Close($false) }}
    if ($excel) {{ $excel.Quit() }}
}}
"""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0 or not converted.exists():
        raise ValueError(
            "Nao foi possivel converter o .xls automaticamente. "
            "Salve o arquivo como .xlsx no Excel e tente novamente."
        )
