"""Verification: every value read from a scan is checked against an
independent second reading of the same spot on the page.

The ladder, from the pipeline's point of view:

1. Reader 1 is the engine whose text became the page (usually RapidOCR).
   The extractor found the value in that text.
2. Reader 2 is the other engine's reading of the same page (kept as
   ``RawPage.alt_ocr``). The lines overlapping the value's box are parsed
   with the same extractor. Agreement on value and unit → ``confirmed`` at
   100%: two engines built differently read the same thing.
3. No agreement → a third, targeted read: the value's box is cropped from
   the page render, enlarged, binarised and read as a single line. Two of
   three agreeing settles it at 95% (``confirmed`` when reader 1 wins,
   ``corrected`` when the other reading wins and the value is replaced).
4. No majority → ``to_fill``: the value is blanked, the readings are kept,
   and a QC flag asks the user to fill it in from the page. A blank is an
   honest answer; a guess is not.
5. Optionally, when an Anthropic key is configured, the blanks are shown
   to the model together with the page image; it may declare a value
   legible (applied at 100% when it matches a reading, 95% otherwise) or
   unreadable (stays blank). Nothing leaves the machine without a key.

Values from embedded PDF text are not touched: the PDF is its own ground
truth there.
"""
from __future__ import annotations

import base64
import logging
import re
from dataclasses import asdict, dataclass

from PIL import Image

from ..config import get_settings
from ..ingest.types import RawBlock, RawPage
from ..qc.validate import QCFlagData
from . import patterns as P
from .entities import ExtractedEntity, _extract_from_block

log = logging.getLogger(__name__)

# Types whose numbers are the same measurement seen from different contexts:
# reader 2 sees "300 A" without the word "fuse" and calls it a current.
_FAMILIES = {
    "current": "amps", "fuse": "amps", "breaker": "amps",
}
_VERIFICATION_FLAGS = {"reading_conflict", "reading_corrected", "reading_unverified"}


@dataclass
class VerificationReport:
    checked: int = 0
    confirmed: int = 0
    corrected: int = 0
    to_fill: int = 0
    unverified: int = 0
    reader1: str | None = None
    reader2: str | None = None
    ai: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------- readings


def _family(entity_type: str) -> str:
    return _FAMILIES.get(entity_type, entity_type)


def _norm_text(t: str) -> str:
    return re.sub(r"[\s\-–—_.,;:()]+", "", (t or "")).lower()


def candidates_from_text(text: str, page_number: int, entity_type: str) -> list[ExtractedEntity]:
    """Run the extractor over a piece of text and keep the values of the same family."""
    if not text or not text.strip():
        return []
    page = RawPage(page_number=page_number, width=1000.0, height=1000.0)
    block = RawBlock(text=text, bbox=(0.0, 0.0, 0.0, 0.0), source="ocr", confidence=1.0)
    try:
        found = _extract_from_block(page, 0, block)
    except Exception as exc:  # noqa: BLE001 - a reading must never break processing
        log.debug("verify: extractor failed on %r: %s", text[:80], exc)
        return []
    fam = _family(entity_type)
    return [e for e in found if _family(e.entity_type) == fam]


def comparable(ent: ExtractedEntity, cand: ExtractedEntity) -> bool:
    """A candidate is a reading *of this value* only when it measures the same
    thing: same unit ("6 mm²" next to "10 AWG" on one line is another value,
    not another reading), and for equipment a model number to compare."""
    if ent.entity_type == "equipment":
        return bool(ent.equipment_model) == bool(cand.equipment_model)
    return (ent.unit or "") == (cand.unit or "")


def same_value(a: ExtractedEntity, b: ExtractedEntity) -> bool:
    if a.entity_type == "equipment" or b.entity_type == "equipment":
        am = (a.equipment_model or a.value_text or "").upper()
        bm = (b.equipment_model or b.value_text or "").upper()
        return _norm_text(am) == _norm_text(bm) and bool(am)
    if a.value is not None and b.value is not None:
        tol = 1e-6 * max(1.0, abs(a.value))
        return abs(a.value - b.value) <= tol and (a.unit or "") == (b.unit or "")
    return _norm_text(a.value_text) == _norm_text(b.value_text) and bool(a.value_text)


def lines_over(entity: ExtractedEntity, lines: list[dict]) -> list[dict]:
    """The second reader's lines that cover the value's box."""
    x0, y0, x1, y1 = entity.bbox
    height = max(1.0, y1 - y0)
    hits = []
    for ln in lines or []:
        bx0, by0, bx1, by1 = ln.get("bbox") or (0, 0, 0, 0)
        v_overlap = min(y1, by1) - max(y0, by0)
        if v_overlap < 0.5 * height:
            continue
        if min(x1, bx1) - max(x0, bx0) < -0.5 * height:
            continue
        hits.append(ln)
    hits.sort(key=lambda ln: (round(ln["bbox"][1] / 5), ln["bbox"][0]))
    return hits


