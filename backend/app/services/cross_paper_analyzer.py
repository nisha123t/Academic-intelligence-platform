import re
from itertools import combinations


_TOKEN_PATTERN = re.compile(r"[a-z][a-z0-9-]*")
_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "being", "by",
    "for", "from", "in", "into", "is", "it", "of", "on", "or", "our",
    "that", "the", "their", "this", "to", "was", "were", "we", "with",
    "study", "studies", "paper", "result", "results", "show", "shows",
    "found", "find", "finding", "findings", "suggest", "suggests",
    "indicate", "indicates", "demonstrate", "demonstrates",
}
_NEGATION_PATTERN = re.compile(
    r"\b(?:not|no|never|neither|without|fail(?:ed|s)? to|"
    r"didn't|doesn't|wasn't|weren't)\b",
    re.I,
)
_POSITIVE_OUTCOMES = {
    "benefit", "benefits", "effective", "effectiveness", "higher", "improve",
    "improved", "improves", "increase", "increased", "increases", "positive",
}
_NEGATIVE_OUTCOMES = {
    "decrease", "decreased", "decreases", "decline", "declined", "ineffective",
    "lower", "negative", "reduce", "reduced", "reduces", "worse", "worsened",
}
_MEASURED_OUTCOMES = {
    "accuracy", "adoption", "cost", "costs", "energy", "error", "errors",
    "latency", "performance", "precision", "quality", "recall", "reliability",
    "score", "scores", "time", "utility",
}
_SAMPLE_SIZE_PATTERN = re.compile(
    r"\b(?:n|sample size)\s*[=:]\s*\d+\b|\b\d+\s+"
    r"(?:participants|subjects|patients|observations|samples)\b",
    re.I,
)
_UNCERTAINTY_PATTERN = re.compile(
    r"\bp\s*[<=>]\s*0?\.\d+\b|\b(?:confidence interval|standard deviation|"
    r"uncertainty|margin of error|standard error|sd)\b",
    re.I,
)


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in _TOKEN_PATTERN.findall(text.casefold())
        if token not in _STOP_WORDS and len(token) > 1
    }


def _claim_records(paper: dict, paper_id: str) -> list[dict]:
    analysis = paper.get("analysis")
    if not isinstance(analysis, dict):
        return []

    records = analysis.get("claim_records")
    if isinstance(records, list):
        normalized_records = [
            {
                "text": record["text"],
                "category": record.get("category", "unknown"),
                "section": record.get("section"),
                "page": record.get("page"),
                "paper_id": paper_id,
            }
            for record in records
            if isinstance(record, dict)
            and isinstance(record.get("text"), str)
            and record["text"].strip()
        ][:10]
        if normalized_records:
            return normalized_records

    legacy_claims = analysis.get("claims")
    if not isinstance(legacy_claims, list):
        return []
    return [
        {
            "text": claim.strip(),
            "category": "unknown",
            "section": None,
            "page": None,
            "paper_id": paper_id,
        }
        for claim in legacy_claims[:10]
        if isinstance(claim, str) and claim.strip()
    ]


def _classify_claim_pair(first: dict, second: dict) -> dict | None:
    first_words = _tokens(first["text"])
    second_words = _tokens(second["text"])
    shared_words = first_words & second_words
    if not shared_words:
        return None

    first_outcomes = first_words & _MEASURED_OUTCOMES
    second_outcomes = second_words & _MEASURED_OUTCOMES
    shared_outcomes = first_outcomes & second_outcomes
    first_positive = first_words & _POSITIVE_OUTCOMES
    second_positive = second_words & _POSITIVE_OUTCOMES
    first_negative = first_words & _NEGATIVE_OUTCOMES
    second_negative = second_words & _NEGATIVE_OUTCOMES
    first_negated = bool(_NEGATION_PATTERN.search(first["text"]))
    second_negated = bool(_NEGATION_PATTERN.search(second["text"]))

    if shared_outcomes and (first_positive or first_negative) and (
        second_positive or second_negative
    ):
        direction_conflict = bool(
            (first_positive and second_negative)
            or (first_negative and second_positive)
        )
        negation_conflict = first_negated != second_negated
        if direction_conflict or negation_conflict:
            status = "potential_conflict"
            explanation = (
                "The claims share measured-outcome terms but use opposing "
                "direction or negation cues. This lexical heuristic does not "
                "verify a scientific contradiction."
            )
        else:
            status = "supporting"
            explanation = (
                "The claims share measured-outcome terms and have matching "
                "lexical direction. This does not independently validate "
                "either study."
            )
    elif (
        first_outcomes
        and second_outcomes
        and not shared_outcomes
        and len(shared_words) >= 1
    ):
        status = "complementary"
        explanation = (
            "The claims share topical terms but mention different measured "
            "outcomes; this lexical heuristic cannot establish that their "
            "evidence is methodologically comparable."
        )
    elif len(shared_words) >= 2:
        status = "insufficient_evidence"
        explanation = (
            "The claims share terms, but the available text does not provide "
            "enough matching outcome and direction evidence to classify their "
            "relationship."
        )
    else:
        return None

    return {
        "status": status,
        "confidence": "heuristic_low",
        "method": "lexical_heuristic",
        "shared_terms": sorted(shared_words),
        "explanation": explanation,
        "evidence": [first, second],
    }


