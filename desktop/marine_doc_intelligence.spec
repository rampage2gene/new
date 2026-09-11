# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build for the desktop app. Run through desktop/build.py."""
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))  # so collect_submodules("app") can import the backend
APP_NAME = "Marine Electrical Document Intelligence"
ICON = {
    "win32": ROOT / "desktop/icons/icon.ico",
    "darwin": ROOT / "desktop/icons/icon.icns",
}.get(sys.platform, ROOT / "desktop/icons/icon.png")

datas = [
    (str(ROOT / "frontend/dist"), "frontend/dist"),
    (str(ROOT / "desktop/icons"), "desktop/icons"),
    # The owner's ABYC E-11 reference tables and reminders, read-only inside
    # the app; what they confirm in the app is saved to the data folder.
    (str(ROOT / "packages/e11-calc/tables"), "reference/e11/tables"),
    (str(ROOT / "packages/e11-calc/cheatsheet"), "reference/e11/cheatsheet"),
    (str(ROOT / "packages/e11-calc/profiles"), "reference/e11/profiles"),
]
binaries, hiddenimports = [], []
for pkg in ("pymupdf", "pytesseract", "anthropic", "openpyxl", "webview", "qrcode"):
    d, b, h = collect_all(pkg)
    datas += d; binaries += b; hiddenimports += h
# The second OCR reader: PP-OCR models (.onnx) and config/default_models.yaml
# live inside the rapidocr package; onnxruntime carries native libraries.
for pkg in ("rapidocr", "onnxruntime", "pyclipper", "shapely", "omegaconf", "colorlog"):
    try:
        d, b, h = collect_all(pkg)
        datas += d; binaries += b; hiddenimports += h
    except Exception as exc:  # the app still runs with Tesseract alone
        print(f"warning: {pkg} not collected: {exc}")
hiddenimports += collect_submodules("uvicorn") + collect_submodules("app") + [
    "sqlalchemy.dialects.sqlite", "multipart", "PIL._tkinter_finder",
    # The OCR reader's child process: PyInstaller's own runtime hook handles
    # the spawn; these are the modules that spawn imports at run time.
    "multiprocessing.spawn", "multiprocessing.popen_spawn_win32", "multiprocessing.popen_spawn_posix",
    "multiprocessing.reduction", "multiprocessing.resource_tracker",
]

a = Analysis(
    [str(ROOT / "desktop/launcher.py")],
    pathex=[str(ROOT / "backend")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "scipy", "pandas", "IPython", "pytest", "cryptography", "aiohttp"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name=APP_NAME if sys.platform == "darwin" else "MarineDocIntelligence",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(ICON),
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="MarineDocIntelligence")

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name=f"{APP_NAME}.app",
        icon=str(ICON),
        bundle_identifier="com.rampage2gene.marine-doc-intelligence",
        info_plist={
            "CFBundleShortVersionString": "0.2.1",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "12.0",
        },
    )
