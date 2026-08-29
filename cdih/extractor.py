"""LLM extraction layer: calls Gemini with a constrained JSON response schema.

Key design decisions
--------------------
- Schema-constrained decoding (`response_schema`) instead of "please return
  JSON" prompting — the API guarantees parseable output matching our Pydantic
  models, so there is no brittle post-hoc parsing.
- Low temperature: extraction should be deterministic, not creative.
- Explicit anti-hallucination rules in the prompt: missing = null, never
  invented; confidence must reflect legibility/ambiguity of the source.
- Model fallback + retry: the free tier rate-limits aggressively, so we retry
  with backoff and fall back across models.
"""

import os
import time

from google import genai
from google.genai import types
from google.genai import errors as genai_errors

from .ingest import IngestedDocument
from .schema import ComparisonResult, ExtractionResult

# Ordered by preference; all available on the AI Studio free tier.
MODEL_CANDIDATES = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.5-flash-lite",
]

EXTRACTION_PROMPT = """\
You are a clinical document intelligence assistant used by clinical and
administrative staff at a mid-size healthcare provider. Read the attached
clinical document and extract structured information.

Rules:
1. Extract ONLY what the document states. If a field is absent, return null or
   an empty list. NEVER invent names, values, doses, or dates.
2. For lab results, flag each value against the reference range printed in the
   document; use flag "critical" only for values that are dangerously abnormal.
3. risk_flags: surface anything a clinician should notice quickly — critical
   labs, drug allergies vs prescribed drugs, red-flag symptoms, missed
   follow-ups. Each rationale must cite evidence from the document.
4. triage: classify the recommended handling of this document:
   - EMERGENCY: findings needing immediate clinical attention (critical labs,
     red-flag symptoms).
   - URGENT: needs clinician review within 24-48h (significant abnormalities,
     new concerning symptoms).
   - ROUTINE: standard follow-up or stable findings.
   - ADMINISTRATIVE: no clinical action; filing/billing/records only.
5. field_confidence: score each major section (patient, diagnoses, medications,
   allergies, vitals, lab_results) between 0 and 1. Lower the score when the
   source is illegible, ambiguous, abbreviated, or inferred — and say why in
   the note. overall_confidence summarises the whole extraction.
6. missing_information: list clinically relevant items this document type
   would normally contain but doesn't.
7. clinical_summary: 3-5 plain-language sentences a busy clinician can absorb
   in ten seconds. This is decision support, not a diagnosis — recommend
   review, never prescribe.

The document follows.
"""

COMPARISON_PROMPT = """\
You are a clinical document intelligence assistant. You are given TWO clinical
documents, labelled DOCUMENT A (earlier) and DOCUMENT B (later). Compare them.

Rules:
1. First verify both documents refer to the same patient (name, ID, DOB). If
   they clearly do not, set same_patient=false and explain — do not compare
   clinical content of different patients.
2. medication_changes: what was added, removed, or dose-changed between A and B.
3. lab_trends: for tests present in both, state whether each improved,
   worsened, or is stable, with the actual values.
4. discrepancies: conflicting information between the documents that staff
   should reconcile (e.g. allergy listed in one but not the other, mismatched
   history).
5. Base every statement on the documents. Never invent values.
6. recommended_action: one concrete next step for the care team.
"""


class ExtractionError(RuntimeError):
    pass


def _client(api_key: str | None = None) -> genai.Client:
    key = api_key or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise ExtractionError(
            "No API key. Set GOOGLE_API_KEY (or paste a key in the sidebar). "
            "Free keys: https://aistudio.google.com/apikey"
        )
    return genai.Client(api_key=key)


def _generate(contents: list, schema, api_key: str | None, model: str | None = None):
    """Call Gemini with retry + model fallback; return (parsed, model_used)."""
    client = _client(api_key)
    models = [model] if model else MODEL_CANDIDATES
    last_error: Exception | None = None

    for candidate in models:
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=candidate,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=schema,
                        temperature=0.1,
                    ),
                )
                parsed = response.parsed
                if parsed is None:  # rare: fall back to manual validation
                    parsed = schema.model_validate_json(response.text)
                return parsed, candidate
            except genai_errors.APIError as exc:
                last_error = exc
                if exc.code == 429:  # rate limited: back off, then retry
                    time.sleep(2 ** (attempt + 1))
                    continue
                break  # other API errors: try the next model
            except Exception as exc:  # noqa: BLE001 - surface anything else once
                last_error = exc
                break

    raise ExtractionError(f"All model attempts failed. Last error: {last_error}")


def extract(document: IngestedDocument, api_key: str | None = None,
            model: str | None = None) -> tuple[ExtractionResult, str]:
    """Run structured extraction on one document. Returns (result, model_used)."""
    contents = [EXTRACTION_PROMPT, *document.parts]
    return _generate(contents, ExtractionResult, api_key, model)


def compare(doc_a: IngestedDocument, doc_b: IngestedDocument,
            api_key: str | None = None, model: str | None = None) -> tuple[ComparisonResult, str]:
    """Compare two documents for the same patient. Returns (result, model_used)."""
    contents = [
        COMPARISON_PROMPT,
        "\n===== DOCUMENT A (earlier) =====\n",
        *doc_a.parts,
        "\n===== DOCUMENT B (later) =====\n",
        *doc_b.parts,
    ]
    return _generate(contents, ComparisonResult, api_key, model)
