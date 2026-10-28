from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from app.services.cross_paper_analyzer import compare_papers
from app.services.pdf_parser import extract_pdf_content
from app.services.paper_analyzer import analyze_paper
from app.services.paper_repository import get_paper, save_paper
from app.services.research_gap_engine import detect_research_gaps
import json
import logging
import os
from uuid import uuid4
from dotenv import load_dotenv
load_dotenv()

_api_logger = logging.getLogger("app.api")
MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024
UPLOAD_CHUNK_SIZE_BYTES = 1024 * 1024
UPLOAD_TOO_LARGE_DETAIL = "PDF files must be 50 MiB or smaller."

app = FastAPI(
    title="Academic Literature Intelligence Platform",
    version="1.0.0"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv(
        "FRONTEND_ORIGIN",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class PaperMetadata(BaseModel):
    title: str | None = Field(default=None)
    authors: list[str] = Field(default_factory=list)
    year: int | None = Field(default=None)
    doi: str | None = Field(default=None)
    keywords: list[str] = Field(default_factory=list)


class PaperUploadResponse(BaseModel):
    paper_id: str
    filename: str
    metadata: PaperMetadata
    sections: dict[str, str] = Field(default_factory=dict)
    analysis: dict[str, object] = Field(default_factory=dict)


class PaperComparisonRequest(BaseModel):
    paper_ids: list[str] = Field(min_length=2, max_length=10)

    @field_validator("paper_ids")
    @classmethod
    def validate_paper_ids(cls, paper_ids: list[str]) -> list[str]:
        normalized_ids = [paper_id.strip() for paper_id in paper_ids]
        if any(not paper_id for paper_id in normalized_ids):
            raise ValueError("Paper IDs cannot be empty.")
        if len(set(normalized_ids)) != len(normalized_ids):
            raise ValueError("Paper IDs must be unique.")
        return normalized_ids


class ResearchGapRequest(BaseModel):
    paper_ids: list[str] = Field(min_length=1, max_length=10)

    @field_validator("paper_ids")
    @classmethod
    def validate_paper_ids(cls, paper_ids: list[str]) -> list[str]:
        normalized_ids = [paper_id.strip() for paper_id in paper_ids]
        if any(not paper_id for paper_id in normalized_ids):
            raise ValueError("Paper IDs cannot be empty.")
        if len(set(normalized_ids)) != len(normalized_ids):
            raise ValueError("Paper IDs must be unique.")
        return normalized_ids


def _log_api_error(event: str, **fields: str | int) -> None:
    _api_logger.error(
        json.dumps({"event": event, **fields}, sort_keys=True)
    )


def _write_pdf_upload(upload: UploadFile, destination) -> None:
    initial_chunk = upload.file.read(min(1024, MAX_UPLOAD_SIZE_BYTES + 1))
    if b"%PDF-" not in initial_chunk:
        raise HTTPException(status_code=400, detail="The uploaded file is not a valid PDF.")

    total_bytes = len(initial_chunk)
    if total_bytes > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=UPLOAD_TOO_LARGE_DETAIL,
        )
    destination.write(initial_chunk)
    while chunk := upload.file.read(UPLOAD_CHUNK_SIZE_BYTES):
        total_bytes += len(chunk)
        if total_bytes > MAX_UPLOAD_SIZE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=UPLOAD_TOO_LARGE_DETAIL,
            )
        destination.write(chunk)


def _attach_claim_paper_id(analysis: object, paper_id: str) -> None:
    if not isinstance(analysis, dict):
        return

    claim_records = analysis.get("claim_records")
    if not isinstance(claim_records, list):
        return

    for record in claim_records:
        if isinstance(record, dict):
            record.setdefault("paper_id", paper_id)


@app.get("/")
def root():
    return {
        "message": "Academic Literature Intelligence Platform API"
    }


@app.post("/papers/upload", response_model=PaperUploadResponse)
async def upload_paper(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed.")
    if file.size is not None and file.size > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(status_code=413, detail=UPLOAD_TOO_LARGE_DETAIL)

    upload_dir = os.path.join(os.getcwd(), "uploads")
    os.makedirs(upload_dir, exist_ok=True)

    safe_name = os.path.basename(file.filename)
    file_path = os.path.join(upload_dir, f"{uuid4().hex}.pdf")

    try:
        with open(file_path, "wb") as buffer:
            _write_pdf_upload(file, buffer)

        paper = extract_pdf_content(file_path)
    except HTTPException:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise
    except Exception as exc:
        if os.path.exists(file_path):
            os.remove(file_path)
        _log_api_error(
            "paper_parse_failed",
            error_type=type(exc).__name__,
        )
        raise HTTPException(
            status_code=400,
            detail=f"Invalid PDF or parsing failed: {str(exc)}"
        ) from exc

    analysis = analyze_paper(paper["text"], paper["sections"], paper["pages"])
    try:
        paper_id = save_paper({
            "filename": safe_name,
            "metadata": paper["metadata"],
            "sections": paper["sections"],
            "analysis": analysis,
        })
    except Exception as exc:
        _log_api_error(
            "paper_storage_unavailable",
            operation="save_paper",
            error_type=type(exc).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail="Paper storage is unavailable.",
        ) from exc

    _attach_claim_paper_id(analysis, paper_id)
    return {
        "paper_id": paper_id,
        "filename": safe_name,
        "metadata": PaperMetadata(**paper["metadata"]),
        "sections": paper["sections"],
        "analysis": analysis,
    }


@app.get("/papers/{paper_id}")
def retrieve_paper(paper_id: str):
    try:
        paper = get_paper(paper_id)
    except Exception as exc:
        _log_api_error(
            "paper_storage_unavailable",
            operation="get_paper",
            error_type=type(exc).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail="Paper storage is unavailable.",
        ) from exc
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found.")
    _attach_claim_paper_id(paper.get("analysis"), paper_id)
    return paper


def _load_selected_papers(paper_ids: list[str]) -> dict[str, dict]:
    papers = {}
    missing_ids = []
    try:
        for paper_id in paper_ids:
            paper = get_paper(paper_id)
            if paper is None:
                missing_ids.append(paper_id)
            else:
                papers[paper_id] = paper
    except Exception as exc:
        _log_api_error(
            "paper_storage_unavailable",
            operation="load_selected_papers",
            selected_count=len(paper_ids),
            error_type=type(exc).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail="Paper storage is unavailable.",
        ) from exc

    if missing_ids:
        raise HTTPException(
            status_code=404,
            detail={"message": "One or more papers were not found.", "paper_ids": missing_ids},
        )
    return papers


@app.post("/papers/compare")
def compare_selected_papers(request: PaperComparisonRequest):
    """Compare claims and reported study context for explicitly selected papers."""
    return compare_papers(_load_selected_papers(request.paper_ids))


@app.post("/papers/gaps")
def find_research_gaps(request: ResearchGapRequest):
    """Find cited limitations and screening signals within selected papers."""
    return detect_research_gaps(_load_selected_papers(request.paper_ids))