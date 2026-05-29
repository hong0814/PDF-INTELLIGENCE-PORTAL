"""Local service process management for PDF Intelligence Portal."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable
from urllib.error import URLError
from urllib.request import urlopen

from pdftablesearch.config import get_settings

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"
LOG_ROOT = ROOT / "logs"
DEFAULT_READY_TIMEOUT_SECONDS = 45.0


@dataclass(frozen=True)
class ServiceSpec:
    """Local service metadata used by the QA launcher."""

    name: str
    ports: tuple[int, ...]
    command: list[str]
    ready_url: str | None = None
    cwd: Path = ROOT
    description: str = ""


def _settings_ports() -> dict[str, int]:
    settings = get_settings()
    return {
        "api": int(os.getenv("PDF_PORTAL_PORT", str(settings.pdf_portal_port))),
        "ui": int(os.getenv("PDF_PORTAL_UI_PORT", str(settings.pdf_portal_ui_port))),
        "hybrid": int(
            os.getenv("PDF_PORTAL_HYBRID_PORT", str(settings.pdf_portal_hybrid_port))
        ),
        "weaviate": int(os.getenv("WEAVIATE_PORT", str(settings.weaviate_port))),
        "weaviate_grpc": int(
            os.getenv("WEAVIATE_GRPC_PORT", str(settings.weaviate_grpc_port))
        ),
    }


def service_specs() -> list[ServiceSpec]:
    """Return the ordered local service registry."""
    ports = _settings_ports()
    settings = get_settings()
    api_host = os.getenv("PDF_PORTAL_HOST", settings.pdf_portal_host)
    return [
        ServiceSpec(
            name="weaviate",
            ports=(ports["weaviate"], ports["weaviate_grpc"]),
            command=["uv", "run", "--package", "pdftablesearch", "weaviate"],
            ready_url=f"http://127.0.0.1:{ports['weaviate']}/v1/.well-known/ready",
            description="embedded Weaviate vector database",
        ),
        ServiceSpec(
            name="hybrid",
            ports=(ports["hybrid"],),
            command=[
                "uv",
                "run",
                "--package",
                "pdftablesearch",
                "opendataloader-pdf-hybrid",
                "--port",
                str(ports["hybrid"]),
            ],
            ready_url=f"http://127.0.0.1:{ports['hybrid']}/health",
            description="opendataloader-pdf hybrid conversion server",
        ),
        ServiceSpec(
            name="api",
            ports=(ports["api"],),
            command=[
                "uv",
                "run",
                "--package",
                "pdftablesearch",
                "api",
                "start",
                "--host",
                api_host,
                "--port",
                str(ports["api"]),
            ],
            ready_url=f"http://127.0.0.1:{ports['api']}/api/health",
            description="FastAPI PDF Intelligence API",
        ),
        ServiceSpec(
            name="ui",
            ports=(ports["ui"],),
            command=[
                "uv",
                "run",
                "--package",
                "pdf-intelligence-web",
                "ui",
                "--host",
                "127.0.0.1",
                "--port",
                str(ports["ui"]),
            ],
            ready_url=f"http://127.0.0.1:{ports['ui']}",
            description="React/Vite web UI",
        ),
    ]


def _service_by_name(name: str) -> ServiceSpec:
    for spec in service_specs():
        if spec.name == name:
            return spec
    known = ", ".join(spec.name for spec in service_specs())
    raise ValueError(f"Unknown service '{name}'. Known services: {known}")


def _pids_on_port(port: int) -> list[int]:
    result = subprocess.run(
        ["lsof", "-ti", f":{port}"],
        capture_output=True,
        text=True,
        check=False,
    )
    return [int(pid) for pid in result.stdout.splitlines() if pid.strip().isdigit()]


def _is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def kill_port(port: int, timeout: float = 1.5) -> list[int]:
    """Terminate all processes listening on a port and return affected PIDs."""
    pids = _pids_on_port(port)
    if not pids:
        return []

    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not any(_is_alive(pid) for pid in pids):
            return pids
        time.sleep(0.1)

    for pid in pids:
        if _is_alive(pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    return pids


def _pids_matching(pattern: str) -> list[int]:
    result = subprocess.run(
        ["pgrep", "-f", pattern],
        capture_output=True,
        text=True,
        check=False,
    )
    current = os.getpid()
    return [
        int(pid)
        for pid in result.stdout.splitlines()
        if pid.strip().isdigit() and int(pid) != current
    ]


def _kill_pids(pids: list[int], timeout: float = 1.5) -> list[int]:
    if not pids:
        return []
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not any(_is_alive(pid) for pid in pids):
            return pids
        time.sleep(0.1)

    for pid in pids:
        if _is_alive(pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    return pids


def killports() -> None:
    """Stop API, UI, hybrid PDF, and Weaviate local service ports."""
    seen_pids: set[int] = set()
    for spec in service_specs():
        for port in spec.ports:
            pids = [pid for pid in _pids_on_port(port) if pid not in seen_pids]
            if not pids:
                print(f"{spec.name:<14} :{port:<5} no process")
                continue
            for pid in pids:
                seen_pids.add(pid)
            killed = kill_port(port)
            print(f"{spec.name:<14} :{port:<5} stopped {', '.join(map(str, killed))}")

    wrapper_pids = _pids_matching("pdftablesearch.vectorstores.weaviate_server")
    if wrapper_pids:
        killed = _kill_pids(wrapper_pids)
        print(f"{'weaviate_py':<14} wrapper stopped {', '.join(map(str, killed))}")


def stop_service(name: str) -> None:
    """Stop one configured local service by name."""
    spec = _service_by_name(name)
    for port in spec.ports:
        killed = kill_port(port)
        status = f"stopped {', '.join(map(str, killed))}" if killed else "no process"
        print(f"{spec.name:<14} :{port:<5} {status}")
    if spec.name == "weaviate":
        wrapper_pids = _pids_matching("pdftablesearch.vectorstores.weaviate_server")
        if wrapper_pids:
            killed = _kill_pids(wrapper_pids)
            print(f"{'weaviate_py':<14} wrapper stopped {', '.join(map(str, killed))}")


def _timestamped_log_dir() -> Path:
    log_dir = LOG_ROOT / f"qa_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def _spawn(name: str, command: list[str], log_dir: Path, cwd: Path = ROOT) -> subprocess.Popen:
    log_path = log_dir / f"{name}.log"
    log_file = log_path.open("ab")
    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    print(f"{name:<14} pid={process.pid:<7} log={log_path}")
    return process


def _spawn_service(spec: ServiceSpec, log_dir: Path) -> subprocess.Popen:
    print(f"{spec.name:<14} command={' '.join(spec.command)}")
    return _spawn(spec.name, spec.command, log_dir, cwd=spec.cwd)


def run_service(name: str, log_dir: Path | None = None) -> subprocess.Popen:
    """Start one configured local service in the background."""
    spec = _service_by_name(name)
    return _spawn_service(spec, log_dir or _timestamped_log_dir())


def run_weaviate(log_dir: Path | None = None) -> subprocess.Popen:
    """Start embedded Weaviate in the background."""
    return run_service("weaviate", log_dir)


def run_hybrid(log_dir: Path | None = None) -> subprocess.Popen:
    """Start opendataloader-pdf hybrid server in the background."""
    return run_service("hybrid", log_dir)


def run_api(log_dir: Path | None = None) -> subprocess.Popen:
    """Start the FastAPI app in the background."""
    return run_service("api", log_dir)


def run_ui(log_dir: Path | None = None) -> subprocess.Popen:
    """Start the Vite dev server in the background."""
    return run_service("ui", log_dir)


def run_all() -> None:
    """Stop existing local services, then start all development services."""
    killports()
    log_dir = _timestamped_log_dir()
    print(f"logs: {log_dir}")
    processes: list[tuple[ServiceSpec, subprocess.Popen]] = []
    for spec in service_specs():
        processes.append((spec, _spawn_service(spec, log_dir)))

    failures = [spec.name for spec, process in processes if not _wait_for_service(spec, process)]
    if failures:
        raise RuntimeError(f"Services failed readiness checks: {', '.join(failures)}")


def _http_ready(url: str, timeout: float = 0.5) -> bool:
    try:
        with urlopen(url, timeout=timeout) as response:
            return 200 <= response.status < 500
    except (OSError, URLError):
        return False


def _ready_timeout() -> float:
    return float(os.getenv("PDF_PORTAL_QA_READY_TIMEOUT", str(DEFAULT_READY_TIMEOUT_SECONDS)))


def _wait_for_service(spec: ServiceSpec, process: subprocess.Popen) -> bool:
    deadline = time.monotonic() + _ready_timeout()
    while time.monotonic() < deadline:
        exit_code = process.poll()
        if exit_code is not None:
            print(f"{spec.name:<14} exited early with code {exit_code}")
            return False
        if spec.ready_url is None:
            return True
        if _http_ready(spec.ready_url):
            print(f"{spec.name:<14} ready")
            return True
        time.sleep(0.5)
    print(f"{spec.name:<14} not ready after {_ready_timeout():.0f}s")
    return False


def service_statuses() -> list[dict[str, object]]:
    """Return local service status rows."""
    rows = []
    for spec in service_specs():
        pids: list[int] = []
        for port in spec.ports:
            pids.extend(_pids_on_port(port))
        ready = _http_ready(spec.ready_url) if spec.ready_url else bool(pids)
        rows.append(
            {
                "name": spec.name,
                "ports": spec.ports,
                "pids": sorted(set(pids)),
                "ready": ready,
                "command": " ".join(spec.command),
                "description": spec.description,
            }
        )
    return rows


def print_status(rows: Iterable[dict[str, object]] | None = None) -> None:
    """Print service status rows."""
    for row in rows or service_statuses():
        pids = row["pids"]
        pid_text = ", ".join(map(str, pids)) if pids else "-"
        ready_text = "ready" if row["ready"] else "not-ready"
        ports = "/".join(str(port) for port in row["ports"])
        print(f"{row['name']:<14} :{ports:<11} pid={pid_text:<12} {ready_text}")


def print_service_commands() -> None:
    """Print the ordered service commands used by the QA launcher."""
    for spec in service_specs():
        ports = "/".join(str(port) for port in spec.ports)
        print(f"{spec.name:<14} :{ports:<11} {' '.join(spec.command)}")
