"""Generate the binary sample documents (lab report PDF + scanned intake form PNG).

Run from the project root:  python scripts/make_samples.py

All patient data is synthetic — generated for this POC, no real PHI.
"""

import random
from pathlib import Path

from fpdf import FPDF
from PIL import Image, ImageDraw, ImageFilter, ImageFont

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


# ---------------------------------------------------------------------------
# 1. Lab report — digital PDF (same patient as the discharge summary, so the
#    two can be used in the multi-document comparison demo)
# ---------------------------------------------------------------------------

LAB_ROWS = [
    # test, value, unit, reference range, flag
    ("Sodium", "134", "mmol/L", "135 - 145", "L"),
    ("Potassium", "2.9", "mmol/L", "3.5 - 5.1", "L*"),
    ("Chloride", "98", "mmol/L", "98 - 107", ""),
    ("Creatinine", "1.7", "mg/dL", "0.7 - 1.3", "H"),
    ("Urea", "52", "mg/dL", "17 - 43", "H"),
    ("eGFR", "44", "mL/min/1.73m2", "> 60", "L"),
    ("Glucose (Fasting)", "162", "mg/dL", "70 - 100", "H"),
    ("HbA1c", "8.4", "%", "< 5.7", "H"),
    ("Hemoglobin", "11.8", "g/dL", "13.0 - 17.0", "L"),
    ("WBC Count", "7.4", "10^3/uL", "4.0 - 11.0", ""),
    ("Platelet Count", "228", "10^3/uL", "150 - 410", ""),
    ("NT-proBNP", "1850", "pg/mL", "< 300", "H"),
]


def make_lab_report_pdf() -> Path:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, "SUNRISE DIAGNOSTICS LABORATORY", ln=True, align="C")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, "NABL Accredited | 12, MG Road, Pune | Tel: 020-5551-2200", ln=True, align="C")
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 6, "LABORATORY REPORT", ln=True, align="C")
    pdf.ln(2)

    pdf.set_font("Helvetica", "", 9)
    left = [
        "Patient Name : Ramesh Kumar",
        "Age / Sex    : 62 Years / Male",
        "Patient ID   : MRN-483920",
    ]
    right = [
        "Collected  : 18-Aug-2026 08:12",
        "Reported   : 18-Aug-2026 14:05",
        "Referred by: Dr. Anita Deshpande (Cardiology)",
    ]
    for l, r in zip(left, right):
        pdf.cell(95, 5, l)
        pdf.cell(95, 5, r, ln=True)
    pdf.ln(3)

    # Table header
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(230, 236, 245)
    for w, h in ((60, "Test"), (28, "Result"), (30, "Unit"), (42, "Reference Range"), (20, "Flag")):
        pdf.cell(w, 7, h, border=1, fill=True)
    pdf.ln()

    pdf.set_font("Helvetica", "", 9)
    for test, value, unit, ref, flag in LAB_ROWS:
        bold = flag != ""
        pdf.set_font("Helvetica", "B" if bold else "", 9)
        pdf.cell(60, 6.5, test, border=1)
        pdf.cell(28, 6.5, value, border=1)
        pdf.cell(30, 6.5, unit, border=1)
        pdf.cell(42, 6.5, ref, border=1)
        pdf.cell(20, 6.5, flag, border=1, ln=True)

    pdf.ln(3)
    pdf.set_font("Helvetica", "I", 8)
    pdf.multi_cell(0, 4.5,
                   "Flags: H = High, L = Low, L* = Critically low. Critical result "
                   "(Potassium 2.9 mmol/L) telephoned to referring physician at 14:10, "
                   "18-Aug-2026. Kindly correlate clinically.")
    pdf.ln(4)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, "Dr. S. Iyer, MD (Pathology) - Electronically verified", ln=True)

    out = SAMPLES / "lab_report.pdf"
    pdf.output(str(out))
    return out


# ---------------------------------------------------------------------------
# 2. Intake form — rendered to PNG and lightly degraded (rotation + noise) so
#    it behaves like a scanned/photographed paper form and exercises the
#    vision path of the pipeline.
# ---------------------------------------------------------------------------

INTAKE_LINES = [
    ("CITYCARE MULTISPECIALTY HOSPITAL", True),
    ("NEW PATIENT INTAKE FORM", True),
    ("", False),
    ("Date: 22-Aug-2026", False),
    ("", False),
    ("Full Name:  Priya Sharma", False),
    ("Date of Birth:  02-Nov-1991        Age: 34      Sex: Female", False),
    ("Phone:  98xx-xx-4321               City: Pune", False),
    ("", False),
    ("Reason for visit:", True),
    ("  Severe one-sided headaches for last 3 months, 2-3 times", False),
    ("  per week, with nausea and sensitivity to light. Worse", False),
    ("  around periods. Missed 4 work days this month.", False),
    ("", False),
    ("Current medications:", True),
    ("  Ibuprofen 400 mg - as needed for headache (taking almost", False),
    ("  daily for 3 weeks)", False),
    ("  Oral contraceptive pill (combined) - daily", False),
    ("", False),
    ("Allergies:  Sulfa drugs (rash)", False),
    ("", False),
    ("Medical history:", True),
    ("  [x] Migraine (mother also has migraines)", False),
    ("  [ ] Diabetes    [ ] Hypertension    [ ] Asthma", False),
    ("  [x] Anaemia - iron tablets taken last year", False),
    ("", False),
    ("Smoking: No      Alcohol: Occasional", False),
    ("", False),
    ("Patient signature:  P. Sharma", False),
]


def _font(size: int, bold: bool):
    candidates = [
        "/System/Library/Fonts/Supplemental/Courier New Bold.ttf" if bold
        else "/System/Library/Fonts/Supplemental/Courier New.ttf",
        "/System/Library/Fonts/Monaco.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def make_intake_form_png() -> Path:
    W, H = 1240, 1560
    img = Image.new("RGB", (W, H), (250, 248, 243))
    draw = ImageDraw.Draw(img)

    y = 70
    for text, bold in INTAKE_LINES:
        font = _font(30 if bold else 27, bold)
        if text:
            x = 90
            if "HOSPITAL" in text or "INTAKE FORM" in text:
                x = (W - draw.textlength(text, font=font)) // 2
            draw.text((x, y), text, fill=(35, 32, 30), font=font)
        y += 46 if bold else 42

    draw.rectangle([60, 40, W - 60, y + 30], outline=(120, 115, 110), width=3)

    # Scan-like degradation: slight rotation, blur, and speckle noise.
    img = img.rotate(-1.2, expand=True, fillcolor=(235, 233, 228))
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    rng = random.Random(42)
    pixels = img.load()
    for _ in range(4000):
        x, y2 = rng.randrange(img.width), rng.randrange(img.height)
        g = rng.randrange(140, 220)
        pixels[x, y2] = (g, g, g)

    out = SAMPLES / "intake_form.png"
    img.save(out)
    return out


if __name__ == "__main__":
    print("Generated:", make_lab_report_pdf())
    print("Generated:", make_intake_form_png())