def _paper_summary(paper: dict, paper_id: str) -> dict:
    metadata = paper.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    analysis = paper.get("analysis")
    analysis = analysis if isinstance(analysis, dict) else {}
    methodology = analysis.get("methodology")
    methodology = methodology if isinstance(methodology, dict) else {}
    evidence_score = analysis.get("evidence_score")
    evidence_score = evidence_score if isinstance(evidence_score, dict) else {}
    statistics = analysis.get("statistics")
    statistics = (
        [item for item in statistics if isinstance(item, str)]
        if isinstance(statistics, list)
        else []
    )
    claim_records = _claim_records(paper, paper_id)
    sections = paper.get("sections")
    sections = sections if isinstance(sections, dict) else {}
    limitation_section = sections.get("limitations")
    limitation_claims = [
        claim["text"]
        for claim in claim_records
        if claim["category"] == "limitation"
    ]
    if isinstance(limitation_section, str) and limitation_section.strip():
        limitation_claims.append(limitation_section.strip()[:2000])

    return {
        "paper_id": paper_id,
        "title": metadata.get("title") or paper.get("filename"),
        "year": metadata.get("year"),
        "study_context": {
            "methodology": methodology,
            "sample_size_signals": [
                item for item in statistics if _SAMPLE_SIZE_PATTERN.search(item)
            ],
            "reported_statistics": statistics,
            "uncertainty_signals": [
                item for item in statistics if _UNCERTAINTY_PATTERN.search(item)
            ],
            "limitations": limitation_claims[:5],
            "evidence_score": evidence_score,
        },
    }


def _compare_study_context(first_summary: dict, second_summary: dict) -> dict:
    first_context = first_summary["study_context"]
    second_context = second_summary["study_context"]
    fields = (
        "method_terms",
        "sample_size_signals",
        "reported_statistics",
        "uncertainty_signals",
        "limitations",
    )
    comparisons = {}
    for field in fields:
        if field == "method_terms":
            first_value = first_context["methodology"].get("method_terms", [])
            second_value = second_context["methodology"].get("method_terms", [])
        else:
            first_value = first_context[field]
            second_value = second_context[field]
        first_available = bool(first_value)
        second_available = bool(second_value)
        if not first_available or not second_available:
            status = "not_comparable"
        elif first_value == second_value:
            status = "reported_values_match"
        else:
            status = "reported_values_differ"
        comparisons[field] = {
            "status": status,
            "values_by_paper": {
                first_summary["paper_id"]: first_value,
                second_summary["paper_id"]: second_value,
            },
        }

    return {
        **comparisons,
        "interpretation": (
            "These are extracted-value comparisons only. Differences in "
            "methods, sample sizes, statistics, uncertainty, or limitations "
            "are not evidence of a contradiction."
        ),
    }


