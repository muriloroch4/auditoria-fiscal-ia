param(
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

function Find-Python {
    if (Test-Path $BundledPython) {
        return $BundledPython
    }

    $PyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($PyLauncher) {
        return "py"
    }

    $Python = Get-Command python -ErrorAction SilentlyContinue
    if ($Python) {
        return "python"
    }

    return $null
}

$PythonCommand = Find-Python

if (-not $PythonCommand) {
    Write-Host "Python nao encontrado."
    Write-Host "Instale o Python 3.11+ em https://www.python.org/downloads/ e marque a opcao Add python.exe to PATH."
    exit 1
}

Set-Location $ProjectRoot

# Carrega a chave do OpenRouter automaticamente se estiver presente no arquivo .env
$EnvFile = Join-Path $ProjectRoot ".env"
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match "^OPENROUTER_API_KEY=(.*)$") {
            $env:OPENROUTER_API_KEY = $matches[1].Trim('"').Trim("'")
        }
    }
}

Write-Host ""
Write-Host "Iniciando API de auditoria fiscal..."
Write-Host "URL: http://127.0.0.1:$Port"
if ($env:OPENROUTER_API_KEY) {
    Write-Host "IA OpenRouter: Habilitada."
} else {
    Write-Host "IA OpenRouter: Desabilitada (sem chave configurada)."
}
Write-Host "Deixe esta janela aberta enquanto estiver usando o sistema."
Write-Host "Para encerrar, pressione Ctrl+C."
Write-Host ""

if ($PythonCommand -eq "py") {
    & py -3 -m src.auditoria.api --port $Port
} else {
    & $PythonCommand -m src.auditoria.api --port $Port
}
