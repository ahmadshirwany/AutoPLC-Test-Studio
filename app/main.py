from __future__ import annotations

from dataclasses import asdict
import logging
from pathlib import Path
import time
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .diagrams import build_mermaid_diagrams
from .docs import write_documents
from .gemini_client import GeminiDocumentationService
from .models import DETAIL_LEVELS
from .parser import parse_codesys_xml
from .prompts import normalize_detail_level
from .purpose import detect_project_purpose
from .storage import create_output_folder


ALLOWED_FORMATS = {"markdown", "html", "docx"}

settings = get_settings()
generator = GeminiDocumentationService(settings)
request_logger = logging.getLogger("app.request")

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
settings.output_root.mkdir(parents=True, exist_ok=True)

app = FastAPI(title=settings.app_name, version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/output", StaticFiles(directory=str(settings.output_root)), name="output")


@app.middleware("http")
async def log_requests(request, call_next):
    request_id = str(uuid4())
    client = request.client.host if request.client else "unknown"
    start_time = time.perf_counter()

    request_logger.info(
        "request_started request_id=%s method=%s path=%s client=%s",
        request_id,
        request.method,
        request.url.path,
        client,
    )

    try:
        response = await call_next(request)
    except Exception:
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        request_logger.exception(
            "request_failed request_id=%s method=%s path=%s duration_ms=%s",
            request_id,
            request.method,
            request.url.path,
            duration_ms,
        )
        raise

    duration_ms = int((time.perf_counter() - start_time) * 1000)
    response.headers["X-Request-ID"] = request_id
    request_logger.info(
        "request_finished request_id=%s method=%s path=%s status=%s duration_ms=%s",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


@app.get("/")
def root() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name}


def _parse_formats(raw_formats: str) -> set[str]:
    parsed = {item.strip().lower() for item in raw_formats.split(",") if item.strip()}
    if not parsed:
        return {"markdown"}

    invalid = parsed - ALLOWED_FORMATS
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid format(s): {', '.join(sorted(invalid))}. Allowed: {', '.join(sorted(ALLOWED_FORMATS))}",
        )

    return parsed


def _parse_bool(raw_value: str | None, default: bool = True) -> bool:
    if raw_value is None:
        return default
    normalized = raw_value.strip().lower()
    if not normalized:
        return default
    return normalized in {"1", "true", "yes", "y", "on"}


def _parse_detail_level(raw_detail_level: str | None) -> str:
    normalized = normalize_detail_level(raw_detail_level)
    if normalized not in DETAIL_LEVELS:
        allowed = ", ".join(sorted(DETAIL_LEVELS.keys()))
        raise HTTPException(status_code=400, detail=f"Invalid detail level. Allowed: {allowed}")
    return normalized


@app.post("/api/generate")
async def generate_documentation(
    file: UploadFile = File(...),
    formats: str = Form("markdown,html,docx"),
    detail_level: str = Form("deep"),
    include_diagrams: str = Form("true"),
) -> dict[str, object]:
    if file.filename and not file.filename.lower().endswith(".xml"):
        raise HTTPException(status_code=400, detail="Only XML files are supported.")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    if len(file_bytes) > settings.upload_max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds upload limit ({settings.upload_max_bytes} bytes).",
        )

    requested_formats = _parse_formats(formats)
    requested_detail_level = _parse_detail_level(detail_level)
    include_diagrams_flag = _parse_bool(include_diagrams, default=True)

    xml_text = file_bytes.decode("utf-8", errors="ignore")
    if not xml_text.strip():
        raise HTTPException(status_code=400, detail="Unable to decode XML content.")

    source_name = file.filename or "uploaded.xml"

    try:
        parsed_project = parse_codesys_xml(xml_text, source_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    purpose = detect_project_purpose(parsed_project)
    output_folder, output_path = create_output_folder(settings.output_root, purpose.slug)
    generated_docs = generator.generate_documents(parsed_project, detail_level=requested_detail_level)

    if include_diagrams_flag:
        generated_docs.diagrams = build_mermaid_diagrams(parsed_project)

    artifacts = write_documents(
        output_path,
        generated_docs,
        requested_formats,
        include_diagrams=include_diagrams_flag,
    )

    detail_config = DETAIL_LEVELS[requested_detail_level]

    return {
        "project_name": parsed_project.project_name,
        "purpose": asdict(purpose),
        "output_folder": output_folder,
        "detail_level": requested_detail_level,
        "generation_config": {
            "overview_max_nodes": detail_config.overview_max_nodes,
            "detailed_max_nodes": detail_config.detailed_max_nodes,
            "min_words_overview": detail_config.min_words_overview,
            "min_words_detailed": detail_config.min_words_detailed,
            "include_diagrams": include_diagrams_flag,
        },
        "stats": parsed_project.stats,
        "artifacts": [asdict(item) for item in artifacts],
        "warnings": generated_docs.warnings,
    }