def _compare_paper_pair(
    first_id: str,
    first_paper: dict,
    second_id: str,
    second_paper: dict,
) -> dict:
    first_claims = _claim_records(first_paper, first_id)
    second_claims = _claim_records(second_paper, second_id)
    first_summary = _paper_summary(first_paper, first_id)
    second_summary = _paper_summary(second_paper, second_id)
    claim_comparisons = []

    for first_claim, second_claim in (
        (first_claim, second_claim)
        for first_claim in first_claims
        for second_claim in second_claims
    ):
        comparison = _classify_claim_pair(first_claim, second_claim)
        if comparison is not None:
            claim_comparisons.append(comparison)
            if len(claim_comparisons) == 5:
                break

    statuses = {item["status"] for item in claim_comparisons}
    if "potential_conflict" in statuses and "supporting" in statuses:
        status = "mixed"
        explanation = (
            "Some claim pairs have opposing lexical cues while others align; "
            "inspect each source pair and study context before drawing a conclusion."
        )
    elif "potential_conflict" in statuses:
        status = "potential_conflict"
        explanation = (
            "At least one claim pair has opposing lexical cues. This is a "
            "screening signal, not a verified contradiction."
        )
    elif "supporting" in statuses:
        status = "supporting"
        explanation = (
            "At least one claim pair has matching lexical direction; "
            "agreement does not establish independent validity."
        )
    elif "complementary" in statuses:
        status = "complementary"
        explanation = (
            "At least one claim pair mentions different measured outcomes "
            "within overlapping topic terms."
        )
    elif "insufficient_evidence" in statuses:
        status = "insufficient_evidence"
        explanation = (
            "Related claim text was found, but there is not enough comparable "
            "outcome evidence to classify the relationship."
        )
    elif first_claims and second_claims:
        status = "incomparable"
        explanation = (
            "No claim pair shared enough specific terms for this lexical "
            "screen to compare their findings."
        )
    else:
        status = "insufficient_evidence"
        explanation = (
            "One or both papers lack extracted claims needed for comparison."
        )

    return {
        "paper_ids": [first_id, second_id],
        "status": status,
        "confidence": "heuristic_low",
        "method": "lexical_heuristic",
        "explanation": explanation,
        "study_context_comparison": _compare_study_context(
            first_summary, second_summary
        ),
        "claim_comparisons": claim_comparisons,
    }


def _summary_statistics(paper_summaries: list[dict]) -> dict:
    year_values = [
        {"paper_id": paper["paper_id"], "year": paper["year"]}
        for paper in paper_summaries
        if isinstance(paper.get("year"), int)
        and not isinstance(paper.get("year"), bool)
    ]
    evidence_scores = [
        {
            "paper_id": paper["paper_id"],
            "score": score["score"],
            "label": score.get("label"),
        }
        for paper in paper_summaries
        for score in [paper["study_context"]["evidence_score"]]
        if isinstance(score.get("score"), (int, float))
        and not isinstance(score.get("score"), bool)
    ]
    method_term_papers = {}
    for paper in paper_summaries:
        terms = paper["study_context"]["methodology"].get("method_terms", [])
        if not isinstance(terms, list):
            continue
        for term in set(item for item in terms if isinstance(item, str)):
            method_term_papers.setdefault(term, set()).add(paper["paper_id"])

    scores = [item["score"] for item in evidence_scores]
    return {
        "paper_count": len(paper_summaries),
        "publication_years": {
            "available_count": len(year_values),
            "values": year_values,
        },
        "evidence_stability_scores": {
            "available_count": len(evidence_scores),
            "average": round(sum(scores) / len(scores), 1) if scores else None,
            "minimum": min(scores) if scores else None,
            "maximum": max(scores) if scores else None,
            "values": evidence_scores,
        },
        "method_term_counts": [
            {"term": term, "paper_count": len(paper_ids)}
            for term, paper_ids in sorted(method_term_papers.items())
        ],
    }


def compare_papers(papers: dict[str, dict]) -> dict:
    paper_ids = list(papers)
    paper_summaries = [
        _paper_summary(papers[paper_id], paper_id)
        for paper_id in paper_ids
    ]
    return {
        "papers": paper_summaries,
        "summary_statistics": _summary_statistics(paper_summaries),
        "comparisons": [
            _compare_paper_pair(
                first_id,
                papers[first_id],
                second_id,
                papers[second_id],
            )
            for first_id, second_id in combinations(paper_ids, 2)
        ],
        "limitations": [
            "Comparisons use lexical heuristics, not semantic models or "
            "independent scientific review.",
            "Study design, populations, methods, uncertainty, and limitations "
            "are reported only when extracted; they are not automatically "
            "controlled for in claim classification.",
            "Missing claims are insufficient evidence, not evidence that a "
            "finding is absent.",
        ],
    }
