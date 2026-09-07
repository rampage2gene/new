"""Desktop launcher: starts the API in-process and opens the UI in a native window.

Works both from a source checkout (`python desktop/launcher.py`) and from the
PyInstaller build produced by `desktop/build.py`. An installed copy keeps user
data in a per-user application directory, never inside the installation folder;
a portable copy (one shipped with a `portable.txt` marker) keeps it in a `data`
folder beside the executable so the whole thing travels together.
"""
from __future__ import annotations

import json
import logging
import os
import platform
import secrets
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser
from logging.handlers import RotatingFileHandler
from pathlib import Path

APP_NAME = "Marine Electrical Document Intelligence"
APP_ID = "marine-doc-intelligence"
APP_VERSION = "0.1.5"
FROZEN = getattr(sys, "frozen", False)
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
REPO_DIR = Path(__file__).resolve().parent.parent
log = logging.getLogger("desktop")


# --------------------------------------------------------------------------- logging
LOG_FILE: Path | None = None


def setup_logging(data_dir: Path) -> Path:
    """Log to `<data_dir>/logs/app.log` (rotating) as well as the console.

    A windowed build (PyInstaller `console=False` on Windows) has no console at
    all: `sys.stdout` and `sys.stderr` are None there. Anything that touches
    them, uvicorn's logging setup included, would crash the app before the
    server starts, so both streams are pointed at the log file instead.
    """
    global LOG_FILE
    log_dir = data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    LOG_FILE = log_dir / "app.log"
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    for h in list(root.handlers):
        root.removeHandler(h)
    file_handler = RotatingFileHandler(LOG_FILE, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)
    if sys.stdout is None or sys.stderr is None:
        stream = open(LOG_FILE, "a", encoding="utf-8", buffering=1)  # noqa: SIM115 - lives for the process
        if sys.stdout is None:
            sys.stdout = stream
        if sys.stderr is None:
            sys.stderr = stream
    else:
        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(fmt)
        root.addHandler(console)
    return LOG_FILE


def message_box(text: str, title: str = APP_NAME, error: bool = False) -> None:
    """Blocking native message box on Windows; a stderr line elsewhere."""
    if sys.platform == "win32":
        try:
            import ctypes

            flags = 0x10 if error else 0x40  # MB_ICONERROR / MB_ICONINFORMATION
            ctypes.windll.user32.MessageBoxW(None, text, title, flags)
            return
        except Exception:  # pragma: no cover - no user32 (unlikely)
            pass
    if sys.stderr is not None:
        print(f"{title}: {text}", file=sys.stderr)


def fatal(message: str) -> int:
    log.error(message)
    hint = f"\n\nDetails were written to:\n{LOG_FILE}" if LOG_FILE else ""
    message_box(f"{APP_NAME} could not start.\n\n{message}{hint}", error=True)
    return 1


# --------------------------------------------------------------------------- paths
def user_data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return base / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / APP_ID


def portable_data_dir() -> Path | None:
    """A portable copy keeps its data (and its log) beside the executable.

    The portable archive ships a `portable.txt` marker next to the exe. When it
    is there and the folder can be written to, documents, the database and the
    log live in `data/` alongside the program, so the app travels on a USB
    stick and `data/logs/app.log` sits next to what was double-clicked. An
    installed copy has no marker and is unaffected; a portable copy dropped
    somewhere read-only falls back to the per-user folder instead of failing.
    """
    if not FROZEN:
        return None
    exe_dir = Path(sys.executable).resolve().parent
    if not (exe_dir / "portable.txt").exists():
        return None
    target = exe_dir / "data"
    try:  # os.access lies on Windows; write something instead
        target.mkdir(parents=True, exist_ok=True)
        probe = target / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError:
        # Logging is not configured yet (this decides where the log goes), and a
        # windowed build has no stderr. `run()` logs the folder it settled on.
        return None
    return target


def frontend_dist() -> Path:
    return (BUNDLE_DIR if FROZEN else REPO_DIR) / "frontend" / "dist"