# --------------------------------------------------------------------------- third read


CROP_DPI = 300


class TieBreaker:
    """Reads one value's line again: a sharp crop from the source (the PDF
    rendered at 300 dpi, or the original image), enlarged, single-line OCR."""

    def __init__(self, source_path: str | None = None, file_type: str | None = None) -> None:
        self._engine = None
        self._images: dict[str, Image.Image] = {}
        self._pdf = None
        self._source_image: Image.Image | None = None
        self.available = False
        try:
            from ..ocr.tesseract import TesseractEngine

            eng = TesseractEngine()
            if eng.available():
                self._engine = eng
                self.available = True
        except Exception as exc:  # noqa: BLE001
            log.debug("verify: no tie-break engine: %s", exc)
        if source_path and file_type == "pdf":
            try:
                import pymupdf

                self._pdf = pymupdf.open(source_path)
            except Exception as exc:  # noqa: BLE001
                log.debug("verify: cannot open source PDF %s: %s", source_path, exc)
        elif source_path:
            try:
                from PIL import ImageOps

                self._source_image = ImageOps.exif_transpose(Image.open(source_path)).convert("RGB")
            except Exception as exc:  # noqa: BLE001
                log.debug("verify: cannot open source image %s: %s", source_path, exc)

    def close(self) -> None:
        pdf = getattr(self, "_pdf", None)
        if pdf is not None:
            try:
                pdf.close()
            except Exception:  # noqa: BLE001
                pass
            self._pdf = None

    def _render_image(self, page: RawPage) -> Image.Image | None:
        """Fallback: the display render already on disk."""
        if not page.image_path:
            return None
        img = self._images.get(page.image_path)
        if img is None:
            try:
                img = Image.open(page.image_path).convert("RGB")
            except Exception as exc:  # noqa: BLE001
                log.debug("verify: cannot open %s: %s", page.image_path, exc)
                return None
            self._images[page.image_path] = img
        return img

    def _line_rect(self, page: RawPage, entity: ExtractedEntity) -> tuple[float, float, float, float]:
        x0, y0, x1, y1 = entity.bbox
        h = max(1.0, y1 - y0)
        # Take the whole line the value sits on: the unit may be a word away.
        return (
            max(0.0, x0 - 6 * h),
            max(0.0, y0 - 0.35 * h),
            min(float(page.width), x1 + 6 * h),
            min(float(page.height), y1 + 0.35 * h),
        )

    def crop(self, page: RawPage, entity: ExtractedEntity) -> Image.Image | None:
        if not page.width or not page.height:
            return None
        left, top, right, bottom = self._line_rect(page, entity)
        if right - left < 2 or bottom - top < 2:
            return None
        if self._pdf is not None and 0 <= page.page_number - 1 < self._pdf.page_count:
            try:
                import pymupdf

                pg = self._pdf[page.page_number - 1]
                zoom = CROP_DPI / 72.0
                pix = pg.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=pymupdf.Rect(left, top, right, bottom), alpha=False)
                mode = "RGB" if pix.n < 4 else "RGBA"
                return Image.frombytes(mode, (pix.width, pix.height), pix.samples).convert("RGB")
            except Exception as exc:  # noqa: BLE001
                log.debug("verify: clip render failed: %s", exc)
        img = self._source_image or self._render_image(page)
        if img is None:
            return None
        scale = img.width / float(page.width)
        box = tuple(int(round(v * scale)) for v in (left, top, right, bottom))
        if box[2] - box[0] < 4 or box[3] - box[1] < 4:
            return None
        return img.crop(box)

    def read(self, page: RawPage, entity: ExtractedEntity) -> str | None:
        if self._engine is None:
            return None
        crop = self.crop(page, entity)
        if crop is None:
            return None
        try:
            blocks = self._engine.recognize_line(crop)
        except Exception as exc:  # noqa: BLE001
            log.debug("verify: re-read failed: %s", exc)
            return None
        text = " ".join(w.text for b in blocks for w in b.words).strip()
        return text or None


# --------------------------------------------------------------------------- the pass


