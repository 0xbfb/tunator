#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"

cd "$BACKEND_DIR"

echo "[Tunator] Bootstrap: criando venv"
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
echo "[Tunator] Bootstrap: instalando dependências"
python -m pip install -e .[dev]
echo "[Tunator] Bootstrap: preparando runtime Tor local"
python -m app.cli bootstrap-local-tor --download-if-missing

echo "Tunator backend bootstrap concluído."
