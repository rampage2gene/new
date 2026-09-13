"""The RapidOCR reader in a process of its own.

onnxruntime is native code. When native code crashes there is no exception
to catch: the process simply ends, and when that process was the server, the
app's window, its server and every document being read went with it. So the
reader runs in a child process. A crash there costs one page's second reading
- the page is still read by Tesseract and the document finishes - and the
reader is started again for the next page.

Protocol over one duplex pipe, parent to child:
    ("recognize", (width, height), rgb_bytes)   a page, raw RGB
    ("quit",)
child to parent, first message then one per page:
    ("ready", version) | ("unavailable", reason)
    ("ok", list[OCRBlock]) | ("error", "Type: message")

Raw bytes rather than PNG: the pipe is local, and encoding a 300 dpi page
costs a second or more each way for nothing.
"""
from __future__ import annotations

import logging
import multiprocessing
import os
import sys
import threading
import time
from multiprocessing.connection import wait
from pathlib import Path

from PIL import Image

from .base import OCRBlock, ReaderStopped

log = logging.getLogger(__name__)

_worker: OCRWorker | None = None
_worker_lock = threading.Lock()


def get_worker() -> OCRWorker:
    global _worker
    with _worker_lock:
        if _worker is None:
            _worker = OCRWorker()
        return _worker


