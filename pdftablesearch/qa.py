"""Interactive QA/service launcher for local development."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from pdftablesearch import port_utils


def _latest_log_dir() -> Path | None:
    log_root = port_utils.LOG_ROOT
    if not log_root.exists():
        return None
    candidates = sorted(
        [path for path in log_root.iterdir() if path.is_dir() and path.name.startswith("qa_")]
    )
    return candidates[-1] if candidates else None


def _print_latest_logs(lines: int = 40) -> None:
    latest = _latest_log_dir()
    if latest is None:
        print("No QA log directory found.")
        return
    print(f"logs: {latest}")
    for path in sorted(latest.glob("*.log")):
        print(f"\n==> {path.name} <==")
        content = path.read_text(errors="replace").splitlines()
        for line in content[-lines:]:
            print(line)


def _run_tests(include_weaviate: bool = False) -> int:
    command = [
        "uv",
        "run",
        "--extra",
        "dev",
        "pytest",
        "tests/test_auth.py",
        "tests/test_vectorstore.py",
        "tests/test_core.py",
        "tests/test_models.py",
        "tests/test_vectorstore_contract.py",
        "tests/test_weaviate_store.py",
    ]
    if include_weaviate:
        command.extend(["tests/test_weaviate_integration.py"])
    print("$ " + " ".join(command), flush=True)
    return subprocess.run(command, check=False).returncode


def _run_weaviate_tests() -> int:
    command = [
        "uv",
        "run",
        "--extra",
        "dev",
        "pytest",
        "-m",
        "weaviate",
        "tests/test_weaviate_integration.py",
    ]
    print("$ " + " ".join(command), flush=True)
    return subprocess.run(command, check=False).returncode


def status(_: argparse.Namespace | None = None) -> None:
    port_utils.print_status()


def commands(_: argparse.Namespace | None = None) -> None:
    port_utils.print_service_commands()


def start(args: argparse.Namespace | None = None) -> None:
    service = getattr(args, "service", None) if args is not None else None
    if service:
        port_utils.run_service(service)
    else:
        port_utils.run_all()


def stop(args: argparse.Namespace | None = None) -> None:
    service = getattr(args, "service", None) if args is not None else None
    if service:
        port_utils.stop_service(service)
    else:
        port_utils.killports()


def restart(args: argparse.Namespace | None = None) -> None:
    stop(args)
    start(args)


def logs(args: argparse.Namespace | None = None) -> None:
    lines = getattr(args, "lines", 40) if args is not None else 40
    _print_latest_logs(lines=lines)


def test(args: argparse.Namespace | None = None) -> None:
    include_weaviate = bool(getattr(args, "weaviate", False)) if args is not None else False
    code = _run_weaviate_tests() if include_weaviate else _run_tests()
    if args is not None and code:
        raise SystemExit(code)


def _service_choice() -> str | None:
    specs = port_utils.service_specs()
    for index, spec in enumerate(specs, start=1):
        ports = "/".join(str(port) for port in spec.ports)
        print(f"{index}. {spec.name:<10} :{ports:<11} {spec.description}")
    print("a. all")
    choice = input("> ").strip().lower()
    if choice == "a":
        return None
    if choice.isdigit():
        index = int(choice)
        if 1 <= index <= len(specs):
            return specs[index - 1].name
    print("Unknown service.")
    return "__invalid__"


def _manual() -> None:
    while True:
        print("\nManual Services")
        print("1. start service")
        print("2. stop service")
        print("3. restart service")
        print("4. commands")
        print("b. back")
        choice = input("> ").strip().lower()
        if choice == "b":
            return
        if choice == "4":
            commands(None)
            continue
        if choice not in {"1", "2", "3"}:
            print("Unknown choice.")
            continue

        service = _service_choice()
        if service == "__invalid__":
            continue
        args = argparse.Namespace(service=service)
        if choice == "1":
            start(args)
        elif choice == "2":
            stop(args)
        else:
            restart(args)


def _tests_menu() -> None:
    while True:
        print("\nTests")
        print("1. regression")
        print("2. weaviate integration")
        print("b. back")
        choice = input("> ").strip().lower()
        if choice == "1":
            _run_tests()
        elif choice == "2":
            _run_weaviate_tests()
        elif choice == "b":
            return
        else:
            print("Unknown choice.")


def _interactive() -> None:
    while True:
        print("\nPDF Intelligence Portal QA")
        print("-" * 32)
        status(None)
        print("\n1. E2E QA")
        print("2. Manual")
        print("3. Tests")
        print("4. Logs")
        print("5. Kill Ports")
        print("e. Exit")
        choice = input("> ").strip().lower()
        if choice == "1":
            start(None)
        elif choice == "2":
            _manual()
        elif choice == "3":
            _tests_menu()
        elif choice == "4":
            logs(None)
        elif choice == "5":
            stop(None)
        elif choice == "e":
            stop(None)
            return
        else:
            print("Unknown choice.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Manage local QA services.")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("status").set_defaults(func=status)
    subparsers.add_parser("commands").set_defaults(func=commands)

    start_parser = subparsers.add_parser("start")
    start_parser.add_argument("service", nargs="?")
    start_parser.set_defaults(func=start)

    stop_parser = subparsers.add_parser("stop")
    stop_parser.add_argument("service", nargs="?")
    stop_parser.set_defaults(func=stop)

    restart_parser = subparsers.add_parser("restart")
    restart_parser.add_argument("service", nargs="?")
    restart_parser.set_defaults(func=restart)

    logs_parser = subparsers.add_parser("logs")
    logs_parser.add_argument("--lines", type=int, default=40)
    logs_parser.set_defaults(func=logs)

    test_parser = subparsers.add_parser("test")
    test_parser.add_argument(
        "--weaviate",
        action="store_true",
        help="Run the local Weaviate integration test; start Weaviate first.",
    )
    test_parser.set_defaults(func=test)

    args = parser.parse_args(argv)
    if args.command is None:
        if sys.stdin.isatty():
            _interactive()
        else:
            status()
        return
    args.func(args)


if __name__ == "__main__":
    main()
