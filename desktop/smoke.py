"""Launch smoke test for a built (frozen) app: start it headless, wait for the
API, upload a small PDF (one text page, one scanned page) and wait for it to be
processed, print the app log on failure, stop it.

    python desktop/smoke.py dist/MarineDocIntelligence/MarineDocIntelligence[.exe]

Exit status 0 when `/api/status` answers 200 with a version and the uploaded
document reaches status "ready" with two pages, 1 otherwise.
"""
from __future__ import annotations

import json
import shutil
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


def post_multipart(base: str, path: str, parts: list[tuple[str, str, str, bytes]]) -> object:
    """POST `parts` as multipart/form-data: (field, filename, content type, bytes)."""
    boundary = "----mdi-smoke-boundary"
    body = b""
    for field, filename, content_type, data in parts:
        body += (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"; filename=\"{filename}\"\r\n"
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode() + data + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    req = urllib.request.Request(base + path, data=body, method="POST",
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def poll_document(base: str, doc_id: str, timeout: float = 240) -> dict:
    deadline = time.time() + timeout
    last: dict = {}
    while time.time() < deadline:
        with urllib.request.urlopen(f"{base}/api/documents/{doc_id}", timeout=10) as r:
            last = json.loads(r.read())
        if last["status"] in ("ready", "failed"):
            break
        time.sleep(1)
    return last


def wait_for_exports(base: str, doc: dict, timeout: float = 90) -> dict:
    """Keep reading the document until its exports folder is on disk.

    A document reports "ready" before the exports folder has been written -
    that is the documented contract, the folder is produced once processing
    finishes and again after every edit - so reading the document once at
    "ready" and asking where its exports are is a coin flip. Wait for them.
    """
    if doc.get("status") != "ready":
        return doc
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _exports_ok((doc.get("stats") or {}).get("export_dir")):
            break
        time.sleep(1)
        doc = poll_document(base, doc["id"], timeout=30)
    return doc


def upload_and_process(base: str, pdf: Path, timeout: float = 240) -> dict:
    """POST the PDF as multipart/form-data (what the UI does) and poll until done."""
    created = post_multipart(base, "/api/documents", [("files", pdf.name, "application/pdf", pdf.read_bytes())])
    return wait_for_exports(base, poll_document(base, created[0]["id"], timeout))


def scan_and_process(base: str, pdf: Path, timeout: float = 240) -> dict:
    """What the phone's camera button does: photographs of two pages, one document."""
    import pymupdf

    doc = pymupdf.open(pdf)
    shots = [doc[i].get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False).tobytes("png") for i in range(len(doc))]
    doc.close()
    parts = [("pages", f"page-{i + 1}.png", "image/png", data) for i, data in enumerate(shots)]
    created = post_multipart(base, "/api/documents/scan", parts)
    return poll_document(base, created["id"], timeout)


def phone_check(base: str, data_dir: Path) -> dict:
    """The phone door: the address to scan, the QR image, and the pairing key file."""
    with urllib.request.urlopen(base + "/api/lan", timeout=10) as r:
        info = json.loads(r.read())
    info["key_file"] = (data_dir / "phone-key.txt").exists()
    info["qr"] = None
    if info.get("urls"):
        with urllib.request.urlopen(base + "/api/lan/qr.png", timeout=10) as r:
            info["qr"] = r.headers.get("Content-Type")
    return info



def inbox_roundtrip(data_dir: Path, pdf: Path, timeout: float = 240) -> Path | None:
    """Copy the PDF into <data_dir>/inbox and wait for done/<stem>.ocr.pdf."""
    inbox = data_dir / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    target = inbox / "inbox-sample.pdf"
    shutil.copyfile(pdf, target)
    expected = inbox / "done" / "inbox-sample.ocr.pdf"
    deadline = time.time() + timeout
    while time.time() < deadline:
        if expected.exists():
            return expected
        failed = list((inbox / "failed").glob("inbox-sample*")) if (inbox / "failed").exists() else []
        if failed:
            print(f"inbox: file moved to failed/: {[f.name for f in failed]}")
            for f in failed:
                if f.suffix == ".txt":
                    print(f.read_text(encoding="utf-8", errors="replace"))
            return None
        time.sleep(1)
    return None


def _exports_ok(folder: str | None) -> bool:
    if not folder:
        return False
    names = {p.name for p in Path(folder).glob("*")}
    return any(n.endswith(".xlsx") for n in names) and any(n.endswith(".clean.pdf") for n in names)


def quit_and_wait(base: str, proc: subprocess.Popen) -> dict:
    """"Stop the app" on the page: the server answers 204 and the process ends
    within ten seconds. In a browser tab this button is the only way to stop
    the app, so it has to work on every platform."""
    req = urllib.request.Request(base + "/api/quit", method="POST")
    with urllib.request.urlopen(req, timeout=5) as r:
        code = r.status
    started = time.time()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        return {"code": code, "exited": False, "seconds": round(time.time() - started, 1)}
    return {"code": code, "exited": True, "seconds": round(time.time() - started, 1), "returncode": proc.returncode}


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
    inbox_out = None
    phone: dict | None = None
    scan: dict | None = None
    quit: dict | None = None
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
                stats = doc.get("stats") or {}
                print(f"document: status={doc.get('status')} pages={doc.get('page_count')} "
                      f"ocr={doc.get('ocr_pages')} error={doc.get('error')}")
                print(f"readers: {stats.get('ocr_engines')} verification={stats.get('verification')}")
                print(f"exports: {stats.get('export_dir')} {stats.get('export_files')}")
            except Exception as exc:
                print(f"upload failed: {type(exc).__name__}: {exc}")
                if proc.poll() is not None:
                    print(f"process died during upload/processing with code {proc.returncode}")
            try:
                inbox_out = inbox_roundtrip(data_dir, pdf)
                print(f"inbox: {'wrote ' + str(inbox_out) if inbox_out else 'no OCR PDF appeared'}")
            except Exception as exc:
                print(f"inbox failed: {type(exc).__name__}: {exc}")
            try:
                phone = phone_check(base, data_dir)
                print(f"phone: enabled={phone.get('enabled')} key_file={phone.get('key_file')} "
                      f"urls={phone.get('urls')} qr={phone.get('qr')}")
            except Exception as exc:
                print(f"phone check failed: {type(exc).__name__}: {exc}")
            try:
                scan = scan_and_process(base, pdf)
                print(f"camera scan: status={scan.get('status')} pages={scan.get('page_count')} error={scan.get('error')}")
            except Exception as exc:
                print(f"camera scan failed: {type(exc).__name__}: {exc}")
            try:
                quit = quit_and_wait(base, proc)
                print(f"stop the app: answered {quit.get('code')}, exited={quit.get('exited')} "
                      f"code={quit.get('returncode')} after {quit.get('seconds')}s")
            except Exception as exc:
                print(f"stop the app failed: {type(exc).__name__}: {exc}")
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
    elif "rapidocr" not in ((doc.get("stats") or {}).get("ocr_engines") or []):
        ok = False
        print("FAILED: the bundled RapidOCR reader did not read the scanned page (stats.ocr_engines)")
    elif ((doc.get("stats") or {}).get("verification") or {}).get("reader2") != "tesseract":
        ok = False
        print("FAILED: the second reader (Tesseract) did not run, so values were not cross-checked")
    elif not _exports_ok((doc.get("stats") or {}).get("export_dir")):
        ok = False
        folder = (doc.get("stats") or {}).get("export_dir")
        holds = sorted(p.name for p in Path(folder).glob("*")) if folder else "(the document names no exports folder)"
        print(f"FAILED: the exports folder is missing the workbook or the clean PDF: {folder} holds {holds}")
    elif not inbox_out or inbox_out.stat().st_size == 0:
        ok = False
        print("FAILED: a PDF copied into the inbox folder did not come back as done/<name>.ocr.pdf")
    elif not phone or not phone.get("enabled") or not phone.get("key_file"):
        ok = False
        print("FAILED: phone access is not set up (/api/lan or the pairing key file)")
    elif phone.get("urls") and phone.get("qr") != "image/png":
        ok = False
        print("FAILED: the QR code for the phone is not a PNG")
    elif not scan or scan.get("status") != "ready" or (scan.get("page_count") or 0) != 2:
        ok = False
        print("FAILED: photographed pages were not processed into a 2-page document")
    elif not quit or quit.get("code") != 204 or not quit.get("exited") or quit.get("returncode") != 0:
        ok = False
        print(f"FAILED: 'Stop the app' (POST /api/quit) did not stop the app cleanly within 10 s: {quit}")
    else:
        print(f"OK: {status}")
        print(f"log file present: {log.exists()}")
    if not ok or "-v" in os.environ.get("MDI_SMOKE_FLAGS", ""):
        print("---- app.log ----")
        print(log.read_text(encoding="utf-8", errors="replace") if log.exists() else "(no log file written)")
    return 0 if ok and log.exists() else 1


if __name__ == "__main__":
    sys.exit(main())
