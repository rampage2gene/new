"""Desktop launcher: must start with no console streams (windowed Windows build)."""
from __future__ import annotations

import importlib.util
import json
import logging
import sys
import urllib.request
from pathlib import Path

import pytest

LAUNCHER = Path(__file__).resolve().parents[2] / "desktop" / "launcher.py"


@pytest.fixture(scope="module")
def launcher():
    spec = importlib.util.spec_from_file_location("mdi_launcher", LAUNCHER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_setup_logging_writes_file(launcher, tmp_path):
    log_file = launcher.setup_logging(tmp_path)
    logging.getLogger("desktop").info("hello from the test")
    for h in list(logging.getLogger().handlers):
        h.flush()
    assert log_file == tmp_path / "logs" / "app.log"
    assert "hello from the test" in log_file.read_text(encoding="utf-8")


def test_server_starts_without_console_streams(launcher, data_dir, monkeypatch, tmp_path):
    """Regression: a PyInstaller windowed build has sys.stdout/sys.stderr == None and
    uvicorn's logging setup used to crash on `sys.stdout.isatty()`."""
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    launcher.setup_logging(tmp_path)
    assert sys.stdout is not None and sys.stderr is not None  # redirected to the log file

    server = launcher.ApiServer(launcher.free_port(0))
    server.start()
    try:
        assert server.wait_ready(timeout=30), "server did not come up"
        with urllib.request.urlopen(server.url + "/api/status", timeout=5) as r:
            body = json.loads(r.read())
        assert body["version"] == launcher.APP_VERSION
    finally:
        server.stop()