def icon_path() -> Path | None:
    root = BUNDLE_DIR / "desktop" / "icons" if FROZEN else REPO_DIR / "desktop" / "icons"
    for name in ("icon.png", "icon.ico"):
        if (root / name).exists():
            return root / name
    return None


def load_user_env(data_dir: Path) -> None:
    """Read `<data_dir>/settings.env` (KEY=value lines) into the environment.

    This is where a user of the packaged app puts MDI_ANTHROPIC_API_KEY and
    other settings; the bundle itself is read-only.
    """
    env_file = data_dir / "settings.env"
    if not env_file.exists():
        env_file.write_text(
            "# Settings for the desktop app. One KEY=value per line. Restart the app after editing.\n"
            "# MDI_ANTHROPIC_API_KEY=sk-ant-...\n"
            "# MDI_AI_MODEL=claude-opus-5\n"
            "# MDI_TESSERACT_CMD=C:\\Program Files\\Tesseract-OCR\\tesseract.exe\n"
            "# MDI_LAN=false   # do not serve the app to phones on this Wi-Fi\n"
        )
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def env_flag(name: str, default: bool = True) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off")


def access_key(data_dir: Path) -> str:
    """The pairing key a phone needs, generated once per installation.

    Serving the UI on the Wi-Fi means anything on that network can knock, so
    every API request that does not come from this computer has to carry this
    key. It is kept in `<data dir>/phone-key.txt`; delete that file and the
    next launch makes a new one, which un-pairs every phone.
    """
    key_file = data_dir / "phone-key.txt"
    try:
        existing = key_file.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    except OSError:
        pass
    key = secrets.token_urlsafe(12)
    key_file.write_text(key + "\n", encoding="utf-8")
    try:  # readable by this user only, where the OS supports it
        key_file.chmod(0o600)
    except OSError:  # pragma: no cover - Windows/FAT
        pass
    return key


def find_tesseract() -> str | None:
    """Locate Tesseract and put its folder on PATH so the OCR engine sees it."""
    import shutil

    explicit = os.environ.get("MDI_TESSERACT_CMD")
    candidates = [explicit] if explicit else []
    exe_dir = Path(sys.executable).resolve().parent
    candidates += [
        str(exe_dir / "tesseract" / ("tesseract.exe" if sys.platform == "win32" else "tesseract")),
        str(BUNDLE_DIR / "tesseract" / ("tesseract.exe" if sys.platform == "win32" else "tesseract")),
    ]
    if sys.platform == "win32":
        for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"), os.environ.get("LOCALAPPDATA")):
            if base:
                candidates.append(str(Path(base) / "Tesseract-OCR" / "tesseract.exe"))
                candidates.append(str(Path(base) / "Programs" / "Tesseract-OCR" / "tesseract.exe"))
    elif sys.platform == "darwin":
        candidates += ["/opt/homebrew/bin/tesseract", "/usr/local/bin/tesseract", "/opt/local/bin/tesseract"]
    else:
        candidates += ["/usr/bin/tesseract", "/usr/local/bin/tesseract", "/snap/bin/tesseract"]

    for cand in candidates:
        if cand and Path(cand).is_file():
            folder = str(Path(cand).parent)
            os.environ["PATH"] = folder + os.pathsep + os.environ.get("PATH", "")
            tessdata = Path(cand).parent / "tessdata"
            if tessdata.is_dir():
                os.environ.setdefault("TESSDATA_PREFIX", str(tessdata))
            return cand
    return shutil.which("tesseract")


# --------------------------------------------------------------------------- server
def free_port(preferred: int = 8765, host: str = "127.0.0.1") -> int:
    for port in (preferred, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, port))
                return s.getsockname()[1]
            except OSError:
                continue
    raise RuntimeError("no free TCP port")


