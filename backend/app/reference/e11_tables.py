"""Reads the JSON tables and refuses anything that could pass a guess off as
the standard: a table without a page, a row without a page, a draft nobody
has confirmed against the page, or the synthetic test fixture outside a test.

Two folders, one loader: the owner's own tables in <data dir>/reference/e11
(what the editor in the app saves) win over the copy bundled with the app,
which is read-only once installed.
"""
from __future__ import annotations

import json
import logging
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import get_settings

log = logging.getLogger(__name__)

TABLE_IDS = (
    "constants",
    "circular_mils",
    "ampacity_outside_engine_space",
    "ampacity_inside_engine_space",
    "bundling_factors",
    "voltage_drop_3pct",
    "voltage_drop_10pct",
    "fuse_classes",
)
STATUSES = ("draft", "confirmed", "fixture")
KINDS = ("constants", "circular_mils", "ampacity", "bundling", "voltage_drop_grid", "fuse_classes")
KIND_OF = {
    "constants": "constants", "circular_mils": "circular_mils",
    "ampacity_outside_engine_space": "ampacity", "ampacity_inside_engine_space": "ampacity",
    "bundling_factors": "bundling", "voltage_drop_3pct": "voltage_drop_grid", "voltage_drop_10pct": "voltage_drop_grid",
    "fuse_classes": "fuse_classes",
}


class TableError(ValueError):
    def __init__(self, file: str, message: str):
        super().__init__(f"{file}: {message}")
        self.file = file


@dataclass
class E11Tables:
    by_id: dict[str, dict] = field(default_factory=dict)
    fixture: bool = False
    #: where each table came from, for the status view
    origin: dict[str, str] = field(default_factory=dict)


