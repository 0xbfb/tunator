$ErrorActionPreference = 'Stop'

$RootDir = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $RootDir 'backend'

Set-Location $BackendDir

Write-Host "[Tunator] Bootstrap: criando venv"
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
Write-Host "[Tunator] Bootstrap: instalando dependências"
& .\.venv\Scripts\python.exe -m pip install -e .[dev]
Write-Host "[Tunator] Bootstrap: preparando runtime Tor local"
& .\.venv\Scripts\python.exe -m app.cli bootstrap-local-tor --download-if-missing

Write-Host 'Tunator backend bootstrap concluído.'
