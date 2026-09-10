"""Desktop launcher: must start with no console streams (windowed Windows build)."""
from __future__ import annotations

import ast
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


def test_bridge_pick_files_uses_the_native_dialog(launcher, monkeypatch):
    """The Upload button in the desktop app opens the OS dialog and hands back paths."""
    import types

    calls = {}

    class FakeWindow:
        def create_file_dialog(self, kind, allow_multiple=False, file_types=()):
            calls["kind"] = kind
            calls["allow_multiple"] = allow_multiple
            calls["file_types"] = file_types
            return ("C:\\Users\\me\\Desktop\\manual.pdf", "C:\\Users\\me\\scan.png")

    fake = types.SimpleNamespace(OPEN_DIALOG="open", windows=[FakeWindow()])
    monkeypatch.setitem(sys.modules, "webview", fake)

    chosen = launcher.Bridge().pick_files()
    assert chosen == ["C:\\Users\\me\\Desktop\\manual.pdf", "C:\\Users\\me\\scan.png"]
    assert calls["kind"] == "open" and calls["allow_multiple"] is True
    assert any("*.pdf" in ft for ft in calls["file_types"])


def test_bridge_pick_files_cancel_is_empty(launcher, monkeypatch):
    import types

    class FakeWindow:
        def create_file_dialog(self, *a, **k):
            return None

    monkeypatch.setitem(sys.modules, "webview", types.SimpleNamespace(OPEN_DIALOG="open", windows=[FakeWindow()]))
    assert launcher.Bridge().pick_files() == []


def test_install_drop_handler_hands_paths_to_the_page(launcher, monkeypatch):
    """A drop on the window becomes an `mdi:dropped` event carrying file paths."""
    import types

    class Events:
        def __init__(self):
            self.handlers = {}

        def __getattr__(self, name):
            return self.handlers.setdefault(name, _Slot())

    class _Slot:
        def __init__(self):
            self.fns = []

        def __iadd__(self, fn):
            self.fns.append(fn)
            return self

    class Handler:
        def __init__(self, callback, prevent_default=False, stop_propagation=False, debounce=0):
            self.callback, self.prevent_default = callback, prevent_default

    body = types.SimpleNamespace(events=Events())
    window = types.SimpleNamespace(dom=types.SimpleNamespace(body=body), js=[])
    window.evaluate_js = lambda code: window.js.append(code)
    monkeypatch.setitem(sys.modules, "webview", types.SimpleNamespace())
    monkeypatch.setitem(sys.modules, "webview.dom", types.SimpleNamespace(DOMEventHandler=Handler))

    assert launcher.install_drop_handler(window) is True
    drop = body.events.handlers["drop"].fns[0]
    assert drop.prevent_default is True and body.events.handlers["dragover"].fns[0].prevent_default is True
    drop.callback({"dataTransfer": {"files": [{"name": "a.pdf", "pywebviewFullPath": "C:\\Docs\\a.pdf"}, {"name": "b.pdf"}]}})
    assert len(window.js) == 1
    assert "mdi:dropped" in window.js[0] and json.dumps(["C:\\Docs\\a.pdf"]) in window.js[0]
    drop.callback({"dataTransfer": {"files": []}})
    assert json.dumps([]) in window.js[1]


def test_install_drop_handler_without_dom_support(launcher, monkeypatch):
    import types

    monkeypatch.setitem(sys.modules, "webview", types.SimpleNamespace())
    monkeypatch.setitem(sys.modules, "webview.dom", None)  # import fails
    assert launcher.install_drop_handler(types.SimpleNamespace()) is False


def test_bridge_open_folder(launcher, monkeypatch, tmp_path):
    opened = []
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda args, **kw: opened.append(args))
    monkeypatch.setattr(launcher.sys, "platform", "linux")
    bridge = launcher.Bridge()
    assert bridge.open_folder(str(tmp_path)) is True
    assert opened == [["xdg-open", str(tmp_path)]]
    assert bridge.open_folder(str(tmp_path / "missing")) is False
    assert bridge.open_folder(str(tmp_path / "file.txt")) is False


def test_access_key_is_made_once_and_kept(launcher, tmp_path):
    key = launcher.access_key(tmp_path)
    assert key and (tmp_path / "phone-key.txt").read_text(encoding="utf-8").strip() == key
    assert launcher.access_key(tmp_path) == key  # a phone stays paired across launches


def test_env_flag(launcher, monkeypatch):
    monkeypatch.delenv("MDI_LAN", raising=False)
    assert launcher.env_flag("MDI_LAN", True) is True
    for off in ("0", "false", "no", "OFF"):
        monkeypatch.setenv("MDI_LAN", off)
        assert launcher.env_flag("MDI_LAN", True) is False
    monkeypatch.setenv("MDI_LAN", "true")
    assert launcher.env_flag("MDI_LAN", True) is True


def test_api_server_binds_where_it_is_told(launcher):
    assert launcher.ApiServer(1234).host == "127.0.0.1"
    assert launcher.ApiServer(1234, "0.0.0.0").host == "0.0.0.0"


def test_lan_addresses_are_private_ipv4(launcher):
    import ipaddress
    import sys

    sys.path.insert(0, str(LAUNCHER.parents[1] / "backend"))
    from app.api.lan import lan_addresses, phone_urls

    for addr in lan_addresses():
        ip = ipaddress.ip_address(addr)
        assert ip.version == 4 and ip.is_private and not ip.is_loopback
    assert phone_urls(8765, "abc") == [f"http://{a}:8765/?key=abc" for a in lan_addresses()]


def test_the_entry_point_hands_a_spawned_child_to_freeze_support_first():
    """The OCR reader's process is this executable started again. If anything
    ran before freeze_support(), that child would start a second app."""
    tree = ast.parse(LAUNCHER.read_text(encoding="utf-8"))
    guard = [n for n in tree.body if isinstance(n, ast.If) and "__main__" in ast.unparse(n.test)]
    assert len(guard) == 1
    statements = [ast.unparse(n) for n in guard[0].body]
    assert statements[:2] == ["import multiprocessing", "multiprocessing.freeze_support()"], statements
