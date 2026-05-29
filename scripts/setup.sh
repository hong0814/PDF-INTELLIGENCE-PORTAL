#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    cp ".env.example" ".env"
    echo "Created .env from .env.example. Fill in API keys before using LLM features."
fi

export UV_HTTP_TIMEOUT="${UV_HTTP_TIMEOUT:-300}"
uv sync --all-packages --extra dev
uv run ui-build

echo ""
echo "Setup complete."
echo "Start with: uv run qa"
echo "Or run: ./scripts/start.sh"
