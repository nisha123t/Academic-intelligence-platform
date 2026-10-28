import io
import json
import logging
import sys
from types import SimpleNamespace

from fastapi import HTTPException
from fastapi.testclient import TestClient
import fitz
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.metadata_extractor import extract_metadata
from app.services.paper_analyzer import analyze_paper, extract_claim_records
from app.services.pdf_parser import extract_pdf_content
from app.services.paper_repository import get_paper, save_paper
from app.main import _write_pdf_upload, app
from app import main as main_module
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


def test_pdf_parser_retains_only_page_text_needed_for_claim_sources(tmp_path):
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Results show a measurable improvement.")
    pdf_path = tmp_path / "page-source.pdf"
    document.save(pdf_path)
    document.close()

    parsed = extract_pdf_content(str(pdf_path))

    assert parsed["pages"][0]["page_number"] == 1
    assert "Results show a measurable improvement." in parsed["pages"][0]["text"]
    assert set(parsed["pages"][0]) == {"page_number", "text"}


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
    score = analysis["evidence_score"]
    assert score["score_type"] == "evidence_stability_heuristic"
    assert score["normalization"]["applied_score"] == score["score"]
    assert sum(
        factor["points"] for factor in score["factors"] if factor["applied"]
    ) == score["score"]
    assert "calibrated confidence" in score["limitations"]
    assert "not scientific validity" in score["limitations"]


def test_evidence_stability_score_explains_empty_and_saturated_inputs():
    empty = analyze_paper("", {})
    full = analyze_paper(
        "Results show improvement (p < 0.05).",
        {"methodology": "We used a quantitative survey."},
    )

    assert empty["evidence_score"]["score"] == 25
    assert empty["evidence_score"]["normalization"]["label_thresholds"] == {
        "low": "0-49",
        "moderate": "50-74",
        "high": "75-100",
    }
    assert full["evidence_score"]["score"] == 100
    assert full["evidence_score"]["normalization"]["raw_score"] == 100


def test_claim_records_include_category_section_page_and_paper_id():
    text = (
        "Results show that the treatment caused improvement. "
        "We hypothesize that the effect will persist. "
        "A limitation is the small sample. "
        "The outcome was associated with age."
    )
    first_page = "Results show that the treatment caused improvement. We hypothesize that the effect will persist."
    second_page = "A limitation is the small sample. The outcome was associated with age."
    sections = {
        "results": "Results show that the treatment caused improvement.",
        "hypothesis": "We hypothesize that the effect will persist.",
        "limitations": "A limitation is the small sample.",
        "discussion": "The outcome was associated with age.",
    }
    pages = [
        {"page_number": 1, "text": first_page},
        {"page_number": 2, "text": second_page},
    ]

    analysis = analyze_paper(text, sections, pages)
    records = analysis["claim_records"]

    assert [record["category"] for record in records] == [
        "causal",
        "hypothesis",
        "limitation",
        "correlational",
    ]
    assert [record["classification_basis"] for record in records] == [
        "caused",
        "We hypothesize",
        "limitation",
        "associated with",
    ]
    assert all(
        "does not verify the scientific finding" in record["classification_reason"]
        for record in records
    )
    assert [record["section"] for record in records] == [
        "results",
        "hypothesis",
        "limitations",
        "discussion",
    ]
    assert [record["page"] for record in records] == [1, 1, 2, 2]
    main_module._attach_claim_paper_id(analysis, "paper-123")
    assert all(record["paper_id"] == "paper-123" for record in records)
    assert analysis["claims"]


def test_claim_records_leave_unavailable_source_locations_unknown():
    records = extract_claim_records("Results show a difference.", {}, [])

    assert records == [
        {
            "text": "Results show a difference.",
            "category": "finding",
            "classification_basis": "Results show",
            "classification_reason": (
                "Heuristically classified from wording marker 'Results show'; "
                "this does not verify the scientific finding."
            ),
            "section": None,
            "page": None,
        }
    ]


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


