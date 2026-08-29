"""Clinical Document Intelligence Hub — Streamlit UI.

Run:  streamlit run app.py
Needs GOOGLE_API_KEY in the environment / .env, or pasted in the sidebar.
"""

import json
import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from cdih import extractor, ingest
from cdih.schema import ComparisonResult, ExtractionResult

load_dotenv()

SAMPLES_DIR = Path(__file__).parent / "samples"
SAMPLE_FILES = {
    "Discharge summary (text)": "discharge_summary.txt",
    "Lab report (PDF)": "lab_report.pdf",
    "Physician progress note (text)": "physician_note.txt",
    "Scanned intake form (image)": "intake_form.png",
}

TRIAGE_STYLE = {
    "EMERGENCY": ("#c62828", "🚨"),
    "URGENT": ("#e65100", "⚠️"),
    "ROUTINE": ("#2e7d32", "✅"),
    "ADMINISTRATIVE": ("#546e7a", "🗂️"),
}
SEVERITY_COLOR = {"low": "#78909c", "moderate": "#f9a825", "high": "#e65100", "critical": "#c62828"}
LAB_FLAG_COLOR = {"normal": "#2e7d32", "low": "#e65100", "high": "#e65100", "critical": "#c62828"}

st.set_page_config(page_title="Clinical Document Intelligence Hub", page_icon="🩺", layout="wide")

