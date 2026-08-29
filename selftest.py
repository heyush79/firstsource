"""End-to-end pipeline self-test (no UI). Requires GOOGLE_API_KEY.

Run:  python selftest.py            # tests text + PDF + image extraction
      python selftest.py --quick    # tests only the text document
"""

import sys
from pathlib import Path

from dotenv import load_dotenv

from cdih import extractor, ingest

load_dotenv()
SAMPLES = Path(__file__).parent / "samples"

CASES = [
    ("discharge_summary.txt", "text ingestion"),
    ("lab_report.pdf", "PDF ingestion"),
    ("intake_form.png", "image/vision ingestion"),
]


def main() -> int:
    quick = "--quick" in sys.argv
    cases = CASES[:1] if quick else CASES
    failures = 0

    for filename, label in cases:
        path = SAMPLES / filename
        print(f"\n=== {label}: {filename} ===")
        try:
            doc = ingest.from_file(path.name, path.read_bytes())
            print(f"ingest mode: {doc.ingest_mode}")
            result, model_used = extractor.extract(doc)
            print(f"model: {model_used}")
            print(f"document_type : {result.document_type.value}")
            print(f"patient       : {result.patient.name} ({result.patient.age}, {result.patient.sex})")
            print(f"diagnoses     : {[d.name for d in result.diagnoses]}")
            print(f"medications   : {len(result.medications)} | labs: {len(result.lab_results)}")
            print(f"risk flags    : {[f'{r.severity.value}:{r.flag}' for r in result.risk_flags]}")
            print(f"triage        : {result.triage.category.value} — {result.triage.rationale[:90]}")
            print(f"confidence    : {result.overall_confidence:.0%}")
            print("PASS")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL: {exc}")

    print(f"\n{'ALL TESTS PASSED' if failures == 0 else f'{failures} test(s) FAILED'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
