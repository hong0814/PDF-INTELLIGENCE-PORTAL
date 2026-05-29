"""Command-line wrappers around the existing Vite npm scripts."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


WEB_DIR = Path(__file__).resolve().parents[1]


def _ensure_node_modules() -> None:
    if not (WEB_DIR / "node_modules").exists():
        subprocess.run(["npm", "install"], cwd=WEB_DIR, check=True)


def _run_npm_script(script: str) -> None:
    _ensure_node_modules()
    subprocess.run(["npm", "run", script, "--", *sys.argv[1:]], cwd=WEB_DIR, check=True)


def dev() -> None:
    _run_npm_script("dev")


def build() -> None:
    _run_npm_script("build")


def preview() -> None:
    _run_npm_script("preview")


def lint() -> None:
    _run_npm_script("lint")


ui = dev
ui_build = build
ui_preview = preview
ui_lint = lint