def verify_entities(
    pages: list[RawPage],
    entities: list[ExtractedEntity],
    source_path: str | None = None,
    file_type: str | None = None,
) -> tuple[VerificationReport, list[QCFlagData]]:
    settings = get_settings()
    report = VerificationReport()
    flags: list[QCFlagData] = []
    by_number = {p.page_number: p for p in pages}
    ocr_pages = [p for p in pages if p.text_source == "ocr"]
    if ocr_pages:
        report.reader1 = ocr_pages[0].ocr_engine
        report.reader2 = next((p.alt_ocr_engine for p in ocr_pages if p.alt_ocr_engine), None)
    tie = TieBreaker(source_path, file_type)
    to_fill: list[int] = []
    try:
        for idx, ent in enumerate(entities):
            _verify_one(idx, ent, by_number, tie, report, flags, to_fill)
    finally:
        tie.close()

    if to_fill and settings.verify_ai:
        report.ai = _ai_check(pages, entities, to_fill, report)
    elif to_fill:
        report.ai = "off"

    for idx in to_fill:
        ent = entities[idx]
        if (ent.extra.get("verification") or {}).get("status") != "to_fill":
            continue  # the AI settled it
        readings = ent.extra["verification"]["readings"]
        seen = " / ".join(f"'{v}'" for v in readings.values() if v)
        severity = "critical" if ent.entity_type in P.SAFETY_CRITICAL_TYPES else "warning"
        flags.append(QCFlagData(
            "reading_conflict", severity,
            f"Readings differ for a {ent.entity_type.replace('_', ' ')} on page {ent.page_number} ({seen}). "
            f"Left blank - fill it in from the page.",
            idx, ent.page_number, {"readings": readings},
        ))
    return report, flags


def _verify_one(idx: int, ent: ExtractedEntity, by_number: dict, tie: TieBreaker, report: VerificationReport, flags: list, to_fill: list[int]) -> None:
    page = by_number.get(ent.page_number)
    if page is None or ent.ocr_confidence is None or page.text_source != "ocr":
        return  # embedded text: the PDF is the ground truth
    report.checked += 1
    readings: dict[str, str | None] = {"reader1": ent.value_text}
    alt_lines = lines_over(ent, page.alt_ocr or [])
    alt_text = " ".join(ln.get("t", "") for ln in alt_lines) if alt_lines else ""
    alt_cands = [c for c in candidates_from_text(alt_text, ent.page_number, ent.entity_type) if comparable(ent, c)] if alt_text else []
    alt_match = next((c for c in alt_cands if same_value(ent, c)), None)
    readings["reader2"] = alt_match.value_text if alt_match else (alt_cands[0].value_text if alt_cands else None)

    if alt_match is not None:
        _mark(ent, "confirmed", 1.0, readings, note="2 readers")
        report.confirmed += 1
        return

    # Third read on a sharp crop of the line.
    reread_text = tie.read(page, ent) if tie.available else None
    reread_cands = [c for c in candidates_from_text(reread_text or "", ent.page_number, ent.entity_type) if comparable(ent, c)] if reread_text else []
    reread_match_1 = next((c for c in reread_cands if same_value(ent, c)), None)
    reread_match_2 = None
    if alt_cands:
        for c in reread_cands:
            if any(same_value(a, c) for a in alt_cands):
                reread_match_2 = c
                break
    readings["reread"] = reread_match_1.value_text if reread_match_1 else (reread_cands[0].value_text if reread_cands else None)

    if reread_match_1 is not None:
        _mark(ent, "confirmed", 0.95, readings, note="majority of 3")
        report.confirmed += 1
        return
    if reread_match_2 is not None:
        original = ent.value_text
        _apply(ent, reread_match_2)
        _mark(ent, "corrected", 0.95, readings, note="majority of 3", original=original)
        flags.append(QCFlagData(
            "reading_corrected", "info",
            f"{ent.entity_type.replace('_', ' ').capitalize()} on page {ent.page_number} was read as '{original}' "
            f"but two other readings say '{ent.value_text}'; the value was corrected.",
            idx, ent.page_number, {"original": original, "readings": readings},
        ))
        report.corrected += 1
        return
    if not alt_cands and not reread_cands:
        # Nobody else could read this spot: not a conflict, just a single reading.
        _mark(ent, "unverified", None, readings, note="1 reader")
        report.unverified += 1
        flags.append(QCFlagData(
            "reading_unverified", "info",
            f"{ent.entity_type.replace('_', ' ').capitalize()} '{ent.value_text}' on page {ent.page_number} "
            f"could not be checked by a second reading; confirm it on the page.",
            idx, ent.page_number, {"readings": readings},
        ))
        return
    # A real conflict: leave it blank.
    _withhold(ent, readings)
    to_fill.append(idx)
    report.to_fill += 1