def _stub_upload_pipeline(monkeypatch):
    monkeypatch.setattr(
        main_module,
        "extract_pdf_content",
        lambda _path: {
            "text": "PDF text",
            "metadata": {},
            "sections": {},
            "pages": [],
        },
    )
    monkeypatch.setattr(
        main_module, "analyze_paper", lambda _text, _sections, _pages: {}
    )
    monkeypatch.setattr(main_module, "save_paper", lambda _paper: "test-paper-id")


def test_upload_accepts_pdf_at_size_limit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(main_module, "MAX_UPLOAD_SIZE_BYTES", 5)
    _stub_upload_pipeline(monkeypatch)

    response = TestClient(app).post(
        "/papers/upload",
        files={"file": ("example.pdf", b"%PDF-", "application/pdf")},
    )

    assert response.status_code == 200
    assert response.json()["paper_id"] == "test-paper-id"
    assert len(list((tmp_path / "uploads").glob("*.pdf"))) == 1


def test_upload_rejects_pdf_over_size_limit_and_removes_partial_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(main_module, "MAX_UPLOAD_SIZE_BYTES", 1024)

    response = TestClient(app).post(
        "/papers/upload",
        files={
            "file": (
                "large.pdf",
                b"%PDF-" + b"x" * 1020,
                "application/pdf",
            )
        },
    )

    assert response.status_code == 413
    assert "50 MiB" in response.json()["detail"]
    assert not (tmp_path / "uploads").exists()


def test_upload_stream_limit_applies_when_size_is_unavailable(monkeypatch):
    monkeypatch.setattr(main_module, "MAX_UPLOAD_SIZE_BYTES", 1024)
    upload = SimpleNamespace(file=io.BytesIO(b"%PDF-" + b"x" * 1020))

    try:
        _write_pdf_upload(upload, io.BytesIO())
    except HTTPException as error:
        assert error.status_code == 413
    else:
        raise AssertionError("Expected an oversized upload to be rejected.")


