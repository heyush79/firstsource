"""Pydantic models defining the structured output contract with the LLM.

These models are passed to Gemini as a response schema, so the model is
constrained to return valid JSON matching this shape — no free-text parsing.
"""

from enum import Enum

from pydantic import BaseModel, Field


class DocumentType(str, Enum):
    DISCHARGE_SUMMARY = "discharge_summary"
    LAB_REPORT = "lab_report"
    PHYSICIAN_NOTE = "physician_note"
    INTAKE_FORM = "intake_form"
    REFERRAL_LETTER = "referral_letter"
    OTHER = "other"


class TriageCategory(str, Enum):
    EMERGENCY = "EMERGENCY"
    URGENT = "URGENT"
    ROUTINE = "ROUTINE"
    ADMINISTRATIVE = "ADMINISTRATIVE"


class Severity(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class LabFlag(str, Enum):
    NORMAL = "normal"
    LOW = "low"
    HIGH = "high"
    CRITICAL = "critical"


class Patient(BaseModel):
    name: str | None = None
    age: str | None = None
    sex: str | None = None
    date_of_birth: str | None = None
    patient_id: str | None = Field(None, description="MRN or any identifier printed on the document")


class Diagnosis(BaseModel):
    name: str
    status: str | None = Field(None, description="active, resolved, suspected, or historical")
    icd10_hint: str | None = Field(None, description="Likely ICD-10 code if confidently inferable, else null")


class Medication(BaseModel):
    name: str
    dose: str | None = None
    frequency: str | None = None
    route: str | None = None


class Vital(BaseModel):
    name: str
    value: str
    unit: str | None = None


class LabResult(BaseModel):
    test: str
    value: str
    unit: str | None = None
    reference_range: str | None = None
    flag: LabFlag = LabFlag.NORMAL


class RiskFlag(BaseModel):
    flag: str = Field(description="Short label, e.g. 'Critically low potassium'")
    severity: Severity
    rationale: str = Field(description="One sentence citing the evidence in the document")


class Triage(BaseModel):
    category: TriageCategory
    rationale: str
    suggested_department: str | None = None
    recommended_next_steps: list[str] = Field(default_factory=list)


class FieldConfidence(BaseModel):
    field: str = Field(description="Section name, e.g. 'patient', 'medications', 'lab_results'")
    confidence: float = Field(ge=0.0, le=1.0)
    note: str | None = Field(None, description="Why confidence is reduced, if it is")


class ExtractionResult(BaseModel):
    """Everything the pipeline extracts from one clinical document."""

    document_type: DocumentType
    document_date: str | None = None
    patient: Patient
    chief_complaint: str | None = None
    diagnoses: list[Diagnosis] = Field(default_factory=list)
    medications: list[Medication] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    vitals: list[Vital] = Field(default_factory=list)
    lab_results: list[LabResult] = Field(default_factory=list)
    key_findings: list[str] = Field(default_factory=list)
    clinical_summary: str = Field(description="3-5 sentence plain-language summary for clinical staff")
    risk_flags: list[RiskFlag] = Field(default_factory=list)
    triage: Triage
    field_confidence: list[FieldConfidence] = Field(default_factory=list)
    overall_confidence: float = Field(ge=0.0, le=1.0)
    missing_information: list[str] = Field(
        default_factory=list,
        description="Clinically relevant items the document does NOT contain",
    )


# ---------------------------------------------------------------------------
# Multi-document comparison (optional enhancement)
# ---------------------------------------------------------------------------

class ChangeType(str, Enum):
    ADDED = "added"
    REMOVED = "removed"
    CHANGED = "changed"
    UNCHANGED = "unchanged"


class MedicationChange(BaseModel):
    medication: str
    change: ChangeType
    detail: str | None = None


class LabTrend(BaseModel):
    test: str
    trend: str = Field(description="improved, worsened, stable, or new")
    detail: str


class ComparisonResult(BaseModel):
    """Comparison of two documents for the same patient (e.g. discharge vs follow-up)."""

    same_patient: bool
    patient_match_note: str
    medication_changes: list[MedicationChange] = Field(default_factory=list)
    diagnosis_changes: list[str] = Field(default_factory=list)
    lab_trends: list[LabTrend] = Field(default_factory=list)
    discrepancies: list[str] = Field(
        default_factory=list,
        description="Conflicting information between the two documents that staff should reconcile",
    )
    summary: str
    recommended_action: str
