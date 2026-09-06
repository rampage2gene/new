"""Synthetic documents for tests and demos (built with PyMuPDF)."""
from __future__ import annotations

from pathlib import Path

import pymupdf

MANUAL_PAGES = [
    {
        "title": "XYZ-5000 Inverter/Charger",
        "heading_size": 22,
        "lines": [
            ("Example Marine Power", 14),
            ("Installation Manual", 16),
            ("Model XYZ-5000  48 V 5000 W Inverter/Charger", 12),
            ("Revision 2.1   March 2024", 10),
            ("WARNING: Risk of fire and electric shock. Read all instructions before installing this equipment.", 10),
        ],
    },
    {
        "title": "1 Specifications",
        "heading_size": 16,
        "table": {
            "header": ["Parameter", "Value"],
            "rows": [
                ["Continuous output power", "5000 W"],
                ["Peak power (surge)", "10,000 W"],
                ["Nominal DC voltage", "48 VDC"],
                ["DC input voltage range", "40-60 V"],
                ["Maximum continuous DC current", "125 A"],
                ["AC output voltage", "230 VAC"],
                ["AC output frequency", "50 Hz"],
                ["Maximum charge current", "70 A"],
                ["Idle consumption", "12 W"],
                ["Efficiency", "94 %"],
                ["Operating temperature", "-20 to 50 °C"],
            ],
        },
        "lines": [
            ("NOTE: Ratings apply at 25 °C ambient. Derating begins above 40 °C.", 10),
        ],
    },
    {
        "title": "2 DC Battery Connection",
        "heading_size": 16,
        "lines": [
            ("Connect the inverter to the battery bank using 4/0 AWG battery cable for runs up to 3 m.", 10),
            ("Install a 300 A Class T fuse within 180 mm of the battery positive terminal. The fuse protects", 10),
            ("the battery cable, not the inverter. A 300 A fuse is required for the 4/0 AWG cable.", 10),
            ("Torque the M8 battery terminals to 12 N·m. Do not exceed 14 N·m.", 10),
            ("WARNING: Never use 4 AWG cable for the battery connection; it cannot carry the 125 A continuous current.", 10),
            ("2.1 Battery Bank", 13),
            ("The recommended minimum battery bank is 200 Ah at 48 V. Use a BMS with at least 150 A continuous discharge rating.", 10),
        ],
    },
    {
        "title": "3 AC Wiring",
        "heading_size": 16,
        "lines": [
            ("AC input: 230 VAC, 50 Hz. Protect the AC input with a 32 A double-pole circuit breaker.", 10),
            ("Use 6 mm² (10 AWG) wire for the AC input and AC output circuits.", 10),
            ("The remote control panel connects with 16 AWG control cable, maximum length 30 m.", 10),
            ("Clearance: allow 100 mm of ventilation space above and below the unit.", 10),
            ("Figure 3: AC wiring diagram", 9),
        ],
    },
]


def _draw_table(page: pymupdf.Page, x: float, y: float, header: list[str], rows: list[list[str]], col_widths=(220, 160), row_h=18) -> float:
    all_rows = [header] + rows
    for r_i, row in enumerate(all_rows):
        cx = x
        for c_i, cell in enumerate(row):
            w = col_widths[c_i]
            rect = pymupdf.Rect(cx, y, cx + w, y + row_h)
            page.draw_rect(rect, color=(0, 0, 0), width=0.6)
            page.insert_text((cx + 4, y + 13), cell, fontsize=9.5, fontname="helv" if r_i else "hebo")
            cx += w
        y += row_h
    return y


def build_manual_pdf(path: Path) -> Path:
    doc = pymupdf.open()
    for spec in MANUAL_PAGES:
        page = doc.new_page(width=595, height=842)
        y = 60
        page.insert_text((50, y), spec["title"], fontsize=spec["heading_size"], fontname="hebo")
        y += spec["heading_size"] + 16
        if "table" in spec:
            y = _draw_table(page, 50, y, spec["table"]["header"], spec["table"]["rows"]) + 16
        for text, size in spec["lines"]:
            fname = "hebo" if size > 11 else "helv"
            page.insert_text((50, y), text, fontsize=size, fontname=fname)
            y += size + 8
        page.insert_text((280, 810), str(doc.page_count), fontsize=9)
    doc.save(path)
    doc.close()
    return path


def build_scanned_pdf(source_pdf: Path, path: Path, dpi: int = 200) -> Path:
    """Rasterise a PDF into an image-only PDF (no text layer)."""
    src = pymupdf.open(source_pdf)
    out = pymupdf.open()
    for page in src:
        pix = page.get_pixmap(matrix=pymupdf.Matrix(dpi / 72, dpi / 72), alpha=False)
        img_page = out.new_page(width=page.rect.width, height=page.rect.height)
        img_page.insert_image(img_page.rect, pixmap=pix)
    out.save(path)
    out.close()
    src.close()
    return path


def build_invoice_pdf(path: Path) -> Path:
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((50, 60), "Harbor Marine Supply", fontsize=18, fontname="hebo")
    page.insert_text((50, 85), "INVOICE", fontsize=14, fontname="hebo")
    page.insert_text((50, 105), "Invoice No: HMS-10442", fontsize=10)
    page.insert_text((50, 120), "Date: March 12, 2024", fontsize=10)
    page.insert_text((50, 135), "Bill to: SV Meridian", fontsize=10)
    y = 170
    page.insert_text((50, y), "Description                                   Qty      Unit Price      Total", fontsize=10, fontname="hebo")
    y += 18
    items = [
        ("Marine Wire 4 AWG red", "20 ft", "3.96", "79.20"),
        ("Class T Fuse 300A", "1 ea", "42.50", "42.50"),
        ("Fuse holder Class T", "1 ea", "38.00", "38.00"),
        ("Heat shrink lug 4/0 AWG 3/8", "4 ea", "6.25", "25.00"),
    ]
    for desc, qty, up, tot in items:
        page.insert_text((50, y), f"{desc:<44} {qty:<8} ${up:<12} ${tot}", fontsize=10, fontname="cour")
        y += 16
    y += 10
    page.insert_text((350, y), "Subtotal: $184.70", fontsize=10); y += 16
    page.insert_text((350, y), "Sales Tax (8%): $14.78", fontsize=10); y += 16
    page.insert_text((350, y), "Total Due: $199.48", fontsize=11, fontname="hebo")
    doc.save(path)
    doc.close()
    return path


def build_photo_image(source_pdf: Path, path: Path, page_index: int = 2) -> Path:
    """A 'photograph' of one page: JPEG at modest resolution."""
    src = pymupdf.open(source_pdf)
    page = src[page_index]
    pix = page.get_pixmap(matrix=pymupdf.Matrix(2.2, 2.2), alpha=False)
    pix.save(path)
    src.close()
    return path


if __name__ == "__main__":
    import sys

    out_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "samples")
    out_dir.mkdir(parents=True, exist_ok=True)
    m = build_manual_pdf(out_dir / "XYZ-5000_Inverter_Installation_Manual.pdf")
    build_scanned_pdf(m, out_dir / "XYZ-5000_Manual_scanned.pdf")
    build_invoice_pdf(out_dir / "Harbor_Marine_Invoice_HMS-10442.pdf")
    build_photo_image(m, out_dir / "Battery_connection_photo.jpg")
    print("wrote samples to", out_dir)
