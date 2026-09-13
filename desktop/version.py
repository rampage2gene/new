"""Print the app version (single source: backend/app/__init__.py). Used by CI."""
import re
from pathlib import Path

INIT = Path(__file__).resolve().parent.parent / "backend" / "app" / "__init__.py"
print(re.search(r'__version__ = "([^"]+)"', INIT.read_text(encoding="utf-8")).group(1))
