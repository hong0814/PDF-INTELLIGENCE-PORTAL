#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

uv run --package pdftablesearch api start --port "${PDF_PORTAL_PORT:-8111}" "$@"
