"""The installation reminders: one entry per rule, each with the clause and
page of the owner's copy of the standard. The Markdown render is byte for
byte the one packages/e11-calc produces; both are held to the same file.
"""
from __future__ import annotations

import html
import json
import logging
from pathlib import Path
from typing import Any

from ..config import get_settings

log = logging.getLogger(__name__)


class CheatSheetError(ValueError):
    pass


def load_cheatsheet(raw: Any) -> dict:
    """Refuses an entry without a clause or a page: a reminder with no way back to the page is a guess."""
    if not isinstance(raw, dict):
        raise CheatSheetError("cheat sheet is not a JSON object")
    source = raw.get("source")
    if not isinstance(source, dict) or not isinstance(source.get("document"), str):
        raise CheatSheetError("cheat sheet has no source.document")
    if not isinstance(raw.get("entries"), list):
        raise CheatSheetError("cheat sheet has no entries")
    entries = []
    for i, e in enumerate(raw["entries"], start=1):
        if not isinstance(e, dict):
            raise CheatSheetError(f"entry {i} is not an object")
        for key in ("topic", "rule", "clause"):
            if not isinstance(e.get(key), str) or not e[key].strip():
                raise CheatSheetError(f"entry {i} has no {key}")
        page = e.get("page")
        if not isinstance(page, int) or isinstance(page, bool) or page < 1:
            raise CheatSheetError(f'entry {i} ("{str(e.get("rule"))[:40]}") has no page')
        tags = [str(t) for t in e["applies_to"]] if isinstance(e.get("applies_to"), list) and e["applies_to"] else ["always"]
        entries.append({"topic": e["topic"], "rule": e["rule"], "clause": e["clause"], "page": page, "applies_to": tags, "status": "confirmed" if e.get("status") == "confirmed" else "draft"})
    out = {"source": {"document": source["document"]}, "entries": entries}
    if isinstance(source.get("edition"), str):
        out["source"]["edition"] = source["edition"]
    return out


def reminders_for(sheet: dict, tags: list[str]) -> list[dict]:
    wanted = {"always", *tags}
    return [e for e in sheet["entries"] if any(t in wanted for t in e["applies_to"])]


def _topics(sheet: dict) -> list[tuple[str, list[dict]]]:
    out: dict[str, list[dict]] = {}
    for e in sheet["entries"]:
        out.setdefault(e["topic"], []).append(e)
    return list(out.items())


def _md_cell(s: str) -> str:
    return s.replace("|", "\\|").replace("\r\n", " ").replace("\n", " ")


def _title(sheet: dict) -> str:
    ed = sheet["source"].get("edition")
    return f"{sheet['source']['document']}{f' ({ed})' if ed else ''}"


def render_markdown(sheet: dict) -> str:
    lines = [
        f"# Installation reminders from {_title(sheet)}",
        "",
        "Every rule names the clause and page of the owner's own copy; a rule marked *draft* has not yet been checked against its page.",
        "",
    ]
    for topic, entries in _topics(sheet):
        lines += [f"## {topic}", "", "| Rule | Clause | Page |", "|---|---|---|"]
        for e in entries:
            lines.append(f"| {_md_cell(e['rule'])}{' *(draft)*' if e['status'] == 'draft' else ''} | {_md_cell(e['clause'])} | p. {e['page']} |")
        lines.append("")
    return "\n".join(lines)


def _esc(s: str) -> str:
    return html.escape(s, quote=True).replace("&#x27;", "'")


def render_html(sheet: dict) -> str:
    title = _title(sheet)
    parts = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>Installation reminders from {_esc(title)}</title>",
        "<style>body{font:15px/1.5 system-ui,sans-serif;max-width:60rem;margin:2rem auto;padding:0 1rem;color:#1a1a1a;background:#fff}table{border-collapse:collapse;width:100%;margin-bottom:1.5rem}th,td{text-align:left;vertical-align:top;padding:.4rem .6rem;border-bottom:1px solid #ddd}th{font-size:.8rem;text-transform:uppercase;letter-spacing:.04em;color:#555}td.page{white-space:nowrap}em.draft{color:#8a5a00}</style>",
        "</head><body>",
        f"<h1>Installation reminders from {_esc(title)}</h1>",
        '<p>Every rule names the clause and page of the owner\'s own copy; a rule marked <em class="draft">draft</em> has not yet been checked against its page.</p>',
    ]
    for topic, entries in _topics(sheet):
        parts += [f"<h2>{_esc(topic)}</h2>", "<table><thead><tr><th>Rule</th><th>Clause</th><th>Page</th></tr></thead><tbody>"]
        for e in entries:
            draft = ' <em class="draft">(draft)</em>' if e["status"] == "draft" else ""
            parts.append(f'<tr><td>{_esc(e["rule"])}{draft}</td><td>{_esc(e["clause"])}</td><td class="page">p. {e["page"]}</td></tr>')
        parts.append("</tbody></table>")
    parts += ["</body></html>", ""]
    return "\n".join(parts)


# ------------------------------------------------------------------ the app's copy

def _paths() -> list[tuple[str, Path]]:
    s = get_settings()
    return [("yours", s.user_reference_dir / "cheatsheet" / "cheatsheet.json"), ("bundled", Path(s.reference_dir) / "cheatsheet" / "cheatsheet.json")]


def get_cheatsheet() -> tuple[dict | None, str | None]:
    """The owner's saved sheet if there is one, else the bundled one, else None. Returns (sheet, origin)."""
    for origin, path in _paths():
        if path.exists():
            try:
                return load_cheatsheet(json.loads(path.read_text(encoding="utf-8"))), origin
            except (CheatSheetError, json.JSONDecodeError) as exc:
                log.warning("cheat sheet %s not loaded: %s", path, exc)
    return None, None


def save_cheatsheet(raw: Any) -> Path:
    sheet = load_cheatsheet(raw)
    path = get_settings().user_reference_dir / "cheatsheet" / "cheatsheet.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sheet, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
