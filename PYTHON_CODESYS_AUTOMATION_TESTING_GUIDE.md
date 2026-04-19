# Python Automation Testing Guide for CODESYS XML Projects

## 1. Goal

Use Python scripts to automate documentation generation tests for this project from CODESYS XML exports.

This guide covers:
- Building Python scripts that call the API.
- Running batch regression checks across multiple XML files.
- Validating output artifacts and warnings.
- Mapping CODESYS export workflow into repeatable automated tests.

## 2. Scope and Connection Model

This project integrates with CODESYS through exported XML files.

Supported flow:
1. Export project XML from CODESYS.
2. Submit XML to this API.
3. Validate generated docs and metadata with Python tests.

Not in scope for this guide:
- Live PLC runtime communication.
- Direct protocol drivers (OPC UA, Modbus, ADS, and similar).

## 3. Prerequisites

- Windows with PowerShell.
- Python 3.8+.
- Local clone of this repository.
- CODESYS project XML export file.

Install dependencies:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create local env file:

```powershell
Copy-Item .env.example .env
```

Start API server (default port 8000):

```powershell
py -3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-config uvicorn-log-config.json
```

Health check:

```powershell
curl.exe -s http://127.0.0.1:8000/api/health
```

## 4. API Contract for Automation

Endpoint:
- `POST /api/generate`

Request type:
- `multipart/form-data`

Form fields:
- `file` (required): XML file, must end with `.xml`.
- `formats` (optional): comma-separated from `markdown,html,docx`.
- `detail_level` (optional): `basic`, `standard`, `deep`, `comprehensive`.
- `include_diagrams` (optional): string bool (`true`, `false`, `1`, `0`, `yes`, `no`).

Response (high-level keys):
- `project_name`
- `purpose`
- `output_folder`
- `detail_level`
- `generation_config`
- `stats`
- `artifacts`
- `warnings`

## 5. Single File Automation Script

Create `scripts/run_generate_once.py`:

```python
from pathlib import Path
import requests

BASE_URL = "http://127.0.0.1:8000"
XML_PATH = Path("tests/fixtures/sample_codesys.xml")
TIMEOUT_SECONDS = 180


def main() -> None:
    if not XML_PATH.exists():
        raise FileNotFoundError(f"Missing XML file: {XML_PATH}")

    with XML_PATH.open("rb") as stream:
        files = {
            "file": (XML_PATH.name, stream, "text/xml"),
        }
        data = {
            "formats": "markdown,html,docx",
            "detail_level": "deep",
            "include_diagrams": "true",
        }

        response = requests.post(
            f"{BASE_URL}/api/generate",
            files=files,
            data=data,
            timeout=TIMEOUT_SECONDS,
        )

    response.raise_for_status()
    payload = response.json()

    required_keys = {
        "project_name",
        "purpose",
        "output_folder",
        "detail_level",
        "generation_config",
        "stats",
        "artifacts",
        "warnings",
    }
    missing = required_keys.difference(payload.keys())
    if missing:
        raise RuntimeError(f"Missing response keys: {sorted(missing)}")

    print(f"PROJECT={payload['project_name']}")
    print(f"FOLDER={payload['output_folder']}")
    print(f"DETAIL_LEVEL={payload['detail_level']}")
    print(f"WARNINGS={len(payload['warnings'])}")

    for artifact in payload["artifacts"]:
        print(
            f"ARTIFACT kind={artifact['kind']} format={artifact['format']} path={artifact['relative_path']}"
        )


if __name__ == "__main__":
    main()
```

Run:

```powershell
py -3 scripts/run_generate_once.py
```

## 6. Batch XML Regression Script

Create `scripts/run_batch_generate.py`:

```python
from pathlib import Path
import time
from typing import Any
import requests

BASE_URL = "http://127.0.0.1:8000"
INPUT_DIR = Path("sample")
MAX_ATTEMPTS = 3
REQUEST_TIMEOUT_SECONDS = 180
RETRY_SLEEP_SECONDS = 2


def submit_xml(xml_path: Path) -> dict[str, Any]:
    last_error: Exception | None = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with xml_path.open("rb") as stream:
                files = {
                    "file": (xml_path.name, stream, "text/xml"),
                }
                data = {
                    "formats": "markdown,docx",
                    "detail_level": "standard",
                    "include_diagrams": "false",
                }
                response = requests.post(
                    f"{BASE_URL}/api/generate",
                    files=files,
                    data=data,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )

            if response.status_code == 413:
                return {
                    "file": str(xml_path),
                    "ok": False,
                    "status": 413,
                    "error": "File too large for UPLOAD_MAX_BYTES",
                }

            if response.status_code >= 500:
                raise RuntimeError(f"Server error {response.status_code}: {response.text}")

            if response.status_code >= 400:
                return {
                    "file": str(xml_path),
                    "ok": False,
                    "status": response.status_code,
                    "error": response.text,
                }

            payload = response.json()
            return {
                "file": str(xml_path),
                "ok": True,
                "status": 200,
                "output_folder": payload.get("output_folder", ""),
                "warning_count": len(payload.get("warnings", [])),
                "artifact_count": len(payload.get("artifacts", [])),
            }
        except Exception as exc:
            last_error = exc
            if attempt < MAX_ATTEMPTS:
                time.sleep(RETRY_SLEEP_SECONDS)

    return {
        "file": str(xml_path),
        "ok": False,
        "status": 0,
        "error": str(last_error) if last_error else "unknown error",
    }


def main() -> None:
    if not INPUT_DIR.exists():
        raise FileNotFoundError(f"Missing input directory: {INPUT_DIR}")

    xml_files = sorted(INPUT_DIR.glob("*.xml"))
    if not xml_files:
        raise RuntimeError(f"No XML files found in: {INPUT_DIR}")

    total = len(xml_files)
    successes = 0

    print(f"Found {total} XML files")

    for xml_path in xml_files:
        result = submit_xml(xml_path)
        if result["ok"]:
            successes += 1
            print(
                f"OK file={result['file']} output_folder={result['output_folder']} artifacts={result['artifact_count']} warnings={result['warning_count']}"
            )
        else:
            print(f"FAIL file={result['file']} status={result['status']} error={result['error']}")

    print(f"DONE success={successes}/{total} failed={total - successes}")


if __name__ == "__main__":
    main()
```

Run:

```powershell
py -3 scripts/run_batch_generate.py
```

## 7. Pytest Integration Pattern

You can add API smoke tests that run against a live local server.

Create `tests/test_api_generate_smoke.py`:

```python
from pathlib import Path
import requests

BASE_URL = "http://127.0.0.1:8000"


def test_generate_smoke() -> None:
    xml_path = Path("tests/fixtures/sample_codesys.xml")

    with xml_path.open("rb") as stream:
        files = {
            "file": (xml_path.name, stream, "text/xml"),
        }
        data = {
            "formats": "markdown",
            "detail_level": "standard",
            "include_diagrams": "false",
        }

        response = requests.post(
            f"{BASE_URL}/api/generate",
            files=files,
            data=data,
            timeout=180,
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["project_name"]
    assert payload["output_folder"]
    assert isinstance(payload["artifacts"], list)
    assert isinstance(payload["warnings"], list)
```

Run tests:

```powershell
pytest
```

## 8. CODESYS Export Workflow Mapping

Suggested team workflow:
1. Engineer updates logic in CODESYS.
2. Export XML snapshot from CODESYS project.
3. Commit XML snapshots into a controlled folder for regression runs.
4. Execute batch Python script.
5. Archive generated outputs under `output/<purpose>-<timestamp>/`.
6. Review warnings and artifact completeness during code review.

Recommended XML choices for this repo:
- `tests/fixtures/sample_codesys.xml` for deterministic unit and smoke runs.
- `sample/Untitled1.xml` for broader real-world validation.

## 9. Environment Variables That Affect Automation

From configuration:
- `GEMINI_API_KEY`: if missing, deterministic fallback docs are generated.
- `GEMINI_MODEL`: default `gemini-1.5-flash`.
- `GEMINI_TIMEOUT_SECONDS`: base timeout used by generation service.
- `UPLOAD_MAX_BYTES`: default `10485760` (10 MB).
- `OUTPUT_ROOT`: default output root directory (`output`).

## 10. Troubleshooting

- 400 Bad Request:
  - Check XML is valid and file extension is `.xml`.
  - Check `formats` contains only supported values.

- 413 Payload Too Large:
  - Reduce XML size or increase `UPLOAD_MAX_BYTES`.

- 5xx errors or timeouts:
  - Retry with backoff.
  - Lower `detail_level` from `comprehensive` or `deep` to `standard`.
  - Increase `GEMINI_TIMEOUT_SECONDS` if your environment is slow.

- Unexpected fallback content:
  - Verify `GEMINI_API_KEY` in `.env`.
  - Confirm outbound network access for Gemini API.

- Missing diagram sections:
  - Ensure `include_diagrams=true`.
  - For very large graphs, diagram simplification safeguards may reduce rendered complexity.

## 11. Optional Improvements

- Add JSON result archiving for each run to track regressions over time.
- Add CI pipeline job that runs batch generation daily on curated XML fixtures.
- Add policy checks that fail CI if warning counts exceed a threshold.
