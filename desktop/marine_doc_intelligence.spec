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
]
binaries, hiddenimports = [], []
for pkg in ("pymupdf", "pytesseract", "anthropic", "openpyxl", "webview"):
    d, b, h = collect_all(pkg)
    datas += d; binaries += b; hiddenimports += h
hiddenimports += collect_submodules("uvicorn") + collect_submodules("app") + [
    "sqlalchemy.dialects.sqlite", "multipart", "PIL._tkinter_finder",
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
            "CFBundleShortVersionString": "0.1.1",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "12.0",
        },
    )
