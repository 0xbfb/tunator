$ErrorActionPreference = 'Stop'

$RootDir = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $RootDir 'backend'

Set-Location $BackendDir

python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -e .[dev]
& .\.venv\Scripts\python.exe -m app.cli bootstrap-local-tor --download-if-missing

Write-Host 'Tunator backend bootstrap concluído.'
