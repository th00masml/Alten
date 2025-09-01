PDF Form Data Extraction – AXA XL

Overview
- Goal: Extract key data from filled AXA XL insurance PDF forms and present results in a structured format with confidence scores, a simple review workflow, and storage.
- Tech stack: Python 3.9+, optional third‑party libs for PDF/OCR, Streamlit UI, SQLite storage.

Quick Start
- Windows
  1) Create venv and install base deps
     python -m venv .venv
     .venv\Scripts\activate
     pip install -r requirements.txt
  2) Recommended: better text extraction (layout-aware)
     pip install pdfplumber==0.11.5
     # or all optional extras (including OCR support)
     pip install -r requirements-optional.txt
  3) Run UI
    python -m streamlit run app_streamlit.py --server.address 127.0.0.1 --server.port 8502
     # Open http://127.0.0.1:8501
  4) Batch process folder from repo root
     set PYTHONPATH=%CD%
     python scripts\cli.py --input . --out-db data\extractions.db --config config\forms\axa_xl_claim.json
  5) Summarize DB results
     set PYTHONPATH=%CD%
     python scripts\db_summary.py

- macOS/Linux
  1) Create venv and install base deps
     python3 -m venv .venv
     source .venv/bin/activate
     pip install -r requirements.txt
  2) Recommended: better text extraction (layout-aware)
     pip install pdfplumber==0.11.5
     # or all optional extras (including OCR support)
     pip install -r requirements-optional.txt
  3) Run UI
     python -m streamlit run app_streamlit.py --server.address 127.0.0.1 --server.port 8501
     # Open http://127.0.0.1:8501
  4) Batch process folder from repo root
     export PYTHONPATH="$PWD"
     python scripts/cli.py --input . --out-db data/extractions.db --config config/forms/axa_xl_claim.json
  5) Summarize DB results
     export PYTHONPATH="$PWD"
     python scripts/db_summary.py

Features
- Dual extraction path:
  - Text-native PDFs: Parse text with PyPDF2 and regex-based field extraction.
  - Layout-aware text: If `pdfplumber` is installed, use it for improved text layout and higher hit rates; otherwise fall back to PyPDF2.
  - OCR fallback: If optional dependencies are installed (pytesseract + a PDF renderer), run OCR and parse the recognized text. If OCR dependencies are missing, the pipeline skips OCR and surfaces a low-confidence result.
- Confidence scoring per field with aggregation.
- Review/correction in the Streamlit UI and persistence to SQLite.
- Configurable field patterns via JSON configs to support new form variants. Selected config is merged with built-in defaults to broaden coverage.
 - Form selector in the UI to choose among multiple AXA XL variants (claim, policy, customer info), driven by configs in `config/forms/`.

Project Structure
- src/axa_extractor/fields.py: Field schema and confidence utilities.
- src/axa_extractor/extractors/base.py: Base extractor interface.
- src/axa_extractor/extractors/text_pdf.py: Text extraction and regex parsing for digital PDFs.
- src/axa_extractor/extractors/ocr_pdf.py: Optional OCR-based extractor (graceful if deps missing).
- src/axa_extractor/pipeline.py: Orchestration, merging results, confidence weighting.
- src/axa_extractor/storage.py: SQLite schema and DAO methods.
- config/forms/axa_xl_claim.json: Regex configuration for AXA XL claim forms.
- config/forms/axa_xl_policy.json: Regex configuration for AXA XL policy/schedule documents.
- config/forms/axa_xl_customer_info.json: Regex configuration for AXA XL customer information forms.
- app_streamlit.py: Streamlit app for upload, review, and save.
- scripts/cli.py: CLI to process files/folders in batch.
- tests/: Basic unit tests using unittest.

Setup
1) Create a virtual environment and install base deps:
   - Windows:
     python -m venv .venv
     .venv\\Scripts\\activate
     pip install -r requirements.txt
   - macOS/Linux:
     python -m venv .venv
     source .venv/bin/activate
     pip install -r requirements.txt

2) Recommended: better text extraction
   - Install optional extras for layout-aware extraction:
     pip install pdfplumber==0.11.5
   - Or install all optional parsing/OCR extras:
     pip install -r requirements-optional.txt

2) Optional OCR extras (for scanned PDFs):
   - Install Tesseract OCR (system binary) and ensure it’s in PATH.
   - Install Python packages: pytesseract, pillow, and one of: pymupdf (preferred), pdf2image + poppler.
   - See requirements-optional.txt for extras.

