"""Build the desktop application for the current operating system.

    python desktop/build.py            # frontend build + icons + PyInstaller
    python desktop/build.py --skip-frontend

Output: dist/MarineDocIntelligence/ (Windows, Linux) or
        dist/Marine Electrical Document Intelligence.app (macOS).
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(cmd: list[str], cwd: Path = ROOT) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-frontend", action="store_true", help="reuse frontend/dist")
    args = ap.parse_args()

    if not args.skip_frontend:
        npm = shutil.which("npm") or shutil.which("npm.cmd")
        if not npm:
            print("npm not found; install Node.js or pass --skip-frontend with an existing frontend/dist", file=sys.stderr)
            return 1
        if not (ROOT / "frontend/node_modules").exists():
            run([npm, "install", "--no-audit", "--no-fund"], cwd=ROOT / "frontend")
        run([npm, "run", "build"], cwd=ROOT / "frontend")
    if not (ROOT / "frontend/dist/index.html").exists():
        print("frontend/dist/index.html missing", file=sys.stderr)
        return 1

    run([sys.executable, str(ROOT / "desktop/make_icon.py")])
    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", str(ROOT / "desktop/marine_doc_intelligence.spec")])

    if sys.platform.startswith("linux"):
        out = ROOT / "dist/MarineDocIntelligence"
        shutil.copy(ROOT / "desktop/linux/marine-doc-intelligence.desktop", out)
        shutil.copy(ROOT / "desktop/linux/install-desktop-entry.sh", out)
        shutil.copy(ROOT / "desktop/icons/icon.png", out / "icon.png")
    print("\nBuild complete. See dist/ .")
    return 0


if __name__ == "__main__":
    sys.exit(main())
