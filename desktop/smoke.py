"""Launch smoke test for a built (frozen) app: start it headless, wait for the
API, upload a small PDF (one text page, one scanned page) and wait for it to be
processed, print the app log on failure, stop it.

    python desktop/smoke.py dist/MarineDocIntelligence/MarineDocIntelligence[.exe]

Exit status 0 when `/api/status` answers 200 with a version and the uploaded
document reaches status "ready" with two pages, 1 otherwise.
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


def make_sample_pdf(path: Path) -> None:
    """Two pages: embedded text, then the same page rasterised (exercises OCR)."""
    import pymupdf  # bundled with the app; also in the build environment

    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((50, 70), "XYZ-5000 Inverter/Charger Installation Manual", fontsize=16, fontname="hebo")
    page.insert_text((50, 110), "Maximum continuous DC input current: 125 A", fontsize=11)
    page.insert_text((50, 130), "DC fuse (manufacturer specified): 300 A Class T", fontsize=11)
    page.insert_text((50, 150), "Battery cable size: 4/0 AWG, maximum length 1.5 m", fontsize=11)
    pix = page.get_pixmap(matrix=pymupdf.Matrix(200 / 72, 200 / 72), alpha=False)
    scan = doc.new_page(width=595, height=842)
    scan.insert_image(scan.rect, pixmap=pix)
    doc.save(path)
    doc.close()


def upload_and_process(base: str, pdf: Path, timeout: float = 240) -> dict:
    """POST the PDF as multipart/form-data (what the UI does) and poll until done."""
    boundary = "----mdi-smoke-boundary"
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"files\"; filename=\"{pdf.name}\"\r\n"
        f"Content-Type: application/pdf\r\n\r\n"
    ).encode() + pdf.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(base + "/api/documents", data=body, method="POST",
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        created = json.loads(r.read())
    doc_id = created[0]["id"]
    deadline = time.time() + timeout
    last = created[0]
    while time.time() < deadline:
        with urllib.request.urlopen(f"{base}/api/documents/{doc_id}", timeout=10) as r:
            last = json.loads(r.read())
        if last["status"] in ("ready", "failed"):
            break
        time.sleep(1)
    return last


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
    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + 90
    status = None
    doc = None
    diag = None
    try:
        while time.time() < deadline:
            if proc.poll() is not None:
                print(f"process exited early with code {proc.returncode}")
                break
            try:
                with urllib.request.urlopen(base + "/api/status", timeout=2) as r:
                    status = json.loads(r.read())
                    break
            except Exception:
                time.sleep(0.5)
        if status:
            try:
                with urllib.request.urlopen(base + "/api/diagnostics", timeout=5) as r:
                    diag = json.loads(r.read())
                print(f"diagnostics: log_path={diag.get('log_path')} tesseract={diag.get('tesseract_version')}")
            except Exception as exc:
                print(f"diagnostics failed: {type(exc).__name__}: {exc}")
            pdf = data_dir / "smoke-sample.pdf"
            make_sample_pdf(pdf)
            try:
                doc = upload_and_process(base, pdf)
                print(f"document: status={doc.get('status')} pages={doc.get('page_count')} "
                      f"ocr={doc.get('ocr_pages')} error={doc.get('error')}")
            except Exception as exc:
                print(f"upload failed: {type(exc).__name__}: {exc}")
                if proc.poll() is not None:
                    print(f"process died during upload/processing with code {proc.returncode}")
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
    log = data_dir / "logs" / "app.log"
    ok = bool(status) and "version" in status
    if not ok:
        print("FAILED: no healthy /api/status answer within 90 s")
    elif not diag or not diag.get("log_path"):
        ok = False
        print("FAILED: /api/diagnostics did not answer with a log path")
    elif not doc or doc.get("status") != "ready" or (doc.get("page_count") or 0) != 2:
        ok = False
        print("FAILED: the uploaded PDF was not processed to 'ready' with 2 pages")
    else:
        print(f"OK: {status}")
        print(f"log file present: {log.exists()}")
    if not ok or "-v" in os.environ.get("MDI_SMOKE_FLAGS", ""):
        print("---- app.log ----")
        print(log.read_text(encoding="utf-8", errors="replace") if log.exists() else "(no log file written)")
    return 0 if ok and log.exists() else 1


if __name__ == "__main__":
    sys.exit(main())
