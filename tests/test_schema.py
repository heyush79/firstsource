"""Offline tests for the Pydantic output contract — no API key required."""

import pytest
from pydantic import ValidationError

from cdih.schema import (
    ComparisonResult,
    ExtractionResult,
    LabFlag,
    LabResult,
    TriageCategory,
)

MINIMAL_EXTRACTION = {
    "document_type": "lab_report",
    "patient": {"name": "Test Patient"},
    "clinical_summary": "A short summary.",
    "triage": {"category": "ROUTINE", "rationale": "Stable findings."},
    "overall_confidence": 0.9,
}


def test_minimal_extraction_validates():
    result = ExtractionResult.model_validate(MINIMAL_EXTRACTION)
    assert result.triage.category is TriageCategory.ROUTINE
    assert result.medications == []
    assert result.missing_information == []


def test_lab_flag_defaults_to_normal():
    lab = LabResult(test="Sodium", value="140")
    assert lab.flag is LabFlag.NORMAL


def test_confidence_out_of_range_rejected():
    bad = dict(MINIMAL_EXTRACTION, overall_confidence=1.4)
    with pytest.raises(ValidationError):
        ExtractionResult.model_validate(bad)


def test_invalid_triage_category_rejected():
    bad = dict(MINIMAL_EXTRACTION,
               triage={"category": "PANIC", "rationale": "nope"})
    with pytest.raises(ValidationError):
        ExtractionResult.model_validate(bad)


def test_comparison_result_roundtrip():
    result = ComparisonResult.model_validate({
        "same_patient": True,
        "patient_match_note": "MRN matches.",
        "summary": "Labs worsened since discharge.",
        "recommended_action": "Notify cardiology.",
    })
    data = result.model_dump_json()
    assert ComparisonResult.model_validate_json(data) == result
