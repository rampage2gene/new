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


def test_portable_data_dir_uses_folder_beside_the_exe(launcher, monkeypatch, tmp_path):
    """A portable copy keeps documents and its log next to the executable."""
    exe = tmp_path / "MarineDocIntelligence"
    exe.write_text("", encoding="utf-8")
    monkeypatch.setattr(launcher, "FROZEN", True)
    monkeypatch.setattr(sys, "executable", str(exe))

    assert launcher.portable_data_dir() is None, "no marker: an installed copy must be unaffected"

    (tmp_path / "portable.txt").write_text("portable", encoding="utf-8")
    assert launcher.portable_data_dir() == tmp_path / "data"
    assert (tmp_path / "data").is_dir()


def test_portable_data_dir_falls_back_when_not_writable(launcher, monkeypatch, tmp_path):
    """Unzipped somewhere read-only, the app uses the per-user folder rather than failing."""
    exe = tmp_path / "MarineDocIntelligence"
    exe.write_text("", encoding="utf-8")
    (tmp_path / "portable.txt").write_text("portable", encoding="utf-8")
    monkeypatch.setattr(launcher, "FROZEN", True)
    monkeypatch.setattr(sys, "executable", str(exe))

    def boom(*args, **kwargs):
        raise OSError("read-only file system")

    monkeypatch.setattr(Path, "mkdir", boom)
    assert launcher.portable_data_dir() is None


def test_portable_data_dir_ignored_when_not_frozen(launcher, monkeypatch, tmp_path):
    (tmp_path / "portable.txt").write_text("portable", encoding="utf-8")
    monkeypatch.setattr(launcher, "FROZEN", False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "python"))
    assert launcher.portable_data_dir() is None
