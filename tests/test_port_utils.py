from __future__ import annotations

import re
from pathlib import Path

from pdftablesearch import port_utils, qa


class _FakeProcess:
    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs
        self.pid = 12345

    def poll(self) -> None:
        return None


def test_run_service_writes_to_daily_app_log(monkeypatch, tmp_path) -> None:
    popen_calls: list[_FakeProcess] = []

    def fake_popen(*args, **kwargs) -> _FakeProcess:
        process = _FakeProcess(*args, **kwargs)
        popen_calls.append(process)
        return process

    spec = port_utils.ServiceSpec(name="api", ports=(8111,), command=["echo", "api"])
    monkeypatch.setattr(port_utils, "LOG_ROOT", tmp_path)
    monkeypatch.setattr(port_utils, "service_specs", lambda: [spec])
    monkeypatch.setattr(port_utils.subprocess, "Popen", fake_popen)

    port_utils.run_service("api")

    assert len(popen_calls) == 1
    stdout = popen_calls[0].kwargs["stdout"]
    try:
        log_path = Path(stdout.name)
    finally:
        stdout.close()

    assert log_path.parent == tmp_path
    assert re.fullmatch(r"app_\d{8}\.log", log_path.name)
    assert log_path.exists()


def test_qa_logs_prints_latest_daily_app_log(monkeypatch, tmp_path, capsys) -> None:
    older_log = tmp_path / "app_20260603.log"
    latest_log = tmp_path / "app_20260604.log"
    older_log.write_text("old\n", encoding="utf-8")
    latest_log.write_text("line 1\nline 2\nline 3\n", encoding="utf-8")

    monkeypatch.setattr(port_utils, "LOG_ROOT", tmp_path)

    qa._print_latest_logs(lines=2)

    output = capsys.readouterr().out
    assert f"logs: {latest_log}" in output
    assert "line 1" not in output
    assert "line 2" in output
    assert "line 3" in output