def _is_page(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and x >= 1


def _is_num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _need(file: str, ok: bool, what: str) -> None:
    if not ok:
        raise TableError(file, what)


def validate_table(file: str, raw: Any) -> dict:
    """Check one table's shape. Cells may be null (not printed); pages may not."""
    _need(file, isinstance(raw, dict), "is not a JSON object")
    t: dict = raw
    _need(file, isinstance(t.get("id"), str) and t["id"], "has no id")
    _need(file, isinstance(t.get("kind"), str), "has no kind")
    _need(file, isinstance(t.get("title"), str), "has no title (the table's name as printed)")
    _need(file, t.get("status") in STATUSES, f"status must be one of {', '.join(STATUSES)}")
    source = t.get("source")
    _need(file, isinstance(source, dict) and isinstance(source.get("document"), str), "has no source.document")
    if t["kind"] != "fuse_classes":
        _need(file, _is_page(source.get("page")), "has no source.page - every table must say which page it was copied from")
    rows = t.get("rows")
    kind = t["kind"]
    if kind == "constants":
        values = t.get("values")
        _need(file, isinstance(values, dict) and isinstance(values.get("K_copper"), dict), "constants needs values.K_copper")
        k = values["K_copper"]
        _need(file, _is_num(k.get("value")) and _is_page(k.get("page")), "K_copper needs a numeric value and its page")
        _need(file, t.get("length_definition") in ("round_trip", "one_way"), 'constants needs length_definition "round_trip" or "one_way", as the page words the formula')
    elif kind == "circular_mils":
        _need(file, isinstance(rows, list) and rows, "needs rows")
        for r in rows:
            _need(file, isinstance(r, dict) and isinstance(r.get("size_awg"), str) and _is_num(r.get("circular_mils")) and _is_page(r.get("page")), "every circular_mils row needs size_awg, circular_mils and page")
    elif kind == "ampacity":
        _need(file, isinstance(t.get("columns"), dict) and t["columns"], "ampacity needs columns keyed by insulation rating")
        _need(file, isinstance(rows, list) and rows, "needs rows")
        for r in rows:
            _need(file, isinstance(r, dict) and isinstance(r.get("size_awg"), str) and isinstance(r.get("values"), dict) and _is_page(r.get("page")), "every ampacity row needs size_awg, values and page")
            for col, v in r["values"].items():
                _need(file, v is None or _is_num(v), f"ampacity cell {r['size_awg']}/{col} must be a number or null")
    elif kind == "bundling":
        _need(file, isinstance(rows, list) and rows, "needs rows")
        for r in rows:
            _need(file, isinstance(r, dict) and _is_num(r.get("min_conductors")) and (r.get("max_conductors") is None or _is_num(r.get("max_conductors"))) and _is_num(r.get("factor")) and _is_page(r.get("page")), "every bundling row needs min_conductors, max_conductors (or null), factor and page")
    elif kind == "voltage_drop_grid":
        _need(file, _is_num(t.get("nominal_voltage")) and _is_num(t.get("drop_percent")), "voltage_drop_grid needs nominal_voltage and drop_percent")
        _need(file, t.get("length_unit") in ("ft", "m"), 'voltage_drop_grid needs length_unit "ft" or "m"')
        _need(file, t.get("length_definition") in ("round_trip", "one_way"), 'voltage_drop_grid needs length_definition "round_trip" or "one_way", as the page words the column heading')
        _need(file, isinstance(t.get("lengths"), list) and t["lengths"], "voltage_drop_grid needs lengths")
        _need(file, isinstance(rows, list) and rows, "needs rows")
        for r in rows:
            _need(file, isinstance(r, dict) and _is_num(r.get("current")) and isinstance(r.get("sizes"), dict) and _is_page(r.get("page")), "every voltage_drop_grid row needs current, sizes and page")
    elif kind == "fuse_classes":
        _need(file, isinstance(rows, list), "needs rows")
        for r in rows:
            _need(file, isinstance(r, dict) and isinstance(r.get("class"), str) and _is_num(r.get("interrupting_rating_a")) and isinstance(r.get("suits"), list), "every fuse_classes row needs class, interrupting_rating_a and suits")
            src = r.get("source")
            _need(file, isinstance(src, dict) and isinstance(src.get("document"), str) and _is_page(src.get("page")), f"fuse class {r['class']} needs source.document and source.page (the datasheet it was read from)")
    else:
        raise TableError(file, f'unknown kind "{kind}"')
    return t


def load_tables(files: dict[str, Any], allow_fixture: bool = False, origin: str = "") -> E11Tables:
    """Load a set of tables from parsed JSON, keyed by file name."""
    out = E11Tables()
    for file, raw in files.items():
        t = validate_table(file, raw)
        if t["status"] == "fixture":
            if not allow_fixture:
                raise TableError(file, "is the synthetic test fixture, not a table from the standard; refused outside a test")
            out.fixture = True
        _need(file, t["id"] in TABLE_IDS, f'unknown table id "{t["id"]}"; expected one of {", ".join(TABLE_IDS)}')
        out.by_id[t["id"]] = t
        out.origin[t["id"]] = origin
    return out


def read_dir(directory: Path) -> dict[str, Any]:
    files: dict[str, Any] = {}
    if directory.is_dir():
        for p in sorted(directory.glob("*.json")):
            files[p.name] = json.loads(p.read_text(encoding="utf-8"))
    return files


def load_tables_from_dirs(dirs: list[tuple[str, Path]], allow_fixture: bool = False) -> E11Tables:
    """First folder wins: the owner's saved tables, then the bundled copy."""
    out = E11Tables()
    for origin, directory in dirs:
        try:
            part = load_tables(read_dir(directory), allow_fixture, origin)
        except (TableError, json.JSONDecodeError) as exc:
            log.warning("reference tables in %s not loaded: %s", directory, exc)
            continue
        out.fixture = out.fixture or part.fixture
        for tid, t in part.by_id.items():
            if tid not in out.by_id:
                out.by_id[tid] = t
                out.origin[tid] = origin
    return out


def usable(tables: E11Tables, table_id: str) -> dict | None:
    """A table the engine may use: present and confirmed (a fixture counts in tests). A draft is loaded but unusable."""
    t = tables.by_id.get(table_id)
    if not t or t["status"] == "draft":
        return None
    return t


def tables_status(tables: E11Tables) -> list[dict]:
    out = []
    for tid in TABLE_IDS:
        t = tables.by_id.get(tid)
        if not t:
            out.append({"id": tid, "kind": KIND_OF[tid], "title": None, "page": None, "status": "missing", "rows": 0, "origin": None})
            continue
        rows = len(t["rows"]) if isinstance(t.get("rows"), list) else 1
        out.append({"id": tid, "kind": t["kind"], "title": t["title"], "page": t["source"].get("page"), "status": t["status"], "rows": rows, "origin": tables.origin.get(tid), "document_id": t["source"].get("document_id")})
    return out


# ------------------------------------------------------------------ the app's copy

_lock = threading.Lock()
_cache: dict[str, E11Tables] = {}


def _dirs() -> list[tuple[str, Path]]:
    s = get_settings()
    return [("yours", s.user_reference_dir / "tables"), ("bundled", Path(s.reference_dir) / "tables")]


def get_tables() -> E11Tables:
    """The tables the app computes with, cached until reset()."""
    key = "|".join(str(d) for _, d in _dirs())
    with _lock:
        if key not in _cache:
            _cache[key] = load_tables_from_dirs(_dirs(), get_settings().reference_allow_fixture)
        return _cache[key]


def reset() -> None:
    with _lock:
        _cache.clear()


_SAFE_ID = re.compile(r"^[a-z0-9_]+$")


def save_table(table: dict) -> Path:
    """Write one table to the owner's folder, after the same checks the loader makes."""
    t = validate_table(f"{table.get('id', '?')}.json", table)
    if t["status"] == "fixture":
        raise TableError(f"{t['id']}.json", "the synthetic fixture cannot be saved as a reference table")
    _need(f"{t['id']}.json", t["id"] in TABLE_IDS and bool(_SAFE_ID.match(t["id"])), f'unknown table id "{t["id"]}"')
    directory = get_settings().user_reference_dir / "tables"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{t['id']}.json"
    path.write_text(json.dumps(t, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    reset()
    return path


def delete_table(table_id: str) -> bool:
    """Remove the owner's copy of a table; the bundled copy, if any, shows again."""
    if table_id not in TABLE_IDS:
        return False
    path = get_settings().user_reference_dir / "tables" / f"{table_id}.json"
    if path.exists():
        path.unlink()
        reset()
        return True
    return False
