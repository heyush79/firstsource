"""Offline tests for the ingestion router — no API key required."""

from pathlib import Path

import pytest

from cdih import ingest

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def test_text_file_routes_as_text():
    doc = ingest.from_file("note.txt", b"Patient presents with cough.")
    assert doc.ingest_mode == "text"
    assert "cough" in doc.preview_text


def test_pasted_text():
    doc = ingest.from_text("BP 120/80, HR 72")
    assert doc.ingest_mode == "text"
    assert doc.source_name == "pasted text"


def test_digital_pdf_takes_local_text_path():
    data = (SAMPLES / "lab_report.pdf").read_bytes()
    doc = ingest.from_file("lab_report.pdf", data)
    assert doc.ingest_mode == "pdf-text"
    assert "Potassium" in doc.preview_text


def test_scanned_pdf_falls_back_to_vision():
    # A tiny valid PDF with no text content at all.
    empty_pdf = (
        b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
        b"trailer<</Root 1 0 R>>\n%%EOF"
    )
    doc = ingest.from_file("scan.pdf", empty_pdf)
    assert doc.ingest_mode == "pdf-vision"


def test_image_routes_to_vision():
    data = (SAMPLES / "intake_form.png").read_bytes()
    doc = ingest.from_file("intake_form.png", data)
    assert doc.ingest_mode == "image-vision"


def test_unsupported_extension_raises():
    with pytest.raises(ValueError, match="Unsupported file type"):
        ingest.from_file("virus.exe", b"nope")
