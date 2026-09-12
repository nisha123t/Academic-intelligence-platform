import sys
from fastapi.testclient import TestClient
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.metadata_extractor import extract_metadata
from app.services.paper_analyzer import analyze_paper
from app.services.paper_repository import get_paper, save_paper
from app.main import app
from app.services.section_detector import detect_sections


def test_detect_sections_recognizes_common_sections():
    sample_text = """
    Abstract
    This study examines the effect of social media on learning.

    Introduction
    Students increasingly rely on digital tools.

    Methods
    We recruited 120 participants.

    Results
    The difference was significant.

    Discussion
    These findings suggest a practical implication.

    References
    Smith, J. (2020). Example.
    """

    sections = detect_sections(sample_text)

    assert "abstract" in sections
    assert "introduction" in sections
    assert "methodology" in sections
    assert "results" in sections
    assert "discussion" in sections
    assert "references" in sections


def test_extract_metadata_handles_title_authors_and_doi():
    sample_text = """
    Using Social Media to Improve Academic Performance
    Emily Carter, Daniel Kim, and Olivia Patel
    Journal of Learning Research, 2024
    DOI: 10.1000/example/abc123
    Keywords: social media, learning, students, education

    Abstract
    We studied 240 participants.
    """

    metadata = extract_metadata(sample_text, detect_sections(sample_text))

    assert metadata["title"] == "Using Social Media to Improve Academic Performance"
    assert metadata["authors"] == ["Emily Carter", "Daniel Kim", "Olivia Patel"]
    assert metadata["year"] == 2024
    assert metadata["doi"] == "10.1000/example/abc123"
    assert metadata["keywords"] == ["social media", "learning", "students", "education"]


def test_extract_metadata_skips_journal_banner_before_title():
    sample_text = """
    Contents lists available at ScienceDirect
    Applied Energy
    journal homepage: www.elsevier.com/locate/apen
    SAGE: Sustainable and green energy-aware client selection for federated
    learning in IoT
    Martina Savoia, Ciro Della Bruna, and Francesco Piccialli
    Keywords:
    Federated learning
    Decentralized learning
    Non-IID-ness
    A B S T R A C T
    We propose a new energy-aware client selection strategy.
    """

    metadata = extract_metadata(sample_text, detect_sections(sample_text))

    assert metadata["title"] == "SAGE: Sustainable and green energy-aware client selection for federated learning in IoT"
    assert metadata["authors"] == ["Martina Savoia", "Ciro Della Bruna", "Francesco Piccialli"]
    assert metadata["keywords"] == ["Federated learning", "Decentralized learning", "Non-IID-ness"]


def test_analyze_paper_extracts_basic_evidence_signals():
    text = (
        "Methods: We conducted a quantitative survey with 120 participants. "
        "Results show a significant effect (p < 0.05). "
        "Future work should test the approach on larger datasets."
    )
    sections = {
        "methodology": "We conducted a quantitative survey with 120 participants.",
    }

    analysis = analyze_paper(text, sections)

    assert analysis["statistics"]
    assert analysis["methodology"]["available"] is True
    assert analysis["claims"]
    assert analysis["research_gaps"]
    assert analysis["evidence_score"]["score"] >= 50


def test_local_repository_saves_and_retrieves_a_paper(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    paper = {"filename": "example.pdf", "metadata": {}, "sections": {}, "analysis": {}}

    paper_id = save_paper(paper)

    assert get_paper(paper_id)["filename"] == "example.pdf"


def test_upload_rejects_non_pdf_files():
    response = TestClient(app).post(
        "/papers/upload",
        files={"file": ("notes.txt", b"not a PDF", "text/plain")},
    )

    assert response.status_code == 400


def test_retrieve_missing_paper_returns_not_found():
    response = TestClient(app).get("/papers/missing-paper")

    assert response.status_code == 404