def test_upload_rejects_pdf_extension_with_invalid_content(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    response = TestClient(app).post(
        "/papers/upload",
        files={"file": ("not-a-pdf.pdf", b"not a PDF", "application/pdf")},
    )

    assert response.status_code == 400
    assert list((tmp_path / "uploads").iterdir()) == []


def test_upload_removes_file_when_pdf_parsing_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def reject_malformed_pdf(_path):
        raise ValueError("Malformed PDF")

    monkeypatch.setattr(main_module, "extract_pdf_content", reject_malformed_pdf)
    response = TestClient(app).post(
        "/papers/upload",
        files={"file": ("malformed.pdf", b"%PDF-malformed", "application/pdf")},
    )

    assert response.status_code == 400
    assert "Malformed PDF" in response.json()["detail"]
    assert list((tmp_path / "uploads").iterdir()) == []


def test_uploads_with_same_filename_do_not_overwrite(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _stub_upload_pipeline(monkeypatch)
    client = TestClient(app)

    first_response = client.post(
        "/papers/upload",
        files={"file": ("example.pdf", b"%PDF-first", "application/pdf")},
    )
    second_response = client.post(
        "/papers/upload",
        files={"file": ("example.pdf", b"%PDF-second", "application/pdf")},
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    saved_files = list((tmp_path / "uploads").glob("*.pdf"))
    assert len(saved_files) == 2
    assert saved_files[0].read_bytes() != saved_files[1].read_bytes()


def test_pdf_upload_returns_claim_with_page_section_and_paper_id(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Results")
    page.insert_text((72, 100), "Results show that treatment caused improvement.")
    pdf_content = document.tobytes()
    document.close()

    response = TestClient(app).post(
        "/papers/upload",
        files={"file": ("study.pdf", pdf_content, "application/pdf")},
    )

    assert response.status_code == 200
    result = response.json()
    claim = result["analysis"]["claim_records"][0]
    assert claim["text"] == "Results show that treatment caused improvement."
    assert claim["category"] == "causal"
    assert claim["classification_basis"] == "caused"
    assert claim["section"] == "results"
    assert claim["page"] == 1
    assert claim["paper_id"] == result["paper_id"]


def test_retrieve_missing_paper_returns_not_found(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)

    response = TestClient(app).get("/papers/missing-paper")

    assert response.status_code == 404


def test_paper_storage_errors_are_logged_without_exposing_exception_details(
    monkeypatch, caplog
):
    secret_detail = "database failure for postgresql://user:secret@example.test"

    def fail_to_load_paper(_paper_id):
        raise RuntimeError(secret_detail)

    monkeypatch.setattr(main_module, "get_paper", fail_to_load_paper)
    with caplog.at_level(logging.ERROR, logger="app.api"):
        response = TestClient(app).get("/papers/paper-a")

    assert response.status_code == 503
    assert response.json()["detail"] == "Paper storage is unavailable."
    assert secret_detail not in response.text
    event = json.loads(caplog.records[-1].getMessage())
    assert event == {
        "error_type": "RuntimeError",
        "event": "paper_storage_unavailable",
        "operation": "get_paper",
    }


def test_upload_storage_failure_logs_only_redacted_error_metadata(
    tmp_path, monkeypatch, caplog
):
    monkeypatch.chdir(tmp_path)
    _stub_upload_pipeline(monkeypatch)

    def fail_to_save(_paper):
        raise RuntimeError("credential=private-value")

    monkeypatch.setattr(main_module, "save_paper", fail_to_save)
    with caplog.at_level(logging.ERROR, logger="app.api"):
        response = TestClient(app).post(
            "/papers/upload",
            files={"file": ("study.pdf", b"%PDF-valid", "application/pdf")},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "Paper storage is unavailable."
    assert "private-value" not in response.text
    event = json.loads(caplog.records[-1].getMessage())
    assert event == {
        "error_type": "RuntimeError",
        "event": "paper_storage_unavailable",
        "operation": "save_paper",
    }


def test_compare_endpoint_returns_claim_evidence_for_selected_papers(monkeypatch):
    papers = {
        "paper-a": {
            "filename": "a.pdf",
            "metadata": {"title": "Study A"},
            "analysis": {
                "evidence_score": {"score": 65, "label": "moderate"},
                "claim_records": [
                    {
                        "text": "The treatment improved accuracy.",
                        "category": "finding",
                        "section": "results",
                        "page": 2,
                    }
                ]
            },
        },
        "paper-b": {
            "filename": "b.pdf",
            "metadata": {"title": "Study B"},
            "analysis": {
                "evidence_score": {"score": 75, "label": "high"},
                "claim_records": [
                    {
                        "text": "The treatment did not improve accuracy.",
                        "category": "finding",
                        "section": "results",
                        "page": 3,
                    }
                ]
            },
        },
    }
    monkeypatch.setattr(main_module, "get_paper", lambda paper_id: papers.get(paper_id))

    response = TestClient(app).post(
        "/papers/compare",
        json={"paper_ids": ["paper-a", "paper-b"]},
    )

    assert response.status_code == 200
    result = response.json()
    assert [paper["paper_id"] for paper in result["papers"]] == [
        "paper-a",
        "paper-b",
    ]
    assert result["comparisons"][0]["status"] == "potential_conflict"
    assert result["summary_statistics"]["evidence_stability_scores"]["average"] == 70
    evidence = result["comparisons"][0]["claim_comparisons"][0]["evidence"]
    assert [claim["paper_id"] for claim in evidence] == ["paper-a", "paper-b"]
    assert [claim["page"] for claim in evidence] == [2, 3]


def test_compare_endpoint_rejects_duplicate_paper_ids():
    response = TestClient(app).post(
        "/papers/compare",
        json={"paper_ids": ["paper-a", " paper-a "]},
    )

    assert response.status_code == 422


def test_compare_endpoint_requires_two_to_ten_papers():
    client = TestClient(app)
    too_few = client.post("/papers/compare", json={"paper_ids": ["paper-a"]})
    too_many = client.post(
        "/papers/compare",
        json={"paper_ids": [f"paper-{index}" for index in range(11)]},
    )

    assert too_few.status_code == 422
    assert too_many.status_code == 422


def test_compare_endpoint_returns_not_found_for_missing_selected_paper(monkeypatch):
    monkeypatch.setattr(main_module, "get_paper", lambda _paper_id: None)

    response = TestClient(app).post(
        "/papers/compare",
        json={"paper_ids": ["paper-a", "paper-b"]},
    )

    assert response.status_code == 404
    assert response.json()["detail"]["paper_ids"] == ["paper-a", "paper-b"]


def test_compare_endpoint_reports_repository_unavailable(monkeypatch):
    def fail_to_load_paper(_paper_id):
        raise RuntimeError("database detail")

    monkeypatch.setattr(main_module, "get_paper", fail_to_load_paper)

    response = TestClient(app).post(
        "/papers/compare",
        json={"paper_ids": ["paper-a", "paper-b"]},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Paper storage is unavailable."
    assert "database detail" not in response.text


def test_research_gaps_endpoint_returns_cited_single_paper_gaps(monkeypatch):
    paper = {
        "filename": "study.pdf",
        "metadata": {"title": "Study"},
        "sections": {},
        "analysis": {
            "claim_records": [
                {
                    "text": "A limitation is the small sample.",
                    "category": "limitation",
                    "section": "limitations",
                    "page": 4,
                }
            ],
            "research_gaps": [],
        },
    }
    monkeypatch.setattr(
        main_module,
        "get_paper",
        lambda paper_id: paper if paper_id == "paper-a" else None,
    )

    response = TestClient(app).post(
        "/papers/gaps",
        json={"paper_ids": ["paper-a"]},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["gaps"][0]["type"] == "author_reported_limitation"
    assert result["gaps"][0]["evidence"][0]["page"] == 4
    assert result["gaps"][0]["evidence"][0]["paper_id"] == "paper-a"
    assert result["gaps"][0]["opportunity_score"] == 40


def test_research_gaps_endpoint_returns_potential_conflict_review_signal(monkeypatch):
    papers = {
        "paper-a": {
            "analysis": {
                "claim_records": [
                    {
                        "text": "The intervention improved accuracy.",
                        "category": "causal",
                        "section": "results",
                        "page": 2,
                    }
                ]
            }
        },
        "paper-b": {
            "analysis": {
                "claim_records": [
                    {
                        "text": "The intervention did not improve accuracy.",
                        "category": "causal",
                        "section": "results",
                        "page": 3,
                    }
                ]
            }
        },
    }
    monkeypatch.setattr(main_module, "get_paper", lambda paper_id: papers.get(paper_id))

    response = TestClient(app).post(
        "/papers/gaps",
        json={"paper_ids": ["paper-a", "paper-b"]},
    )

    assert response.status_code == 200
    gap = response.json()["gaps"][0]
    assert gap["type"] == "potentially_inconsistent_findings"
    assert gap["confidence"] == "heuristic_low"
    assert {item["paper_id"] for item in gap["evidence"]} == {
        "paper-a",
        "paper-b",
    }


def test_research_gaps_endpoint_rejects_duplicate_ids_and_missing_papers(monkeypatch):
    client = TestClient(app)
    duplicate = client.post(
        "/papers/gaps",
        json={"paper_ids": ["paper-a", " paper-a "]},
    )
    monkeypatch.setattr(main_module, "get_paper", lambda _paper_id: None)
    missing = client.post(
        "/papers/gaps",
        json={"paper_ids": ["paper-a"]},
    )

    assert duplicate.status_code == 422
    assert missing.status_code == 404
    assert missing.json()["detail"]["paper_ids"] == ["paper-a"]
