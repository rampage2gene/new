"""End-to-end: upload -> process -> viewer data -> search -> ask -> exports."""
from __future__ import annotations


def test_text_pdf_is_understood(manual_doc):
    d = manual_doc
    assert d["status"] == "ready", d["error"]
    assert d["page_count"] == 4 and d["embedded_text_pages"] == 4 and d["ocr_pages"] == 0
    assert d["document_type"] == "Installation Manual"
    assert d["model_number"] == "XYZ-5000"
    assert d["revision"] == "2.1" and d["publication_date"] == "March 2024"
    assert d["title"].startswith("XYZ-5000")
    assert "inverter" in d["equipment_types"]
    titles = [s["title"] for s in d["structure"]["sections"]]
    assert "2 DC Battery Connection" in titles and "2.1 Battery Bank" in titles
    assert d["structure"]["tables"] and d["structure"]["warnings"]
    assert d["stats"]["entities"]["fuse"] >= 2


def test_scanned_pdf_is_ocrd(scanned_doc, manual_doc, client):
    d = scanned_doc
    assert d["status"] == "ready", d["error"]
    assert d["ocr_pages"] == 4 and d["embedded_text_pages"] == 0
    assert d["stats"]["avg_ocr_confidence"] > 0.8
    ents = client.get(f"/api/documents/{d['id']}/entities", params={"entity_type": ["fuse", "wire_size"]}).json()
    values = {e["value_text"] for e in ents}
    assert {"300 A", "4/0 AWG", "4 AWG", "16 AWG"} <= values
    fuse = next(e for e in ents if e["value_text"] == "300 A")
    assert fuse["ocr_confidence"] is not None and fuse["page"] == 3 and fuse["bbox"][2] > fuse["bbox"][0]
    # OCR bbox should land near the embedded one for the same value.
    ref = next(e for e in client.get(f"/api/documents/{manual_doc['id']}/entities", params={"entity_type": ["fuse"]}).json() if e["value_text"] == "300 A")
    assert abs(ref["bbox"][0] - fuse["bbox"][0]) < 15 and abs(ref["bbox"][1] - fuse["bbox"][1]) < 15


def test_photo_is_ocrd(photo_doc):
    assert photo_doc["status"] == "ready" and photo_doc["file_type"] == "image"
    assert photo_doc["stats"]["entities"].get("fuse")


def test_pages_blocks_and_images(client, manual_doc):
    did = manual_doc["id"]
    pages = client.get(f"/api/documents/{did}/pages").json()
    assert len(pages) == 4 and pages[0]["text_source"] == "embedded"
    page = client.get(f"/api/documents/{did}/pages/3", params={"words": "true"}).json()
    types = {b["block_type"] for b in page["blocks"]}
    assert "heading" in types and "warning" in types
    assert all(b["section"] for b in page["blocks"] if b["block_type"] not in ("page_number", "footer", "header"))
    assert any(b.get("words") for b in page["blocks"])
    img = client.get(f"/api/documents/{did}/pages/3/image")
    assert img.status_code == 200 and img.headers["content-type"] == "image/png"
    assert client.get(f"/api/documents/{did}/file").status_code == 200


def test_spec_extraction_report(client, manual_doc):
    r = client.get(f"/api/documents/{manual_doc['id']}/spec-extraction").json()
    groups = {g["key"]: g for g in r["groups"]}
    wires = {(i["value_text"], i["application"]) for i in groups["wire_sizes"]["items"]}
    assert ("4/0 AWG", "Battery cable") in wires and ("16 AWG", "Remote / control") in wires
    fuse = groups["fuse_ratings"]["items"][0]
    assert fuse["value_text"] == "300 A" and fuse["device_type"] == "Class T" and fuse["page"] == 3 and fuse["section"] == "2 DC Battery Connection"
    assert groups["breaker_ratings"]["items"][0]["value_text"] == "32 A"
    assert groups["torque_specifications"]["items"][0]["value_text"] == "12 N·m"
    assert groups["equipment"]["items"]
    assert groups["warnings"]["count"] >= 2


def test_qc_flags_awg_cross_reference(client, manual_doc):
    flags = client.get(f"/api/documents/{manual_doc['id']}/qc").json()
    assert any(f["flag_type"] == "awg_cross_reference" for f in flags)


def test_search_keyword_semantic_entity(client, manual_doc):
    r = client.post("/api/search", json={"query": "What size fuse does this inverter require?", "document_ids": [manual_doc["id"]]}).json()
    assert r["query"]["entity_types"] == ["fuse"]
    top = r["hits"][0]
    assert top["page_number"] == 3 and top["section"] == "2 DC Battery Connection"
    assert "keyword" in top["sources"] and "entity" in top["sources"]
    r = client.post("/api/search", json={"query": "Find every mention of 48 volts", "document_ids": [manual_doc["id"]]}).json()
    assert r["query"]["value"] == 48 and r["query"]["unit"] == "V"
    assert {h["page_number"] for h in r["hits"]} >= {1, 2, 3}
    r = client.post("/api/search", json={"query": "battery charger"}).json()
    assert "charging source" in r["query"]["expansions"]["battery charger"]
    r = client.post("/api/search", json={"query": "installation clearances", "document_ids": [manual_doc["id"]]}).json()
    assert r["hits"][0]["page_number"] == 4


