"""Launch smoke test for a built (frozen) app: start it headless, wait for the
API, print the app log on failure, stop it.

    python desktop/smoke.py dist/MarineDocIntelligence/MarineDocIntelligence[.exe]

Exit status 0 when `/api/status` answers 200 with a version, 1 otherwise.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    exe = Path(sys.argv[1]).resolve()
    if not exe.exists():
        print(f"not found: {exe}")
        return 1
    port = free_port()
    data_dir = Path(tempfile.mkdtemp(prefix="mdi-smoke-"))
    env = {**os.environ, "MDI_HEADLESS": "1", "MDI_PORT": str(port), "MDI_DATA_DIR": str(data_dir)}
    print(f"starting {exe} on port {port}, data in {data_dir}")
    proc = subprocess.Popen([str(exe)], env=env, cwd=str(exe.parent))
    url = f"http://127.0.0.1:{port}/api/status"
    deadline = time.time() + 90
    status = None
    try:
        while time.time() < deadline:
            if proc.poll() is not None:
                print(f"process exited early with code {proc.returncode}")
                break
            try:
                with urllib.request.urlopen(url, timeout=2) as r:
                    status = json.loads(r.read())
                    break
            except Exception:
                time.sleep(0.5)
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
    log = data_dir / "logs" / "app.log"
    ok = bool(status) and "version" in status
    if ok:
        print(f"OK: {status}")
        print(f"log file present: {log.exists()}")
    else:
        print("FAILED: no healthy /api/status answer within 90 s")
    if not ok or "-v" in os.environ.get("MDI_SMOKE_FLAGS", ""):
        print("---- app.log ----")
        print(log.read_text(encoding="utf-8", errors="replace") if log.exists() else "(no log file written)")
    return 0 if ok and log.exists() else 1


if __name__ == "__main__":
    sys.exit(main())
