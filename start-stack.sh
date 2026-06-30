#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
VENV_DIR="$BACKEND_DIR/.venv"
HOST="127.0.0.1"
PORT="8000"
NO_RUN="false"

usage() {
  cat <<'EOF'
Usage: ./start-stack.sh [options]

Options:
  --host <host>      Host for uvicorn (default: 127.0.0.1)
  --port <port>      Port for uvicorn (default: 8000)
  --no-run           Prepare environment only, do not start server
  -h, --help         Show this help

Environment variables:
  MANGA_SOURCE_COOKIE Optional cookie used when source is behind Cloudflare
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      HOST="$2"
      shift 2
      ;;
    --port)
      PORT="$2"
      shift 2
      ;;
    --no-run)
      NO_RUN="true"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      usage
      exit 1
      ;;
  esac
done

if [[ ! -d "$BACKEND_DIR" ]]; then
  echo "Backend folder not found: $BACKEND_DIR"
  exit 1
fi

cd "$BACKEND_DIR"

if [[ ! -d "$VENV_DIR" ]]; then
  echo "Creating virtual environment in $VENV_DIR"
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

echo "Upgrading pip toolchain"
python -m pip install --upgrade pip setuptools wheel

echo "Installing project dependencies"
pip install -e .

if [[ "$NO_RUN" == "true" ]]; then
  echo "Environment is ready. Server not started (--no-run)."
  exit 0
fi

echo "Starting API on http://$HOST:$PORT"
exec uvicorn app.main:app --reload --host "$HOST" --port "$PORT"