Run
- Streamlit UI:
  - Windows/macOS/Linux (works even if `streamlit` is not on PATH):
    python -m streamlit run app_streamlit.py --server.address 127.0.0.1 --server.port 8501
  - Then open: http://127.0.0.1:8501
  - In the sidebar Form Variant selector, pick:
    - Auto (recommended): the app tries all configs in `config/forms/`, scores each by confidence and filled fields, and applies a filename-based tie-breaker (e.g., files with “policy” prefer the Policy config). The Summary panel shows the chosen config, reasons, and top alternatives.
    - A specific config (Claim/Policy/Customer Info): manual override for known form type.

- CLI batch processing:
  python scripts/cli.py --input "path/to/folder" --out-db data/extractions.db

Configuration
- Add or edit JSON configs in `config/forms/` to define new field patterns without changing code.
- In the Streamlit sidebar, pick the form variant (claim, policy, or customer info). The selected JSON is merged with defaults to broaden coverage.
- CLI: pass `--config` with the desired JSON, e.g. `--config config/forms/axa_xl_policy.json`.

Confidence and Review
- Each extracted field has a confidence (0.0–1.0). Regex hits with consistent formats score higher; ambiguous or multi-match hits score lower. OCR path applies a penalty due to recognition uncertainty.
- The UI highlights low-confidence fields for review; users can correct values before saving. Corrections are stored with metadata to enable future rule improvements.

Batch Processing
- Windows:
  - Ensure the repo root is on the Python path for imports:
    set PYTHONPATH=%CD%
  - Process a folder recursively (recommended to start from repo root):
    python scripts\cli.py --input . --out-db data\extractions.db --auto-config
  - macOS/Linux:
  export PYTHONPATH="$PWD"
  python scripts/cli.py --input . --out-db data/extractions.db --auto-config

Tip: If your input path contains spaces, prefer `--input .` to scan recursively from the current directory or wrap the path in quotes.

Database
- SQLite path: `data/extractions.db`
- Tables: `documents` (per-file) and `fields` (per-field with value, confidence, source)
- Quick summary report:
  - Windows:  set PYTHONPATH=%CD% && python scripts\db_summary.py
  - macOS/Linux: export PYTHONPATH="$PWD" && python scripts/db_summary.py

Performance Considerations
- Fast path for text-native PDFs (no rendering).
- Batched processing in CLI; potential for multiprocessing in future.
- Config-driven patterns reduce code changes as forms evolve.

Security Notes
- Avoid logging sensitive PII. Local SQLite storage by default; for production, consider encrypted storage, secrets management, and access controls. Ensure files are processed in a secure environment and scrub temporary artifacts.

Testing
- Unit tests for parsing and storage using Python’s unittest (no external deps required). Add golden-text fixtures to simulate extracted text from PDFs.

Requirements
- Base: see `requirements.txt` (Streamlit UI and PyPDF2 for text extraction).
- Optional parsing/OCR:
  - `pdfplumber` for improved text extraction/layout on text PDFs.
  - `pytesseract`, `pillow` and a PDF renderer like `pymupdf` or `pdf2image` for scanned PDFs.
  - If using `pdf2image`, install Poppler; for OCR, install the Tesseract system binary and ensure it’s on PATH.

Development
- Install dev tools:
  pip install -r requirements-dev.txt
- Run tests (unittest or pytest):
  python -m unittest discover -s tests
  # or
  pytest -q
- Format and lint:
  black . && isort . && flake8
- Type check (optional):
  mypy src

Troubleshooting
- `streamlit` not recognized: use `python -m streamlit run app_streamlit.py`.
- `ModuleNotFoundError: No module named 'src'`: set PYTHONPATH to repo root before running CLI/scripts.
- Paths with spaces on Windows: wrap paths in quotes or use `--input .` to scan recursively from the current directory.
- Unsure which form variant to choose: use Auto (recommended). The app/CLI tries all configs, applies filename-based tie-breakers (e.g., “fnol”, “policy”, “customer”), and shows which one scored best for each document with reasons.

Security Notes
- Avoid logging sensitive PII. Local SQLite storage by default; for production, consider encrypted storage, secrets management, and access controls. Ensure files are processed in a secure environment and scrub temporary artifacts.

Roadmap / Improvements
- Learn from corrections: persist corrected patterns and build a feedback loop (e.g., track false positives/negatives and propose rule updates).
- Add layout-aware parsing (PDF coordinate-based anchors) with pdfplumber/pymupdf for higher accuracy.
- Add model-based key-value extraction and handwriting OCR for notes sections.
- Add asynchronous workers and a job queue for large-scale processing.
