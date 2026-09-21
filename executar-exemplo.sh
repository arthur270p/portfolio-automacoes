#!/usr/bin/env bash
# Demonstracao em Linux e macOS. O equivalente para Windows e
# executar-exemplo.ps1. Nenhum dos dois exige instalar o pacote.
set -euo pipefail

raiz="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python="${PYTHON:-python3}"

PYTHONPATH="$raiz/src" "$python" -m automacao_planilhas processar \
  --entrada "$raiz/exemplos/entrada" \
  --config "$raiz/exemplos/config.json" \
  --saida "$raiz/exemplos/saida/relatorio.xlsx" \
  --sobrescrever