class OCRWorker:
    """Parent side. One lock serialises pages, as the in-process reader's lock did."""

    def __init__(self) -> None:
        from ..config import get_settings

        self._ctx = multiprocessing.get_context("spawn")  # never fork: this process has threads
        self._lock = threading.Lock()
        self._proc = None
        self._conn = None
        self._state: tuple[str, str | None] | None = None  # ("ready", version) | ("unavailable", reason)
        self.restarts = 0
        self.stops = 0
        self.failed_starts = 0
        self.last_exit_code: int | None = None
        # The test hook arms only the first worker this parent starts. Read
        # from the environment in the child, every restarted worker would
        # crash again and the app would never get a page read.
        self._crash_armed = bool(get_settings().ocr_crash_once)

    # ----------------------------------------------------------------- public
    def available(self) -> bool:
        with self._lock:
            self._ensure()
            return self._state is not None and self._state[0] == "ready"

    def unavailable_reason(self) -> str | None:
        with self._lock:
            self._ensure()
            return self._state[1] if self._state and self._state[0] == "unavailable" else None

    def status(self) -> dict:
        proc = self._proc
        return {
            "pid": proc.pid if proc is not None and proc.exitcode is None else None,
            "ready": bool(self._state and self._state[0] == "ready"),
            "version": self._state[1] if self._state and self._state[0] == "ready" else None,
            "error": self._state[1] if self._state and self._state[0] == "unavailable" else None,
            "restarts": self.restarts,
            "stops": self.stops,
            "last_exit_code": self.last_exit_code,
            "log": str(self._log_path()),
        }

    def recognize(self, image: Image.Image) -> list[OCRBlock]:
        from ..config import get_settings

        with self._lock:
            self._ensure()
            if not self._state or self._state[0] != "ready" or self._proc is None:
                return []  # no reader: the same answer the in-process engine gives
            rgb = image.convert("RGB")
            try:
                self._conn.send(("recognize", rgb.size, rgb.tobytes()))
            except (OSError, EOFError, ValueError):
                self._stopped("could not be given the page")
            timeout = get_settings().ocr_page_timeout
            ready = wait([self._conn, self._proc.sentinel], timeout=timeout)
            if self._conn in ready:
                try:
                    msg = self._conn.recv()
                except (EOFError, OSError):
                    msg = None
                if msg is None:
                    self._stopped("stopped while reading the page")
                if msg[0] == "ok":
                    return msg[1]
                raise RuntimeError(msg[1])  # an ordinary failure inside the reader; the page goes on without it
            if ready:  # the process ended before answering
                self._stopped("stopped while reading the page")
            self._kill()
            self.stops += 1
            log.error("rapidocr: the reader did not answer within %.0f s and was stopped", timeout)
            raise ReaderStopped(f"the RapidOCR reader did not answer within {timeout:.0f} s and was stopped")

    def stop(self) -> None:
        """End the worker (tests, shutdown). It is started again on demand."""
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.send(("quit",))
                except (OSError, EOFError, ValueError):
                    pass
            if self._proc is not None:
                self._proc.join(2)
            self._kill()
            self._proc = None

    # ---------------------------------------------------------------- private
    def _log_path(self) -> Path:
        from ..config import get_settings

        folder = get_settings().data_dir / "logs"
        folder.mkdir(parents=True, exist_ok=True)
        return folder / "ocr-worker.log"

    def _alive(self) -> bool:
        return self._proc is not None and self._proc.exitcode is None and self._conn is not None

    def _ensure(self) -> None:
        """A live worker, unless the reader has been found unusable."""
        if self._alive():
            return
        if self._state and self._state[0] == "unavailable":
            return
        if self._proc is not None:
            # It died between pages, or was stopped: no page was lost.
            self.last_exit_code = self._proc.exitcode
            self.restarts += 1
        self._start()

    def _start(self) -> None:
        from ..config import get_settings

        timeout = get_settings().ocr_start_timeout
        parent, child = self._ctx.Pipe(duplex=True)
        proc = self._ctx.Process(
            target=_child_main, args=(child, str(self._log_path()), self._crash_armed), name="ocr-worker", daemon=True
        )
        self._crash_armed = False
        proc.start()
        child.close()  # or this end stays open here and the child's death never reads as EOF
        self._proc, self._conn = proc, parent
        msg = None
        if parent in wait([parent, proc.sentinel], timeout=timeout):
            try:
                msg = parent.recv()
            except (EOFError, OSError):
                msg = None
        if msg and msg[0] == "ready":
            self._state = ("ready", msg[1])
            log.info("rapidocr: reader running in process %s (rapidocr %s)", proc.pid, msg[1])
            return
        self.failed_starts += 1
        if msg and msg[0] == "unavailable":
            reason = str(msg[1])
        elif proc.exitcode is not None or not proc.is_alive():
            proc.join(1)
            reason = f"the reader stopped while loading its models (exit code {proc.exitcode})"
        else:
            reason = f"the reader did not finish loading within {timeout:.0f} s"
        self.last_exit_code = proc.exitcode
        self._kill()
        if (msg and msg[0] == "unavailable") or self.failed_starts >= 2:
            # Not installed, or it crashes on load: do not start it again on
            # every page. Diagnostics shows this reason.
            self._state = ("unavailable", f"{reason}; see {self._log_path()}")
            log.warning("rapidocr unavailable: %s", self._state[1])
        else:
            self._state = None
            log.warning("rapidocr: %s; it will be tried once more", reason)

    def _stopped(self, what: str) -> None:
        """The child died under a request: record it, clean up, tell the caller."""
        proc = self._proc
        if proc is not None:
            proc.join(1)
        code = proc.exitcode if proc is not None else None
        self.last_exit_code = code
        self.stops += 1
        self._kill()
        log.error("rapidocr: the reader %s (exit code %s); see %s", what, code, self._log_path())
        raise ReaderStopped(f"the RapidOCR reader {what} (exit code {code})")

    def _kill(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except OSError:
                pass
            self._conn = None
        if self._proc is not None and self._proc.exitcode is None:
            self._proc.kill()
            self._proc.join(5)


# ------------------------------------------------------------------ the child
def _child_main(conn, log_path: str, crash_once: bool) -> None:
    """Runs in the worker process. Imports only this package's reader modules:
    importing the application would start a second database and inbox
    watcher. Nothing may escape this function - the parent has no console,
    and multiprocessing's own error path writes to a stderr that is None."""
    try:
        stream = _child_streams(log_path)
        import faulthandler

        faulthandler.enable(file=stream, all_threads=True)  # a native crash leaves its traceback here

        from . import rapid

        engine = rapid.load()
        if engine is None:
            conn.send(("unavailable", rapid.load_error()))
            return
        conn.send(("ready", rapid.rapid_version()))
        import numpy as np

        while True:
            try:
                msg = conn.recv()
            except (EOFError, OSError):
                return  # the parent is gone
            if msg[0] == "quit":
                return
            if msg[0] != "recognize":
                continue
            if crash_once:
                crash_once = False
                _crash_hard()
            _, (width, height), data = msg
            try:
                arr = np.frombuffer(data, dtype=np.uint8).reshape(height, width, 3)
                conn.send(("ok", rapid.recognize_array(arr)))
            except Exception as exc:  # noqa: BLE001 - reported to the parent, not raised here
                conn.send(("error", f"{type(exc).__name__}: {exc}"))
    except Exception:  # noqa: BLE001
        try:
            logging.getLogger(__name__).exception("the OCR worker failed")
        except Exception:  # noqa: BLE001
            pass


def _child_streams(log_path: str):
    """Log to <data>/logs/ocr-worker.log. A child of the windowed build has
    no console: sys.stdout and sys.stderr are None, so both point at the log,
    before rapidocr is imported (its log handler binds sys.stderr then)."""
    from logging.handlers import RotatingFileHandler

    stream = open(log_path, "a", encoding="utf-8", buffering=1)  # noqa: SIM115 - lives for the process
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    handler = RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=1, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)
    logging.getLogger("RapidOCR").setLevel(logging.WARNING)
    logging.getLogger(__name__).info("ocr worker started, pid %s", os.getpid())
    return stream


def _crash_hard() -> None:
    """The test hook: die the way native code dies, with no Python exception.
    A ctypes null write is not that on Windows (it becomes an OSError), and
    os.abort() can raise a Windows Error Reporting dialog that hangs a build
    runner; the exit code of an access violation, without the violation, is
    what the parent sees either way."""
    if sys.platform == "win32":
        os._exit(0xC0000005)
    import signal

    os.kill(os.getpid(), signal.SIGSEGV)
    time.sleep(5)  # the signal is delivered asynchronously
    os._exit(139)
