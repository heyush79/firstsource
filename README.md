# Clinical Document Intelligence Hub

AI proof-of-concept for the Firstsource POC stage: ingests unstructured clinical
documents (text, PDF, or scanned image), extracts structured clinical data with
per-section confidence scores, and produces a decision-ready **patient summary
card** with risk flags and a triage recommendation. Includes an optional
**multi-document comparison** mode (e.g. discharge summary vs follow-up labs).

> This is decision
> support, not a medical device — outputs recommend review, never treatment.

## Approach

```
 Input                Ingestion                AI Extraction              Output
┌──────────┐   ┌─────────────────────┐   ┌────────────────────────┐   ┌──────────────────────┐
│ .txt     │   │ digital PDF → text  │   │ Gemini 2.5 Flash        │   │ Patient summary card │
│ .pdf     │ → │   (pypdf, cheap)    │ → │ schema-constrained JSON │ → │ Risk flags + triage  │
│ .png/.jpg│   │ scan/image → vision │   │ (Pydantic response      │   │ Confidence + gaps    │
└──────────┘   └─────────────────────┘   │  schema, temp 0.1)      │   │ JSON export          │
                                         └────────────────────────┘   └──────────────────────┘
```

Key design decisions:

1. **Schema-constrained decoding, not "please return JSON".** The Pydantic
   models in `cdih/schema.py` are passed to Gemini as a `response_schema`, so
   the API guarantees valid, parseable output — no brittle string parsing.
2. **Hybrid PDF ingestion.** Digital PDFs are text-extracted locally (faster,
   cheaper); scanned PDFs and images fall back to Gemini vision, which handles
   OCR implicitly. The UI shows which path was used.
3. **Anti-hallucination rules.** The prompt requires `null` for absent fields,
   evidence-cited rationales for every risk flag, and honest per-section
   confidence scores (lowered for illegible/ambiguous sources). The model also
   reports **missing information** — what the document *should* contain but
   doesn't — because knowing what the AI didn't find builds clinical trust.
4. **Triage as operational output.** Every document is classified
   EMERGENCY / URGENT / ROUTINE / ADMINISTRATIVE with a rationale, suggested
   department, and concrete next steps — turning extraction into routing.
5. **Free-tier resilience.** Retries with backoff on rate limits and falls back
   across models (`gemini-2.5-flash` → `gemini-2.0-flash` → `2.5-flash-lite`).

## Tools used

Python 3.11+ · Streamlit (UI) · Google Gemini API via `google-genai`
(extraction + vision) · Pydantic (output contract) · pypdf (PDF text) ·
fpdf2 + Pillow (sample document generation).

## Setup (clean clone → running in ~3 minutes)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Get a free API key at https://aistudio.google.com/apikey
cp .env.example .env          # then paste your key into .env
# (or: export GOOGLE_API_KEY=...  — or paste the key in the app sidebar)

python selftest.py --quick    # optional: verify the pipeline end-to-end
streamlit run app.py          # opens http://localhost:8501
```

Sample documents live in `samples/` (regenerate the PDF/PNG with
`python scripts/make_samples.py`).

## Example — input and output

**Input:** `samples/lab_report.pdf` — a follow-up lab report for a recently
discharged heart-failure patient, containing a critically low potassium
(2.9 mmol/L), rising creatinine, and HbA1c 8.4%.

**Output (abridged; full JSON downloadable from the app):**

```json
{
  "document_type": "lab_report",
  "patient": {"name": "Ramesh Kumar", "age": "62", "sex": "Male", "patient_id": "MRN-483920"},
  "lab_results": [
    {"test": "Potassium", "value": "2.9", "unit": "mmol/L", "reference_range": "3.5 - 5.1", "flag": "critical"},
    {"test": "Creatinine", "value": "1.7", "unit": "mg/dL", "reference_range": "0.7 - 1.3", "flag": "high"},
    {"test": "HbA1c", "value": "8.4", "unit": "%", "reference_range": "< 5.7", "flag": "high"}
  ],
  "risk_flags": [
    {"flag": "Critically low potassium", "severity": "critical",
     "rationale": "K+ 2.9 mmol/L, below 3.5–5.1 range; lab telephoned the result as critical."}
  ],
  "triage": {
    "category": "URGENT",
    "rationale": "Critical hypokalemia in a heart-failure patient on diuretics requires clinician review within 24h.",
    "suggested_department": "Cardiology",
    "recommended_next_steps": ["Notify treating cardiologist", "Arrange potassium correction and repeat electrolytes"]
  },
  "overall_confidence": 0.95,
  "missing_information": ["No vital signs recorded in this document"]
}
```

The **Compare** tab run on `discharge_summary.txt` (Doc A) vs `lab_report.pdf`
(Doc B) confirms the patient match via MRN, trends the labs against discharge
values, and flags the new critical result for reconciliation.

## Assumptions

- Synthetic data only; no PHI. Production use would require de-identification,
  audit logging, and regulatory review (HIPAA / DPDP).
- Local demo (the brief accepts a screen recording); no auth or persistence.
- One document = one patient; comparison mode verifies identity before comparing.
- ICD-10 codes are surfaced as *hints* only, for coder review — not billing-grade.

## Repository layout

```
app.py                  Streamlit UI (summary card, comparison view)
cdih/schema.py          Pydantic output contract (extraction + comparison)
cdih/ingest.py          File → model-input conversion (text/PDF/image routing)
cdih/extractor.py       Gemini calls, prompts, retry + model fallback
samples/                4 synthetic documents covering all input types
scripts/make_samples.py Regenerates the PDF + scanned-image samples
selftest.py             End-to-end pipeline test (text, PDF, image)
```