st.markdown("""
<style>
.badge {display:inline-block; padding:4px 14px; border-radius:14px; color:white;
        font-weight:600; font-size:0.95rem; margin-right:6px;}
.chip  {display:inline-block; padding:3px 10px; border-radius:12px; color:white;
        font-size:0.8rem; margin:2px 4px 2px 0;}
.card  {border:1px solid rgba(128,128,128,0.35); border-radius:10px;
        padding:16px 20px; margin-bottom:12px;}
.small-muted {opacity:0.65; font-size:0.85rem;}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Sidebar — configuration
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("🩺 Clinical Document Intelligence Hub")
    st.caption("Turn patient documents into clear, actionable summaries — "
               "in seconds, not hours.")

    # Configuration is deliberately hidden from end users: the service key is
    # read from the environment / .env by the extraction layer.
    api_key = None
    model = None

    if os.environ.get("GOOGLE_API_KEY"):
        st.markdown("<span style='color:#2e7d32'>●</span> AI service connected",
                    unsafe_allow_html=True)
    else:
        st.warning("AI service not configured. Please contact your administrator.")

    st.divider()
    st.markdown(
        "**How it works**\n\n"
        "1. 📄 Add a patient document\n"
        "2. 🤖 The assistant reads and organises it\n"
        "3. ✅ Review the summary, alerts and suggested next step\n")

    st.markdown(
        "**Works with**\n\n"
        "Discharge summaries · lab reports · physician notes · intake forms — "
        "as typed text, PDF, or a scanned/photographed page.")

    st.divider()
    st.markdown(
        "<span class='small-muted'>All sample data is synthetic. "
        "This tool supports clinical review — it does not replace it. "
        "Not a medical device.</span>",
        unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Input helpers
# ---------------------------------------------------------------------------
def pick_document(key_prefix: str) -> ingest.IngestedDocument | None:
    """Render an input picker (sample / upload / paste) and return the doc."""
    source = st.radio("Document source", ["Sample document", "Upload file", "Paste text"],
                      horizontal=True, key=f"{key_prefix}_source")
    try:
        if source == "Sample document":
            label = st.selectbox("Choose a sample", list(SAMPLE_FILES), key=f"{key_prefix}_sample")
            path = SAMPLES_DIR / SAMPLE_FILES[label]
            return ingest.from_file(path.name, path.read_bytes())
        if source == "Upload file":
            up = st.file_uploader("Upload .txt, .pdf, .png, .jpg", key=f"{key_prefix}_upload",
                                  type=["txt", "md", "pdf", "png", "jpg", "jpeg", "webp"])
            if up is not None:
                return ingest.from_file(up.name, up.getvalue())
            return None
        text = st.text_area("Paste clinical document text", height=220, key=f"{key_prefix}_paste")
        return ingest.from_text(text) if text.strip() else None
    except ValueError as exc:
        st.error(str(exc))
        return None


INGEST_MODE_LABEL = {
    "text": "typed text",
    "pdf-text": "digital PDF",
    "pdf-vision": "scanned PDF (read visually)",
    "image-vision": "scanned image (read visually)",
}


def show_preview(doc: ingest.IngestedDocument):
    mode = INGEST_MODE_LABEL.get(doc.ingest_mode, doc.ingest_mode)
    with st.expander(f"📄 Document preview — {doc.source_name}  ·  {mode}"):
        if doc.ingest_mode == "image-vision":
            path = SAMPLES_DIR / doc.source_name
            if path.exists():
                st.image(str(path), width=420)
            else:
                st.write(doc.preview_text)
        else:
            st.text(doc.preview_text)


# ---------------------------------------------------------------------------
# Result rendering — the "patient summary card"
# ---------------------------------------------------------------------------
def render_extraction(result: ExtractionResult, model_used: str):
    color, icon = TRIAGE_STYLE.get(result.triage.category.value, ("#546e7a", ""))

    # Header row: patient identity + triage badge
    left, right = st.columns([3, 2])
    with left:
        p = result.patient
        st.subheader(p.name or "Unknown patient")
        bits = [b for b in (
            f"{p.age} yrs" if p.age else None, p.sex,
            f"DOB {p.date_of_birth}" if p.date_of_birth else None,
            f"ID {p.patient_id}" if p.patient_id else None) if b]
        st.markdown(" · ".join(bits) if bits else "_No identifiers found_")
        st.markdown(f"**Document:** {result.document_type.value.replace('_', ' ').title()}"
                    + (f" · {result.document_date}" if result.document_date else ""))
    with right:
        st.markdown(
            f"<div style='text-align:right'>"
            f"<span class='badge' style='background:{color}'>{icon} {result.triage.category.value}</span>"
            f"<div class='small-muted' style='margin-top:6px'>"
            f"Extraction confidence: {result.overall_confidence:.0%}</div></div>",
            unsafe_allow_html=True)

    # Clinical summary
    st.markdown(f"<div class='card'><b>🧾 Clinical summary</b><br>{result.clinical_summary}</div>",
                unsafe_allow_html=True)

    # Risk flags
    if result.risk_flags:
        st.markdown("**🚩 Risk flags**")
        for rf in result.risk_flags:
            c = SEVERITY_COLOR.get(rf.severity.value, "#78909c")
            st.markdown(
                f"<div class='card' style='border-left:6px solid {c}; padding:10px 16px'>"
                f"<span class='chip' style='background:{c}'>{rf.severity.value.upper()}</span> "
                f"<b>{rf.flag}</b><br><span class='small-muted'>{rf.rationale}</span></div>",
                unsafe_allow_html=True)

    # Triage recommendation
    st.markdown(
        f"<div class='card' style='border-left:6px solid {color}'>"
        f"<b>🧭 Recommended handling — {result.triage.category.value}</b><br>"
        f"{result.triage.rationale}"
        + (f"<br><b>Suggested department:</b> {result.triage.suggested_department}"
           if result.triage.suggested_department else "") + "</div>",
        unsafe_allow_html=True)
    if result.triage.recommended_next_steps:
        st.markdown("**Next steps**")
        for i, step in enumerate(result.triage.recommended_next_steps, 1):
            st.markdown(f"{i}. {step}")

    # Structured detail columns
    c1, c2 = st.columns(2)
    with c1:
        if result.diagnoses:
            st.markdown("**🩺 Diagnoses**")
            st.table([{"Diagnosis": d.name, "Status": d.status or "—",
                       "ICD-10 (hint)": d.icd10_hint or "—"} for d in result.diagnoses])
        if result.medications:
            st.markdown("**💊 Medications**")
            st.table([{"Medication": m.name, "Dose": m.dose or "—",
                       "Frequency": m.frequency or "—", "Route": m.route or "—"}
                      for m in result.medications])
        if result.allergies:
            st.markdown("**⚠️ Allergies:** " + ", ".join(result.allergies))
    with c2:
        if result.lab_results:
            st.markdown("**🧪 Lab results**")
            st.table([{"Test": l.test, "Value": f"{l.value} {l.unit or ''}".strip(),
                       "Reference": l.reference_range or "—", "Flag": l.flag.value}
                      for l in result.lab_results])
        if result.vitals:
            st.markdown("**❤️ Vitals**")
            st.table([{"Vital": v.name, "Value": f"{v.value} {v.unit or ''}".strip()}
                      for v in result.vitals])
        if result.key_findings:
            st.markdown("**🔍 Key findings**")
            for kf in result.key_findings:
                st.markdown(f"- {kf}")

    # Confidence + gaps
    c3, c4 = st.columns(2)
    with c3:
        if result.field_confidence:
            st.markdown("**📊 Extraction confidence by section**")
            for fc in result.field_confidence:
                st.progress(min(max(fc.confidence, 0.0), 1.0),
                            text=f"{fc.field}: {fc.confidence:.0%}"
                                 + (f" — {fc.note}" if fc.note else ""))
    with c4:
        if result.missing_information:
            st.markdown("**❓ Missing information**")
            for m in result.missing_information:
                st.markdown(f"- {m}")

    # Structured record for downstream systems (EHR / billing integration)
    with st.expander("📋 Structured record (for system integration)"):
        st.json(json.loads(result.model_dump_json()))
    st.download_button("⬇️ Export patient record",
                       data=result.model_dump_json(indent=2),
                       file_name="patient_record.json", mime="application/json")


def render_comparison(result: ComparisonResult, model_used: str):
    if not result.same_patient:
        st.error(f"⛔ Patient mismatch: {result.patient_match_note}")
        return
    st.success(f"✅ Same patient confirmed — {result.patient_match_note}")
    st.markdown(f"<div class='card'><b>🧾 Comparison summary</b><br>{result.summary}</div>",
                unsafe_allow_html=True)
    st.markdown(f"<div class='card' style='border-left:6px solid #e65100'>"
                f"<b>🧭 Recommended action</b><br>{result.recommended_action}</div>",
                unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        if result.medication_changes:
            st.markdown("**💊 Medication changes**")
            st.table([{"Medication": m.medication, "Change": m.change.value,
                       "Detail": m.detail or "—"} for m in result.medication_changes])
        if result.diagnosis_changes:
            st.markdown("**🩺 Diagnosis changes**")
            for d in result.diagnosis_changes:
                st.markdown(f"- {d}")
    with c2:
        if result.lab_trends:
            st.markdown("**🧪 Lab trends**")
            st.table([{"Test": t.test, "Trend": t.trend, "Detail": t.detail}
                      for t in result.lab_trends])
        if result.discrepancies:
            st.markdown("**⚠️ Discrepancies to reconcile**")
            for d in result.discrepancies:
                st.markdown(f"- {d}")

    with st.expander("📋 Structured record (for system integration)"):
        st.json(json.loads(result.model_dump_json()))


# ---------------------------------------------------------------------------
# Main layout
# ---------------------------------------------------------------------------
tab_analyze, tab_compare = st.tabs(["📄 Analyze a document", "🔀 Compare two documents"])

with tab_analyze:
    doc = pick_document("analyze")
    if doc:
        show_preview(doc)
    if st.button("🔎 Analyze document", type="primary", disabled=doc is None):
        with st.spinner("Reading document and extracting structured intelligence…"):
            try:
                result, used = extractor.extract(doc, api_key=api_key or None, model=model)
                st.session_state["analyze_result"] = (result, used)
            except extractor.ExtractionError as exc:
                st.error(str(exc))
    if "analyze_result" in st.session_state:
        render_extraction(*st.session_state["analyze_result"])

with tab_compare:
    st.caption("Compare an earlier and a later document for the same patient — "
               "e.g. the discharge summary vs the follow-up lab report.")
    ca, cb = st.columns(2)
    with ca:
        st.markdown("**Document A (earlier)**")
        doc_a = pick_document("cmp_a")
        if doc_a:
            show_preview(doc_a)
    with cb:
        st.markdown("**Document B (later)**")
        doc_b = pick_document("cmp_b")
        if doc_b:
            show_preview(doc_b)
    if st.button("🔀 Compare documents", type="primary",
                 disabled=doc_a is None or doc_b is None):
        with st.spinner("Comparing documents…"):
            try:
                result, used = extractor.compare(doc_a, doc_b, api_key=api_key or None, model=model)
                st.session_state["compare_result"] = (result, used)
            except extractor.ExtractionError as exc:
                st.error(str(exc))
    if "compare_result" in st.session_state:
        render_comparison(*st.session_state["compare_result"])
