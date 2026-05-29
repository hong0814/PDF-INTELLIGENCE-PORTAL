"""Local development runner for PDF Intelligence Portal."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"
WEB_DIST = WEB_DIR / "dist"


def _run(command: list[str], cwd: Path = ROOT) -> None:
    print("$ " + " ".join(command), flush=True)
    subprocess.run(command, cwd=str(cwd), check=True)


def _pids_on_port(port: int) -> list[int]:
    result = subprocess.run(
        ["lsof", "-ti", f":{port}"],
        capture_output=True,
        text=True,
        check=False,
    )
    return [int(pid) for pid in result.stdout.splitlines() if pid.strip().isdigit()]


def _port_is_open(port: int) -> bool:
    return bool(_pids_on_port(port))


def _wait_for_port(port: int, timeout: float = 20.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _port_is_open(port):
            return True
        time.sleep(0.5)
    return False


def _kill_port(port: int) -> None:
    pids = _pids_on_port(port)
    if not pids:
        print(f"No process is listening on port {port}.")
        return

    for pid in pids:
        print(f"Stopping pid {pid} on port {port}.")
        os.kill(pid, signal.SIGTERM)


def _build_web() -> None:
    if not (WEB_DIR / "node_modules").is_dir():
        _run(["npm", "install"], cwd=WEB_DIR)
    _run(["npm", "run", "build"], cwd=WEB_DIR)


def _start_hybrid(port: int) -> None:
    if _port_is_open(port):
        print(f"Hybrid PDF server is already listening on http://localhost:{port}.")
        return

    log_dir = ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / "hybrid.log"
    with log_path.open("ab") as log_file:
        subprocess.Popen(
            ["opendataloader-pdf-hybrid", "--port", str(port)],
            cwd=str(ROOT),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    if _wait_for_port(port):
        print(f"Hybrid PDF server started on http://localhost:{port}.")
    else:
        print(f"Hybrid PDF server did not bind port {port}; check {log_path}.")


def _start_api(host: str, port: int, reload: bool) -> None:
    import uvicorn

    print(f"Starting PDF Intelligence Portal on http://localhost:{port}")
    uvicorn.run(
        "pdftablesearch.web_server:app",
        host=host,
        port=port,
        reload=reload,
        reload_dirs=[str(ROOT / "pdftablesearch")] if reload else None,
    )


def start(args: argparse.Namespace) -> None:
    if args.build_web or not WEB_DIST.is_dir():
        _build_web()

    if args.with_hybrid:
        _start_hybrid(args.hybrid_port)

    if _port_is_open(args.port):
        print(f"Port {args.port} is already in use. Choose another port with --port.")
        sys.exit(1)

    _start_api(args.host, args.port, args.reload)


def status(args: argparse.Namespace) -> None:
    checks = {
        "api": args.port,
        "hybrid": args.hybrid_port,
    }
    for name, port in checks.items():
        pids = _pids_on_port(port)
        status_text = f"active pid(s): {', '.join(map(str, pids))}" if pids else "inactive"
        print(f"{name:<8} :{port:<5} {status_text}")


def stop(args: argparse.Namespace) -> None:
    _kill_port(args.port)
    if args.with_hybrid:
        _kill_port(args.hybrid_port)


def build_web(_: argparse.Namespace) -> None:
    _build_web()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run PDF Intelligence Portal locally.")
    subparsers = parser.add_subparsers(dest="command")

    start_parser = subparsers.add_parser("start", help="Build the web UI and start FastAPI.")
    start_parser.add_argument("--host", default="127.0.0.1")
    start_parser.add_argument("--port", type=int, default=int(os.getenv("PDF_PORTAL_PORT", "8111")))
    start_parser.add_argument("--hybrid-port", type=int, default=int(os.getenv("PDF_PORTAL_HYBRID_PORT", "8112")))
    start_parser.add_argument("--reload", action="store_true")
    start_parser.add_argument("--build-web", action="store_true")
    start_parser.add_argument("--with-hybrid", action="store_true")
    start_parser.set_defaults(func=start)

    status_parser = subparsers.add_parser("status", help="Show local service status.")
    status_parser.add_argument("--port", type=int, default=int(os.getenv("PDF_PORTAL_PORT", "8111")))
    status_parser.add_argument("--hybrid-port", type=int, default=int(os.getenv("PDF_PORTAL_HYBRID_PORT", "8112")))
    status_parser.set_defaults(func=status)

    stop_parser = subparsers.add_parser("stop", help="Stop local services on the configured ports.")
    stop_parser.add_argument("--port", type=int, default=int(os.getenv("PDF_PORTAL_PORT", "8111")))
    stop_parser.add_argument("--hybrid-port", type=int, default=int(os.getenv("PDF_PORTAL_HYBRID_PORT", "8112")))
    stop_parser.add_argument("--with-hybrid", action="store_true")
    stop_parser.set_defaults(func=stop)

    build_parser = subparsers.add_parser("build-web", help="Install and build the React web UI.")
    build_parser.set_defaults(func=build_web)

    args = parser.parse_args(argv)
    if args.command is None:
        args = parser.parse_args(["start"])

    args.func(args)


if __name__ == "__main__":
    main()
