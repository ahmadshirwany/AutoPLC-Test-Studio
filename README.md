# CODESYS XML Documentation Agent (MVP)

This project is a standalone web MVP that:

1. Accepts a CODESYS XML upload in the browser.
2. Parses structure and logic blocks from XML.
3. Uses Gemini to generate documentation (or a deterministic fallback if Gemini is unavailable).
4. Supports depth-aware generation profiles (`basic`, `standard`, `deep`, `comprehensive`).
5. Generates Mermaid system flow and logic flow diagrams from parsed structure.
6. Saves outputs in purpose-based timestamped folders.
7. Exports Markdown, HTML, and DOCX artifacts.

## Quick Start

1. Create and activate a Python environment.
2. Install dependencies.
3. Configure environment variables.
4. Start the API server.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload --port 8000
```

Open http://127.0.0.1:8000 in a browser.

## Environment Variables

- `GEMINI_API_KEY`: API key for Gemini. If missing, fallback templates are used.
- `GEMINI_MODEL`: Model name (default: `gemini-1.5-flash`).
- `GEMINI_TIMEOUT_SECONDS`: Request timeout for Gemini API.
- `UPLOAD_MAX_BYTES`: Maximum XML upload size in bytes.
- `OUTPUT_ROOT`: Root directory for generated documentation.

## API Endpoints

- `GET /` -> Upload UI.
- `GET /api/health` -> Health status.
- `POST /api/generate` -> Generates docs from XML upload.

Request body (`multipart/form-data`):
- `file`: XML file.
- `formats`: Comma-separated formats (`markdown,html,docx`).
- `detail_level`: Documentation depth (`basic`, `standard`, `deep`, `comprehensive`). Default is `deep`.
- `include_diagrams`: Whether to inject flow and logic diagrams into generated docs (`true`/`false`). Default is `true`.

Sample request:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/generate" `
	-F "file=@tests/fixtures/sample_codesys.xml;type=text/xml" `
	-F "formats=markdown,html,docx" `
	-F "detail_level=deep" `
	-F "include_diagrams=true"
```

## Automation & Testing Guide

For a complete workflow to create Python automation scripts, process exported CODESYS XML files, and run regression checks against this API, see:

- [PYTHON_CODESYS_AUTOMATION_TESTING_GUIDE.md](PYTHON_CODESYS_AUTOMATION_TESTING_GUIDE.md)

## Tests

```powershell
pytest
```
