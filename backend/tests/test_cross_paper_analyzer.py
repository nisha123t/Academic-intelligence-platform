import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.cross_paper_analyzer import compare_papers


def _paper(claims):
    return {
        "filename": "study.pdf",
        "metadata": {"title": "Example study"},
        "analysis": {
            "claim_records": [
                {
                    "text": claim,
                    "category": "finding",
                    "section": "results",
                    "page": 2,
                }
                for claim in claims
            ]
        },
    }


def test_compare_papers_flags_opposing_outcome_cues_as_potential_only():
    result = compare_papers(
        {
            "paper-a": _paper(["The treatment improved accuracy."]),
            "paper-b": _paper(["The treatment did not improve accuracy."]),
        }
    )

    comparison = result["comparisons"][0]
    assert comparison["status"] == "potential_conflict"
    assert comparison["confidence"] == "heuristic_low"
    assert "not a verified contradiction" in comparison["explanation"]
    assert [
        evidence["paper_id"]
        for evidence in comparison["claim_comparisons"][0]["evidence"]
    ] == ["paper-a", "paper-b"]


def test_compare_papers_marks_lexically_aligned_claims_as_supporting():
    result = compare_papers(
        {
            "paper-a": _paper(["The treatment improved accuracy."]),
            "paper-b": _paper(["The treatment improved accuracy significantly."]),
        }
    )

    assert result["comparisons"][0]["status"] == "supporting"
    assert "does not establish independent validity" in result["comparisons"][0][
        "explanation"
    ]


def test_compare_papers_marks_distinct_measured_outcomes_as_complementary():
    result = compare_papers(
        {
            "paper-a": _paper(["The treatment improved accuracy."]),
            "paper-b": _paper(["The treatment reduced cost."]),
        }
    )

    assert result["comparisons"][0]["status"] == "complementary"


def test_compare_papers_distinguishes_incomparable_and_insufficient_claims():
    incomparable = compare_papers(
        {
            "paper-a": _paper(["Researchers studied sleep duration in adolescents."]),
            "paper-b": _paper(["The engine temperature increased during testing."]),
        }
    )
    insufficient = compare_papers(
        {
            "paper-a": _paper(["The intervention affected learning outcomes."]),
            "paper-b": _paper(["The intervention influenced learning outcomes."]),
        }
    )
    no_claims = compare_papers(
        {"paper-a": _paper([]), "paper-b": _paper(["A finding was reported."])}
    )

    assert incomparable["comparisons"][0]["status"] == "incomparable"
    assert insufficient["comparisons"][0]["status"] == "insufficient_evidence"
    assert no_claims["comparisons"][0]["status"] == "insufficient_evidence"


def test_compare_papers_supports_legacy_claim_strings():
    first = {
        "analysis": {
            "claim_records": [],
            "claims": ["The treatment improved accuracy."],
        }
    }
    second = {"analysis": {"claims": ["The treatment improved accuracy."]}}

    result = compare_papers({"paper-a": first, "paper-b": second})

    comparison = result["comparisons"][0]
    assert comparison["status"] == "supporting"
    assert comparison["claim_comparisons"][0]["evidence"][0]["paper_id"] == "paper-a"


def test_compare_papers_reports_extracted_study_context_without_inference():
    paper = _paper(["A limitation is the small sample."])
    paper["analysis"]["claim_records"][0]["category"] = "limitation"
    paper["analysis"].update(
        {
            "statistics": [
                "We recruited 120 participants.",
                "The result was significant (p < 0.05).",
            ],
            "methodology": {"available": True, "method_terms": ["survey"]},
            "evidence_score": {"score": 65, "label": "moderate"},
        }
    )

    result = compare_papers({"paper-a": paper, "paper-b": _paper([])})
    context = result["papers"][0]["study_context"]

    assert context["sample_size_signals"] == ["We recruited 120 participants."]
    assert context["uncertainty_signals"] == [
        "The result was significant (p < 0.05)."
    ]
    assert context["limitations"] == ["A limitation is the small sample."]
    assert context["methodology"]["method_terms"] == ["survey"]
    assert context["evidence_score"]["score"] == 65
    assert result["papers"][1]["study_context"]["sample_size_signals"] == []
    context_comparison = result["comparisons"][0]["study_context_comparison"]
    assert context_comparison["sample_size_signals"]["status"] == "not_comparable"

    second_paper = _paper([])
    second_paper["analysis"].update(
        {
            "statistics": ["We recruited 90 participants."],
            "methodology": {"available": True, "method_terms": ["experiment"]},
            "evidence_score": {"score": 55, "label": "moderate"},
        }
    )
    result = compare_papers({"paper-a": paper, "paper-b": second_paper})
    context_comparison = result["comparisons"][0]["study_context_comparison"]
    assert context_comparison["method_terms"]["status"] == "reported_values_differ"
    assert (
        context_comparison["sample_size_signals"]["status"]
        == "reported_values_differ"
    )
    assert "not evidence of a contradiction" in context_comparison["interpretation"]


def test_compare_papers_summarizes_only_available_cross_paper_statistics():
    first = _paper([])
    first["metadata"]["year"] = 2022
    first["analysis"].update(
        {
            "methodology": {"available": True, "method_terms": ["survey"]},
            "evidence_score": {"score": 60, "label": "moderate"},
        }
    )
    second = _paper([])
    second["metadata"]["year"] = None
    second["analysis"].update(
        {
            "methodology": {"available": True, "method_terms": ["survey", "experiment"]},
            "evidence_score": {"score": 80, "label": "high"},
        }
    )
    result = compare_papers({"paper-a": first, "paper-b": second})
    statistics = result["summary_statistics"]

    assert statistics["paper_count"] == 2
    assert statistics["publication_years"] == {
        "available_count": 1,
        "values": [{"paper_id": "paper-a", "year": 2022}],
    }
    assert statistics["evidence_stability_scores"]["available_count"] == 2
    assert statistics["evidence_stability_scores"]["average"] == 70
    assert statistics["evidence_stability_scores"]["minimum"] == 60
    assert statistics["evidence_stability_scores"]["maximum"] == 80
    assert statistics["method_term_counts"] == [
        {"term": "experiment", "paper_count": 1},
        {"term": "survey", "paper_count": 2},
    ]


def test_compare_papers_reports_unavailable_summary_statistics_as_empty():
    result = compare_papers(
        {
            "paper-a": {"analysis": {}},
            "paper-b": {"analysis": {}},
        }
    )

    statistics = result["summary_statistics"]
    assert statistics["publication_years"]["available_count"] == 0
    assert statistics["evidence_stability_scores"] == {
        "available_count": 0,
        "average": None,
        "minimum": None,
        "maximum": None,
        "values": [],
    }
    assert statistics["method_term_counts"] == []