def test_ask_extractive_fallback_has_citations(client, manual_doc):
    r = client.post("/api/ask", json={"question": "What size fuse does this inverter require?", "document_ids": [manual_doc["id"]]}).json()
    assert r["mode"] == "extractive" and r["status"] == "partial"
    assert "300 A" in r["answer"] and "page 3" in r["answer"]
    assert r["citations"] and r["citations"][0]["page"] == 3 and r["citations"][0]["document_id"] == manual_doc["id"]
    assert any(e["entity_type"] == "fuse" for e in r["entities"])


def test_ask_not_found(client, manual_doc):
    r = client.post("/api/ask", json={"question": "zzqx flux capacitor plutonium rating", "document_ids": [manual_doc["id"]]}).json()
    assert r["status"] == "not_found" and "could not find" in r["answer"]


def test_calculator_suggestions_and_run(client, manual_doc):
    s = client.get("/api/calculators/inverter_dc_current/suggest", params={"document_id": manual_doc["id"]}).json()["suggestions"]
    assert s["power"][0]["value_text"] == "5000 W" and s["voltage"][0]["value_text"] == "48 VDC"
    r = client.post("/api/calculators/inverter_dc_current/run", json={"inputs": {"power": {"value": 5000, "source": {"document_id": manual_doc["id"], "document_name": "Manual", "page": 2}}, "voltage": 48, "efficiency": 94}}).json()
    assert abs(r["results"][0]["value"] - 110.8) < 0.1
    assert r["formula"] == "I = P ÷ V ÷ η" and r["sources"][0]["page"] == 2 and r["inputs"]["power"]["origin"] == "document"
    assert client.post("/api/calculators/dc_current/run", json={"inputs": {"power": 100}}).status_code == 422


def test_fuse_calculator_distinguishes_manufacturer_from_estimate(client):
    r = client.post("/api/calculators/fuse_protection/run", json={"inputs": {"device_type": "inverter", "continuous_current": 125, "manufacturer_fuse": {"value": 300, "source": {"document_name": "XYZ Manual", "page": 3}}, "conductor_size": "4/0 AWG", "system_voltage": 48}}).json()
    by_key = {x["key"]: x for x in r["results"]}
    assert by_key["manufacturer_required"]["classification"] == "manufacturer_required"
    assert by_key["calculated_estimate"]["value"] == 175 and by_key["calculated_estimate"]["classification"] == "calculated_estimate"
    assert by_key["recommended"]["value"] == 300 and by_key["recommended"]["classification"] == "recommended_pending_verification"
    r = client.post("/api/calculators/fuse_protection/run", json={"inputs": {"device_type": "inverter", "continuous_current": 125, "conductor_size": "6 AWG"}}).json()
    assert any("exceeds the conductor ampacity" in w for w in r["warnings"])


def test_voltage_drop(client):
    r = client.post("/api/calculators/voltage_drop/run", json={"inputs": {"voltage": 12, "current": 20, "length": 10, "length_unit": "m", "size": "10 AWG", "material": "copper"}}).json()
    pct = next(x for x in r["results"] if x["key"] == "percent")["value"]
    assert 10 < pct < 12 and r["warnings"]


def test_invoice_extraction_and_exports(client, invoice_doc):
    inv = client.get(f"/api/documents/{invoice_doc['id']}/invoice").json()
    assert inv["vendor"] == "Harbor Marine Supply" and inv["invoice_number"] == "HMS-10442"
    assert inv["invoice_date"] == "March 12, 2024" and inv["currency"] == "USD"
    assert inv["subtotal"] == 184.7 and inv["tax"] == 14.78 and inv["total"] == 199.48
    items = {li["description"]: li for li in inv["line_items"]}
    wire = items["Marine Wire 4 AWG red"]
    assert wire["quantity"] == 20 and wire["unit"] == "ft" and wire["unit_price"] == 3.96 and wire["total"] == 79.2
    csv_text = client.get("/api/export/invoices", params={"format": "csv"}).text
    assert "HMS-10442" in csv_text and "Class T Fuse 300A" in csv_text
    assert client.get("/api/export/invoices", params={"format": "xlsx", "report": "estimate"}).status_code == 200
    est = client.get("/api/export/invoices", params={"format": "json", "report": "costing"}).json()
    assert est[-1]["vendor"] == "TOTAL" and est[-1]["total"] == 199.48
    ents_csv = client.get("/api/export/entities", params={"format": "csv", "document_ids": [invoice_doc["id"]]}).text
    assert "4/0 AWG" in ents_csv


def test_compare_documents(client, manual_doc, scanned_doc):
    r = client.post("/api/compare", json={"document_ids": [manual_doc["id"], scanned_doc["id"]]}).json()
    labels = {row["label"] for row in r["table"]}
    assert "Nominal / system voltage" in labels and "Recommended fuse" in labels
    volt = next(row for row in r["table"] if row["key"] == "nominal_voltage")
    assert all(c["values"] and c["values"][0]["value"] == 48 for c in volt["cells"])
    assert r["conflicts"] == []


def test_diagram_heuristic(client, manual_doc):
    r = client.post(f"/api/documents/{manual_doc['id']}/pages/4/diagram").json()
    assert r["engine"] == "heuristic" and r["connections"] == [] and r["confidence_legend"]
    assert all(c["confidence"] == "possible" for c in r["components"])
    assert client.get(f"/api/documents/{manual_doc['id']}/pages/4/diagram").status_code == 200


def test_delete_document(client, photo_doc):
    assert client.delete(f"/api/documents/{photo_doc['id']}").status_code == 204
    assert client.get(f"/api/documents/{photo_doc['id']}").status_code == 404
