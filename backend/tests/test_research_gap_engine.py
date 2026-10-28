import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.research_gap_engine import detect_research_gaps


def _paper(paper_id, *, claims=None, gaps=None, sections=None):
    records = [
        {
            "text": claim,
            "category": "limitation" if "limitation" in claim.casefold() else "finding",
            "section": "limitations" if "limitation" in claim.casefold() else "results",
            "page": index + 1,
        }
        for index, claim in enumerate(claims or [])
    ]
    return {
        "filename": f"{paper_id}.pdf",
        "metadata": {"title": paper_id},
        "sections": sections or {},
        "analysis": {
            "claim_records": records,
            "research_gaps": gaps or [],
        },
    }


def test_explicit_limitation_is_source_linked_and_scored_with_explanation():
    paper = _paper(
        "paper-a",
        claims=["A limitation is the small sample in this study."],
        gaps=["A limitation is the small sample in this study."],
        sections={"limitations": "A limitation is the small sample in this study."},
    )

    result = detect_research_gaps({"paper-a": paper})

    assert len(result["gaps"]) == 1
    gap = result["gaps"][0]
    assert gap["type"] == "author_reported_limitation"
    assert gap["opportunity_score"] == 40
    assert gap["score_label"] == "heuristic"
    assert gap["confidence"] == "heuristic_low"
    assert gap["score_factors"][0]["points"] == 40
    assert "'limitation'" in gap["identification_reason"]
    assert "does not independently validate" in gap["identification_reason"]
    assert gap["evidence"] == [
        {
            "paper_id": "paper-a",
            "text": "A limitation is the small sample in this study.",
            "section": "limitations",
            "page": 1,
            "source_type": "author_statement",
        }
    ]


def test_explicit_missing_comparison_is_reported_but_not_inferred():
    paper = _paper(
        "paper-a",
        gaps=["A comparison between the two approaches was not made."],
    )

    result = detect_research_gaps({"paper-a": paper})

    assert result["gaps"][0]["type"] == "author_reported_underexplored_area"
    assert result["gaps"][0]["evidence"][0]["text"] == (
        "A comparison between the two approaches was not made."
    )
    assert result["gaps"][0]["evidence"][0]["source_type"] == "author_statement"


def test_explicit_future_work_and_underexplored_statements_are_distinguished():
    paper = _paper(
        "paper-a",
        gaps=[
            "Future work should investigate the approach in rural settings.",
            "Little is known about long-term outcomes.",
        ],
    )

    result = detect_research_gaps({"paper-a": paper})

    assert {gap["type"] for gap in result["gaps"]} == {
        "future_research",
        "author_reported_underexplored_area",
    }
    scores = {gap["type"]: gap["opportunity_score"] for gap in result["gaps"]}
    assert scores["future_research"] == 40
    assert scores["author_reported_underexplored_area"] == 25
    assert all(gap["evidence"][0]["page"] is None for gap in result["gaps"])


def test_repeated_author_statement_increases_score_and_keeps_all_sources():
    statement = "A limitation is the small sample."
    result = detect_research_gaps(
        {
            "paper-a": _paper("paper-a", claims=[statement]),
            "paper-b": _paper("paper-b", claims=[statement]),
        }
    )

    gap = result["gaps"][0]
    assert gap["opportunity_score"] == 55
    assert len(gap["evidence"]) == 2
    assert gap["score_factors"][1]["name"] == "additional_evidence_paper"
    assert gap["score_factors"][1]["points"] == 15
    assert "not corpus-wide prevalence" in gap["score_factors"][1]["reason"]


def test_potential_conflict_creates_review_signal_not_verified_gap():
    result = detect_research_gaps(
        {
            "paper-a": _paper(
                "paper-a", claims=["The intervention improved accuracy."]
            ),
            "paper-b": _paper(
                "paper-b", claims=["The intervention did not improve accuracy."]
            ),
        }
    )

    gap = result["gaps"][0]
    assert gap["type"] == "potentially_inconsistent_findings"
    assert gap["opportunity_score"] == 45
    assert "not a verified contradiction" in gap["statement"]
    assert "not a verified contradiction" in gap["identification_reason"]
    assert {item["paper_id"] for item in gap["evidence"]} == {
        "paper-a",
        "paper-b",
    }
    assert all(
        item["source_type"] == "claim_pair_screening_signal"
        for item in gap["evidence"]
    )


def test_absent_topics_or_comparisons_do_not_create_research_gaps():
    result = detect_research_gaps(
        {
            "paper-a": _paper("paper-a", claims=["The cohort included adults."]),
            "paper-b": _paper("paper-b", claims=["A sensor measured temperature."]),
        }
    )

    assert result["gaps"] == []
    assert "No gap is inferred merely" in result["scoring"]["limitations"][2]


def test_score_weights_are_configurable_and_validated():
    paper = _paper("paper-a", claims=["A limitation is the small sample."])

    result = detect_research_gaps(
        {"paper-a": paper},
        score_weights={"explicit_limitation_or_future_work": 70},
    )

    assert result["gaps"][0]["opportunity_score"] == 70
    assert result["scoring"]["weights"]["explicit_limitation_or_future_work"] == 70
    bounded = detect_research_gaps(
        {
            "paper-a": _paper("paper-a", claims=["A limitation is the small sample."]),
            "paper-b": _paper("paper-b", claims=["A limitation is the small sample."]),
        },
        score_weights={
            "explicit_limitation_or_future_work": 100,
            "additional_evidence_paper": 100,
            "maximum_recurrence_points": 100,
        },
    )
    assert bounded["gaps"][0]["opportunity_score"] == 100
    with pytest.raises(ValueError, match="Unknown opportunity score weights"):
        detect_research_gaps({"paper-a": paper}, score_weights={"unknown": 10})
    with pytest.raises(ValueError, match="integer from 0 to 100"):
        detect_research_gaps(
            {"paper-a": paper},
            score_weights={"explicit_limitation_or_future_work": 101},
        )


def test_empty_selection_returns_empty_gap_list():
    result = detect_research_gaps({})

    assert result["paper_ids"] == []
    assert result["gaps"] == []
