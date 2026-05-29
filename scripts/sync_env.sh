#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"
REQUIREMENTS_FILE="${ROOT_DIR}/requirements.txt"
MODE="${1:-recreate}"

if [[ ! -f "${REQUIREMENTS_FILE}" ]]; then
  echo "requirements.txt not found at ${REQUIREMENTS_FILE}" >&2
  exit 1
fi

case "${MODE}" in
  recreate)
    rm -rf "${VENV_DIR}"
    python3 -m venv "${VENV_DIR}"
    # shellcheck disable=SC1091
    source "${VENV_DIR}/bin/activate"
    python -m pip install --upgrade pip
    python -m pip install -r "${REQUIREMENTS_FILE}"
    ;;
  sync)
    if [[ ! -d "${VENV_DIR}" ]]; then
      echo ".venv does not exist. Run: scripts/sync_env.sh recreate" >&2
      exit 1
    fi
    # shellcheck disable=SC1091
    source "${VENV_DIR}/bin/activate"
    python -m pip install --upgrade pip pip-tools
    pip-sync "${REQUIREMENTS_FILE}"
    ;;
  *)
    echo "Usage: scripts/sync_env.sh [recreate|sync]" >&2
    echo "  recreate  Remove .venv, create a fresh venv, install requirements.txt" >&2
    echo "  sync      Keep .venv, use pip-sync so only requirements.txt packages remain" >&2
    exit 1
    ;;
esac

echo "[OK] Environment ${MODE} completed."
