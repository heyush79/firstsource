# firstsource

## What this is
- Streamlit proof-of-concept built for the Firstsource POC stage. It reads clinical documents (.txt/.md, PDF, PNG/JPG/WEBP) and produces a structured patient summary card: extracted data, risk flags, a triage category, and per-section confidence. A Compare tab diffs two documents for the same patient.
- `cdih` = Clinical Document Intelligence Hub, the core package (ingestion, Pydantic schema, Gemini calls).
- Stack: Python 3.11+ (CI runs 3.11 and 3.12; ruff targets py311), Streamlit, `google-genai` (Gemini 2.x), Pydantic v2, pypdf, python-dotenv. fpdf2 and Pillow are only used to generate samples. `requirements*.txt` set lower bounds (`>=`) only, with no lock file. All data is synthetic. The tool is decision support, not a medical device.

## How to run it
- Setup: `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements-dev.txt` (runtime + pytest + ruff; the README shows `requirements.txt` only). Takes about 1 to 3 minutes, depending on the pip cache.
- Config: `cp .env.example .env`, then set `GOOGLE_API_KEY` (free key: https://aistudio.google.com/apikey).
- Tests are offline (no key needed). They take about 2 s: `pytest tests/ -v` (the CI command; 11 tests), or bare `pytest`.
- Single test: `pytest tests/test_ingest.py::test_digital_pdf_takes_local_text_path -v`
- Lint (the CI gate, under 1 s): `ruff check .`
- App: `streamlit run app.py` serves http://localhost:8501. To use another port: `streamlit run app.py --server.port 8599 --server.headless true`. The app is up in a few seconds. Without a key it still renders, with the sidebar warning "AI service not configured".
- Headless UI smoke check (no browser, no API call, under 1 s): `python -c "from pathlib import Path; from streamlit.testing.v1 import AppTest; at = AppTest.from_file(str(Path('app.py').resolve())).run(); print(list(at.exception))"`. It should print `[]`. The path must be absolute, because AppTest resolves relative paths against the calling file.
- Live end-to-end check (calls the Gemini API and needs a key): `python selftest.py --quick` runs the text sample only; `python selftest.py` runs text, PDF and image. It exits 1 on any failure. Without a key it fails fast with `FAIL: No API key. Set GOOGLE_API_KEY ...`.
- Regenerate binary samples (about 3 s): `python scripts/make_samples.py`. It overwrites `samples/lab_report.pdf` and `samples/intake_form.png`; see Do NOT.
- Env: `GOOGLE_API_KEY` is the only variable. `cdih/extractor.py::_client` reads it, and `load_dotenv()` in `app.py` and `selftest.py` loads it from `.env`. The placeholder value is in `.env.example`. CI reads it from the `GOOGLE_API_KEY` repo secret.

## Project layout
- `app.py`: Streamlit UI as one module-level script (sidebar, Analyze/Compare tabs, summary-card rendering, JSON export).
- `cdih/ingest.py`: turns a file or pasted text into an `IngestedDocument` (Gemini `parts`, `ingest_mode`, preview text).
- `cdih/extractor.py`: prompts (`EXTRACTION_PROMPT`, `COMPARISON_PROMPT`), Gemini client, retry and model fallback, `extract()` / `compare()`.
- `cdih/schema.py`: Pydantic output contract (`ExtractionResult`, `ComparisonResult`, enums). It is also passed to Gemini as `response_schema`.
- `tests/test_ingest.py`, `tests/test_schema.py`: offline tests for ingestion routing and for schema validation.
- `samples/`: 4 synthetic documents, used by the app's sample picker, the tests and `selftest.py`.
- `scripts/make_samples.py`: regenerates the lab-report PDF and the "scanned" intake-form PNG.
- `selftest.py`: live pipeline check against Gemini (no UI).
- `.github/workflows/ci.yml`: `ruff check .` and `pytest tests/ -v` on 3.11/3.12 for pushes and PRs to main, plus a live smoke test on pushes to main.
- `ruff.toml`, `pytest.ini`: lint config. pytest sets `pythonpath = .` so `from cdih import ...` works under bare `pytest`.

## Architecture in short
1. Input comes from `app.py::pick_document` (sample picker, upload or paste) or from a sample path in `selftest.py`.
2. `cdih/ingest.py::from_file` routes by file extension:
   - text becomes a string part;
   - a PDF becomes pypdf text if it has at least `MIN_CHARS_PER_PAGE` (120) characters per page, otherwise its raw bytes go to Gemini vision;
   - images go to vision as bytes;
   - other types raise `ValueError`.
3. `cdih/extractor.py::extract` / `compare` put the prompt first and call `_generate`. That calls `generate_content` with `response_mime_type="application/json"`, `response_schema=<Pydantic model>` and `temperature=0.1`.
4. `_generate` tries `MODEL_CANDIDATES` in order (`gemini-2.5-flash`, `gemini-2.0-flash`, `gemini-2.5-flash-lite`):
   - on a 429 it sleeps 2, 4 or 8 s and retries (up to 3 attempts per model);
   - any other error moves on to the next model;
   - if every model fails it raises `ExtractionError`.
5. The result is `(ExtractionResult | ComparisonResult, model_used)`. `app.py` keeps it in `st.session_state` and renders it with `render_extraction` / `render_comparison` (HTML cards via `unsafe_allow_html`, `st.table`, a JSON download).

## Conventions
- Ruff (`ruff.toml`):
  - `line-length = 100`; rules `E4,E7,E9,F,I,UP,B,BLE`.
  - `UP042` is ignored on purpose, so enums stay `class X(str, Enum)` rather than `StrEnum`.
  - `BLE001` is ignored only in `cdih/ingest.py`.
  - E501 is not selected, so lines over 100 characters exist and still pass.
- `ruff format` is not used: `ruff format --check .` says 6 of 10 files would be reformatted. Follow the existing hand-wrapped style instead (continuation lines aligned with the open paren).
- Code style: modern type hints (`str | None`, `list[str]`, `tuple[X, str]`), `_`-prefixed private helpers, UPPER_CASE module constants at the top of the file, and module docstrings that explain design decisions.
- Schema: optional fields default to `None`, and lists use `Field(default_factory=list)`. `Field(description=...)` text is sent to Gemini as part of the schema, so treat it as prompt text.
- Errors:
  - Ingestion raises `ValueError`, which the UI shows with `st.error`.
  - The PDF helpers swallow every exception, so a parse failure falls through to the vision path.
  - The extractor wraps all failures in `ExtractionError`, which `app.py` catches.
  - Any other broad `except Exception` needs `# noqa: BLE001` with a reason.
- Logging: the `logging` module isn't used. `selftest.py` and the scripts use `print`; the UI uses `st.error` / `st.warning`.
- Tests: plain pytest functions with no fixtures, no conftest and no mocking. They read real files from `samples/` and use inline bytes for edge cases (a PDF with no text). No test touches the network, and `cdih/extractor.py` has no offline tests.
- Commits: imperative, sentence-case subject with no type prefix (e.g. `Fix CI test collection: put project root on sys.path via pytest.ini`). Add an optional body that explains why, using bullets for multi-part changes, and a `Co-Authored-By:` trailer on AI-assisted commits.

## Do NOT
- Run `ruff format` across the repo, or loosen `ruff.toml` (for example by dropping the `UP042` ignore or adding new ignores) to get lint to pass.
- Edit `samples/*` or run `scripts/make_samples.py` unless asked:
  - Tests assert that `lab_report.pdf` routes as `pdf-text` and contains "Potassium", and they need `intake_form.png`.
  - The Compare demo relies on all three text/PDF samples sharing patient Ramesh Kumar / MRN-483920.
  - Regenerating rewrites the PDF bytes on every run (new `/CreationDate` and `/ID`), even when the content is unchanged.
- Add real patient data or PHI. The samples are synthetic on purpose.
- Commit `.env`, or put a real key in `.env.example` (keep `GOOGLE_API_KEY=your_api_key`).
- Run `selftest.py`, or click Analyze/Compare in the app, as a routine check. Both make live Gemini calls with the user's key. Use `pytest` and the AppTest smoke check instead.
- Push to `main` casually. Every push to main runs the CI `live-smoke-test` job, which calls Gemini with the repo secret.
- Add dependencies without asking. Runtime deps go in `requirements.txt` and dev tools in `requirements-dev.txt`.
- Change a field in `cdih/schema.py` without also checking both prompts in `cdih/extractor.py` (they name fields such as `risk_flags`, `triage` and `field_confidence`) and the renderers in `app.py`.

## Gotchas
- The UI has no API-key input. `app.py` hard-codes `api_key = None` and `model = None`, yet the README and the `ExtractionError` message both say "paste a key in the sidebar". The key has to come from the environment or `.env`.
- `.env` is loaded only by `app.py` and `selftest.py`. Code that imports `cdih.extractor` directly must set `GOOGLE_API_KEY` itself.
- `show_preview` shows an image only if a file with that name exists in `samples/`. Uploaded images show placeholder text.
- Bare `pytest` (as CI runs it) depends on `pythonpath = .` in `pytest.ini` (see commit c586d66).
- Under heavy rate limiting, `_generate` can sleep up to about 42 s (14 s per model times 3 models) before it raises.
- `scripts/make_samples.py` loads macOS fonts from `/System/Library/Fonts/...` and falls back to Pillow's default font on other systems. On macOS the regenerated PNG was byte-identical. With fpdf2 2.9.0 it prints `DeprecationWarning`s for `ln=True`; these are harmless.
- Python versions: the venv installed and the tests passed on 3.12 and on 3.15 on the dev Mac, but CI only covers 3.11 and 3.12.
- Runs create `.pytest_cache/`, `.ruff_cache/` and `__pycache__/`; all of them are ignored.

## Where things are documented
- `README.md`: overview, design decisions, setup, example input/output, assumptions, layout.
- Module docstrings in `cdih/ingest.py` and `cdih/extractor.py` cover the routing strategy and the LLM design choices. Comments in `ruff.toml`, `pytest.ini` and `ci.yml` explain each config choice.
- Live demo: https://clinical-doc-app.streamlit.app (`ci.yml` notes that the Streamlit Cloud deployment runs Python 3.12).

## Current status / next steps
- POC. The most recent work (2026-09-16) added CI and fixed test collection. The code has no TODO/FIXME comments, and `main` is the only remote branch.