class ApiServer:
    """The built-in API server.

    `host` is `0.0.0.0` when the app is also serving a phone on the Wi-Fi and
    `127.0.0.1` otherwise; either way the window itself opens the loopback
    address, so the desktop app never depends on the network being up.
    """

    def __init__(self, port: int, host: str = "127.0.0.1"):
        self.port = port
        self.host = host
        self._server = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> None:
        import uvicorn

        from app.main import app  # backend package; sys.path set in main()

        # use_colors=False: uvicorn otherwise asks sys.stdout whether it is a TTY,
        # which has no answer in a windowed build.
        config = uvicorn.Config(app, host=self.host, port=self.port, log_level="info", workers=1, use_colors=False)
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, name="api", daemon=True)
        self._thread.start()

    def wait_ready(self, timeout: float = 60.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(self.url + "/api/status", timeout=1) as r:
                    if r.status == 200:
                        return True
            except Exception:
                time.sleep(0.2)
        return False

    def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=10)


# --------------------------------------------------------------------------- window

class Bridge:
    """Functions the page can call as `window.pywebview.api.<name>()`.

    `pick_files` opens the ordinary operating-system Open dialog and returns
    the chosen paths. The page hands those to `POST /api/documents/import`, so
    the server reads the files straight off the disk and the bytes never pass
    through the web view - the one part of an upload the web view can fail
    without being able to say why.
    """

    FILE_TYPES = (
        "Documents (*.pdf;*.png;*.jpg;*.jpeg;*.tif;*.tiff;*.bmp;*.webp)",
        "All files (*.*)",
    )

    def pick_files(self) -> list[str]:
        import webview

        window = webview.windows[0]
        paths = window.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=True, file_types=self.FILE_TYPES)
        chosen = [str(p) for p in (paths or [])]
        log.info("open dialog: %d file(s) chosen", len(chosen))
        return chosen

    def open_folder(self, path: str) -> bool:
        """Show a folder (the exports folder of a document) in the file manager."""
        target = Path(str(path or "")).expanduser()
        if not target.is_dir():
            log.warning("open folder: not a folder: %s", target)
            return False
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(target))  # type: ignore[attr-defined]  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(target)])  # noqa: S603, S607
            else:
                subprocess.Popen(["xdg-open", str(target)])  # noqa: S603, S607
        except Exception as exc:  # noqa: BLE001
            log.warning("open folder failed for %s: %s", target, exc)
            return False
        log.info("open folder: %s", target)
        return True


def install_drop_handler(window) -> bool:
    """Make a drag-and-drop onto the window deliver *file paths* to the page.

    Inside the web view a drop only yields browser File objects, and reading
    those is the one step that can fail without saying why. pywebview hands
    Python the dropped files' full paths when a drop listener is registered
    from Python; the page is then told the paths (a `mdi:dropped` event) and
    imports them the same way the Open dialog does. When pywebview cannot do
    this (old version, no DOM support) the page keeps its own drop handling.
    """
    try:
        from webview.dom import DOMEventHandler
    except Exception as exc:  # noqa: BLE001
        log.info("drop: pywebview DOM events unavailable (%s); drops stay with the page", exc)
        return False

    def on_drop(event) -> None:
        files = ((event or {}).get("dataTransfer") or {}).get("files") or []
        paths = [f.get("pywebviewFullPath") for f in files if isinstance(f, dict) and f.get("pywebviewFullPath")]
        log.info("drop: %d file(s), %d with a path", len(files), len(paths))
        window.evaluate_js("window.dispatchEvent(new CustomEvent('mdi:dropped', {detail: %s}))" % json.dumps(paths))

    try:
        body = window.dom.body
        body.events.dragover += DOMEventHandler(lambda _e: None, prevent_default=True)
        body.events.drop += DOMEventHandler(on_drop, prevent_default=True)
    except Exception as exc:  # noqa: BLE001
        log.warning("drop: could not register the window drop handler: %s", exc)
        return False
    log.info("drop: window drop handler installed")
    return True


