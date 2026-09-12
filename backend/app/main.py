from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from app.services.pdf_parser import extract_pdf_content
from app.services.paper_analyzer import analyze_paper
from app.services.paper_repository import get_paper, save_paper
import os
import shutil
from dotenv import load_dotenv
load_dotenv()
app = FastAPI(
    title="Academic Literature Intelligence Platform",
    version="1.0.0"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("FRONTEND_ORIGIN", "http://localhost:5173").split(","),
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


@app.get("/")
def root():
    return {
        "message": "Academic Literature Intelligence Platform API"
    }


@app.post("/papers/upload", response_model=PaperUploadResponse)
async def upload_paper(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed.")

    upload_dir = os.path.join(os.getcwd(), "uploads")
    os.makedirs(upload_dir, exist_ok=True)

    safe_name = os.path.basename(file.filename)
    file_path = os.path.join(upload_dir, safe_name)

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        paper = extract_pdf_content(file_path)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid PDF or parsing failed: {str(exc)}"
        ) from exc

    analysis = analyze_paper(paper["text"], paper["sections"])
    paper_id = save_paper({
        "filename": safe_name,
        "metadata": paper["metadata"],
        "sections": paper["sections"],
        "analysis": analysis,
    })

    return {
        "paper_id": paper_id,
        "filename": safe_name,
        "metadata": PaperMetadata(**paper["metadata"]),
        "sections": paper["sections"],
        "analysis": analysis,
    }


@app.get("/papers/{paper_id}")
def retrieve_paper(paper_id: str):
    paper = get_paper(paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found.")
    return paper