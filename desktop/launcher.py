"""Desktop launcher: starts the API in-process and opens the UI in a native window.

Works both from a source checkout (`python desktop/launcher.py`) and from the
PyInstaller build produced by `desktop/build.py`. All user data lives in a
per-user application directory, never inside the installation folder.
"""
from __future__ import annotations

import logging
import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

APP_NAME = "Marine Electrical Document Intelligence"
APP_ID = "marine-doc-intelligence"
FROZEN = getattr(sys, "frozen", False)
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
REPO_DIR = Path(__file__).resolve().parent.parent
log = logging.getLogger("desktop")


# --------------------------------------------------------------------------- paths
def user_data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return base / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / APP_ID


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
        )
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


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
def free_port(preferred: int = 8765) -> int:
    for port in (preferred, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return s.getsockname()[1]
            except OSError:
                continue
    raise RuntimeError("no free TCP port")


class ApiServer:
    def __init__(self, port: int):
        self.port = port
        self._server = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> None:
        import uvicorn

        from app.main import app  # backend package; sys.path set in main()

        config = uvicorn.Config(app, host="127.0.0.1", port=self.port, log_level="info", workers=1)
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
def open_window(url: str, on_close) -> bool:
    """Open `url` in a native window. Returns False when no GUI backend exists."""
    try:
        import webview
    except Exception as exc:  # pragma: no cover - depends on host GUI stack
        log.warning("pywebview unavailable (%s); falling back to the browser", exc)
        return False
    try:
        window = webview.create_window(
            APP_NAME, url, width=1440, height=900, min_size=(1024, 640), text_select=True
        )
        window.events.closed += on_close
        kwargs = {}
        icon = icon_path()
        if icon and sys.platform.startswith("linux"):
            kwargs["icon"] = str(icon)
        webview.start(private_mode=False, **kwargs)
        return True
    except Exception as exc:  # pragma: no cover
        log.warning("native window failed (%s); falling back to the browser", exc)
        return False


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    data_dir = Path(os.environ.get("MDI_DATA_DIR") or user_data_dir())
    data_dir.mkdir(parents=True, exist_ok=True)
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
        log.error("frontend build missing at %s (run: cd frontend && npm run build)", frontend_dist())

    port = int(os.environ.get("MDI_PORT") or free_port())
    server = ApiServer(port)
    server.start()
    if not server.wait_ready():
        log.error("API did not start; see the log above")
        return 1
    log.info("UI at %s", server.url)

    done = threading.Event()
    if not open_window(server.url, lambda: done.set()):
        webbrowser.open(server.url)
        print(f"\n{APP_NAME} is running at {server.url}\nPress Ctrl+C to quit.\n")
        try:
            while not done.is_set():
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
    server.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