def open_window(url: str, on_close) -> bool:
    """Open `url` in a native window. Returns False when no GUI backend exists."""
    try:
        import webview
    except Exception as exc:  # pragma: no cover - depends on host GUI stack
        log.warning("pywebview unavailable (%s); falling back to the browser", exc)
        return False
    try:
        # Exports (workbooks, PDFs, conversions) are browser downloads; let the
        # native web view save them instead of swallowing them.
        try:
            webview.settings["ALLOW_DOWNLOADS"] = True
        except Exception:  # pragma: no cover - older pywebview
            pass
        window = webview.create_window(
            APP_NAME, url, width=1440, height=900, min_size=(1024, 640), text_select=True, js_api=Bridge()
        )
        window.events.closed += on_close
        window.events.loaded += lambda *_: install_drop_handler(window)
        kwargs = {}
        icon = icon_path()
        if icon and sys.platform.startswith("linux"):
            kwargs["icon"] = str(icon)
        webview.start(private_mode=False, **kwargs)
        return True
    except Exception as exc:  # pragma: no cover
        log.warning("native window failed (%s); falling back to the browser", exc)
        return False


def run() -> int:
    data_dir = Path(os.environ.get("MDI_DATA_DIR") or portable_data_dir() or user_data_dir())
    data_dir.mkdir(parents=True, exist_ok=True)
    setup_logging(data_dir)
    log.info("%s %s on %s (%s), frozen=%s", APP_NAME, APP_VERSION, platform.platform(), platform.machine(), FROZEN)
    load_user_env(data_dir)
    os.environ["MDI_DATA_DIR"] = str(data_dir)
    os.environ.setdefault("MDI_FRONTEND_DIST", str(frontend_dist()))
    os.environ.setdefault("OMP_THREAD_LIMIT", "1")

    tess = find_tesseract()
    log.info("data dir: %s", data_dir)
    log.info("tesseract: %s", tess or "NOT FOUND (scanned pages will not be OCR'd; install Tesseract)")

    if not FROZEN:
        sys.path.insert(0, str(REPO_DIR / "backend"))
    if not (frontend_dist() / "index.html").exists():
        return fatal(f"The user interface files are missing at {frontend_dist()}. Reinstall the app (developers: cd frontend && npm run build).")

    # Serving on the Wi-Fi as well as on loopback is what lets a phone open the
    # app (see the "Use on your phone" page). Windows asks once, at the first
    # launch, whether to allow that: the answer must be yes for private networks.
    lan = env_flag("MDI_LAN", True)
    host = "0.0.0.0" if lan else "127.0.0.1"  # noqa: S104 - deliberate; the pairing key is the door
    os.environ["MDI_LAN"] = "true" if lan else "false"
    if lan:
        os.environ.setdefault("MDI_ACCESS_KEY", access_key(data_dir))
    log.info("serving on %s (phone access %s)", host, "on" if lan else "off")

    port = int(os.environ.get("MDI_PORT") or free_port(host=host))
    server = ApiServer(port, host)
    server.start()
    if not server.wait_ready():
        return fatal("The built-in server did not start within 60 seconds.")
    log.info("UI at %s", server.url)

    done = threading.Event()
    headless = os.environ.get("MDI_HEADLESS", "").lower() in ("1", "true", "yes")
    if headless:
        log.info("headless mode: no window; stop the process to quit")
        try:
            while not done.is_set():
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
    elif not open_window(server.url, lambda: done.set()):
        webbrowser.open(server.url)
        if sys.platform == "win32" and FROZEN:
            # No console to Ctrl+C in a windowed build: give the user a button.
            message_box(f"{APP_NAME} is running in your web browser at {server.url}\n\nClick OK to stop the app.")
        else:
            print(f"\n{APP_NAME} is running at {server.url}\nPress Ctrl+C to quit.\n")
            try:
                while not done.is_set():
                    time.sleep(0.5)
            except KeyboardInterrupt:
                pass
    server.stop()
    return 0


def main() -> int:
    if sys.stderr is not None:  # a windowed build has no console; setup_logging() takes over
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        return run()
    except Exception as exc:  # anything unexpected: keep the reason, tell the user
        log.error("unhandled error: %s\n%s", exc, traceback.format_exc())
        return fatal(f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    sys.exit(main())