def _mark(ent: ExtractedEntity, status: str, confidence: float | None, readings: dict, note: str | None = None, original: str | None = None) -> None:
    info = {"status": status, "readings": dict(readings)}
    if note:
        info["note"] = note
    if original is not None:
        info["original"] = original
    ent.extra["verification"] = info
    if confidence is not None:
        ent.confidence = confidence


def _apply(ent: ExtractedEntity, other: ExtractedEntity) -> None:
    ent.value = other.value
    ent.unit = other.unit
    ent.value_text = other.value_text
    for key in ("awg", "nm_equivalent", "range"):
        if key in other.extra:
            ent.extra[key] = other.extra[key]
        else:
            ent.extra.pop(key, None)


def _withhold(ent: ExtractedEntity, readings: dict) -> None:
    ent.extra["verification"] = {"status": "to_fill", "readings": dict(readings), "original": ent.value_text}
    ent.value = None
    ent.value_text = ""
    ent.confidence = 0.0


# --------------------------------------------------------------------------- optional AI check


def _ai_check(pages: list[RawPage], entities: list[ExtractedEntity], to_fill: list[int], report: VerificationReport) -> str:
    try:
        from ..ai.client import ai_available, structured_call
    except Exception as exc:  # noqa: BLE001
        return f"skipped: {exc}"
    if not ai_available():
        return "skipped: no API key"
    from pydantic import BaseModel, Field

    class Verdict(BaseModel):
        index: int = Field(description="the index given for the value")
        legible: bool = Field(description="true only when the value is clearly readable at the marked spot")
        value_text: str | None = Field(default=None, description="the value exactly as printed, with its unit, when legible")

    class Verdicts(BaseModel):
        verdicts: list[Verdict]

    system = (
        "You check numbers that two OCR programs read differently on a scanned page of a marine electrical document. "
        "For each listed value look at the marked spot on the page image. Report a value only when it is clearly "
        "legible; when it is smudged, cut off or ambiguous say it is not legible. Never infer a value from context, "
        "never guess, never complete a partial number."
    )
    by_number = {p.page_number: p for p in pages}
    by_page: dict[int, list[int]] = {}
    for idx in to_fill:
        by_page.setdefault(entities[idx].page_number, []).append(idx)
    limit = get_settings().ai_verify_max_pages
    settled = 0
    errors = 0
    for n, (page_number, idxs) in enumerate(sorted(by_page.items())):
        if n >= limit:
            break
        page = by_number.get(page_number)
        if page is None or not page.image_path:
            continue
        try:
            with open(page.image_path, "rb") as f:
                data = base64.standard_b64encode(f.read()).decode("ascii")
        except OSError:
            continue
        listing = []
        for idx in idxs:
            e = entities[idx]
            x0, y0, x1, y1 = e.bbox
            pct = [round(100 * v / (page.width if i % 2 == 0 else page.height), 1) for i, v in enumerate((x0, y0, x1, y1))]
            readings = e.extra.get("verification", {}).get("readings", {})
            listing.append(f"index {idx}: a {e.entity_type.replace('_', ' ')} at [{pct[0]}%, {pct[1]}%, {pct[2]}%, {pct[3]}%] of the page "
                           f"(readings so far: {', '.join(repr(v) for v in readings.values() if v)})")
        content = [
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": data}},
            {"type": "text", "text": f"Page {page_number}. Values to check:\n" + "\n".join(listing)},
        ]
        try:
            out: Verdicts = structured_call(system, content, Verdicts, max_tokens=2000)
        except Exception as exc:  # noqa: BLE001
            errors += 1
            log.warning("verify: AI check failed on page %s: %s", page_number, exc)
            continue
        for v in out.verdicts:
            if v.index not in idxs or not v.legible or not v.value_text:
                continue
            e = entities[v.index]
            cands = candidates_from_text(v.value_text, page_number, e.entity_type)
            if not cands:
                continue
            pick = cands[0]
            readings = e.extra["verification"]["readings"]
            readings["ai"] = pick.value_text
            original = e.extra["verification"].get("original")
            _apply(e, pick)
            agrees = any(_norm_text(r or "") == _norm_text(pick.value_text) for k, r in readings.items() if k != "ai")
            _mark(e, "ai_confirmed" if agrees else "ai_corrected", 1.0 if agrees else 0.95, readings,
                  note="AI read the page", original=original)
            settled += 1
            report.to_fill -= 1
            if agrees:
                report.confirmed += 1
            else:
                report.corrected += 1
    return f"settled {settled} of {len(to_fill)}" + (f", {errors} page(s) failed" if errors else "")
