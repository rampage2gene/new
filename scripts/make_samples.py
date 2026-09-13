#!/usr/bin/env python3
"""Generate sample documents (text manual, scanned manual, invoice, photo) for a demo."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from tests.fixtures import build_invoice_pdf, build_manual_pdf, build_photo_image, build_scanned_pdf  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else "samples")
out.mkdir(parents=True, exist_ok=True)
manual = build_manual_pdf(out / "XYZ-5000_Inverter_Installation_Manual.pdf")
build_scanned_pdf(manual, out / "XYZ-5000_Manual_scanned.pdf")
build_invoice_pdf(out / "Harbor_Marine_Invoice_HMS-10442.pdf")
build_photo_image(manual, out / "Battery_connection_photo.jpg")
print(f"Sample documents written to {out}/")
