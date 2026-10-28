import re

from app.services.cross_paper_analyzer import compare_papers


_NORMALIZE_PATTERN = re.compile(r"\s+")
_FUTURE_WORK_PATTERN = re.compile(
    r"\b(?:future work|further research|future research|should be studied|"
    r"should investigate|should examine|should compare|warrants further study)\b",
    re.I,
)
_LIMITATION_PATTERN = re.compile(
    r"\b(?:limitation|limitations|limited by|constraint|constraints|"
    r"we acknowledge|caution should be exercised)\b",
    re.I,
)
_UNDEREXPLORED_PATTERN = re.compile(
    r"\b(?:underexplored|under-explored|little is known|remains unclear|"
    r"limited research|has not been studied|have not been studied|"
    r"few studies|lack of research|research gap|not compared|"
    r"have not been compared|no comparison|lack of comparison|"
    r"comparisons? (?:were not|was not|have not been) made|"
    r"comparison.{0,80}(?:not made|not performed|not conducted))\b",
    re.I,
)
_DEFAULT_SCORE_WEIGHTS = {
    "explicit_limitation_or_future_work": 40,
    "explicit_underexplored_statement": 25,
    "inconsistent_findings_signal": 30,
    "additional_evidence_paper": 15,
    "maximum_recurrence_points": 30,
}


def _normalize(text: str) -> str:
    return _NORMALIZE_PATTERN.sub(" ", text).strip().casefold()


def _gap_type(text: str) -> str | None:
    if _FUTURE_WORK_PATTERN.search(text):
        return "future_research"
    if _LIMITATION_PATTERN.search(text):
        return "author_reported_limitation"
    if _UNDEREXPLORED_PATTERN.search(text):
        return "author_reported_underexplored_area"
    return None


def _statement_evidence(papers: dict[str, dict]) -> list[dict]:
    evidence_by_key = {}
    for paper_id, paper in papers.items():
        analysis = paper.get("analysis")
        analysis = analysis if isinstance(analysis, dict) else {}
        sections = paper.get("sections")
        sections = sections if isinstance(sections, dict) else {}
        claim_records = analysis.get("claim_records")
        claim_records = claim_records if isinstance(claim_records, list) else []
        statements = []

        for record in claim_records:
            if not isinstance(record, dict) or not isinstance(record.get("text"), str):
                continue
            text = record["text"].strip()
            if _gap_type(text):
                statements.append((text, record.get("section"), record.get("page")))

        for section_name, section_text in sections.items():
            if not isinstance(section_text, str):
                continue
            for sentence in re.split(r"(?<=[.!?])\s+", section_text):
                text = sentence.strip()
                if _gap_type(text):
                    statements.append((text, section_name, None))

        research_gaps = analysis.get("research_gaps")
        if isinstance(research_gaps, list):
            for text in research_gaps:
                if not isinstance(text, str) or not _gap_type(text):
                    continue
                matching_claim = next(
                    (
                        claim
                        for claim in claim_records
                        if isinstance(claim, dict)
                        and isinstance(claim.get("text"), str)
                        and _normalize(claim["text"]) == _normalize(text)
                    ),
                    {},
                )
                matching_section = next(
                    (
                        name
                        for name, content in sections.items()
                        if isinstance(content, str)
                        and _normalize(text) in _normalize(content)
                    ),
                    None,
                )
                statements.append(
                    (
                        text.strip(),
                        matching_claim.get("section") or matching_section,
                        matching_claim.get("page"),
                    )
                )

        seen_in_paper = set()
        for text, section, page in statements:
            category = _gap_type(text)
            normalized_text = _normalize(text)
            key = (category, normalized_text)
            if not category or key in seen_in_paper:
                continue
            seen_in_paper.add(key)
            evidence_by_key.setdefault(key, []).append(
                {
                    "paper_id": paper_id,
                    "text": text,
                    "section": section,
                    "page": page,
                    "source_type": "author_statement",
                }
            )

    return [
        {
            "type": category,
            "statement": statements[0]["text"],
            "evidence": statements,
        }
        for (category, _), statements in evidence_by_key.items()
    ]


def _inconsistent_finding_evidence(papers: dict[str, dict]) -> list[dict]:
    if len(papers) < 2:
        return []

    comparisons = compare_papers(papers)["comparisons"]
    evidence_by_key = {}
    for comparison in comparisons:
        for claim_pair in comparison["claim_comparisons"]:
            if claim_pair["status"] != "potential_conflict":
                continue
            evidence = claim_pair["evidence"]
            if len(evidence) != 2:
                continue
            pair_key = tuple(sorted(
                (
                    (item["paper_id"], _normalize(item["text"]))
                    for item in evidence
                )
            ))
            evidence_by_key.setdefault(
                pair_key,
                {
                    "type": "potentially_inconsistent_findings",
                    "statement": (
                        "These claim excerpts have opposing lexical cues and "
                        "may warrant contextual follow-up; they are not a "
                        "verified contradiction."
                    ),
                    "evidence": [
                        {
                            **item,
                            "source_type": "claim_pair_screening_signal",
                        }
                        for item in evidence
                    ],
                },
            )

    return list(evidence_by_key.values())


def _score_gap(gap: dict, weights: dict[str, int]) -> dict:
    is_conflict = gap["type"] == "potentially_inconsistent_findings"
    is_underexplored = gap["type"] == "author_reported_underexplored_area"
    base_factor = (
        "inconsistent_findings_signal"
        if is_conflict
        else (
            "explicit_underexplored_statement"
            if is_underexplored
            else "explicit_limitation_or_future_work"
        )
    )
    base_points = weights[base_factor]
    distinct_papers = len({item["paper_id"] for item in gap["evidence"]})
    recurrence_points = min(
        max(distinct_papers - 1, 0) * weights["additional_evidence_paper"],
        weights["maximum_recurrence_points"],
    )
    factors = [
        {
            "name": base_factor,
            "points": base_points,
            "reason": (
                "A source paper explicitly states this limitation, future "
                "research direction, or underexplored area."
                if not is_conflict
                else "A claim-pair lexical screen flagged opposing cues for review."
            ),
            "evidence_paper_ids": sorted(
                {item["paper_id"] for item in gap["evidence"]}
            ),
        }
    ]
    if distinct_papers > 1:
        factors.append(
            {
                "name": "additional_evidence_paper",
                "points": recurrence_points,
                "reason": (
                    f"The signal appears across {distinct_papers} selected papers; "
                    "this is recurrence in the supplied set, not corpus-wide prevalence."
                ),
                "evidence_paper_ids": sorted(
                    {item["paper_id"] for item in gap["evidence"]}
                ),
            }
        )
    score = min(max(base_points + recurrence_points, 0), 100)
    if is_conflict:
        identification_reason = (
            "Flagged by lexical screening for opposing cues in the cited claim "
            "excerpts; this is not a verified contradiction."
        )
    else:
        marker = (
            _FUTURE_WORK_PATTERN
            if gap["type"] == "future_research"
            else (
                _LIMITATION_PATTERN
                if gap["type"] == "author_reported_limitation"
                else _UNDEREXPLORED_PATTERN
            )
        )
        match = marker.search(gap["statement"])
        matched_phrase = match.group(0) if match else "an author-statement marker"
        identification_reason = (
            f"Classified as {gap['type'].replace('_', ' ')} because the cited "
            f"source statement contains '{matched_phrase}'. This rule-based "
            "screen does not independently validate the research need."
        )
    return {
        **gap,
        "identification_reason": identification_reason,
        "opportunity_score": score,
        "score_label": "heuristic",
        "confidence": "heuristic_low",
        "score_factors": factors,
    }


def detect_research_gaps(
    papers: dict[str, dict],
    score_weights: dict[str, int] | None = None,
) -> dict:
    weights = dict(_DEFAULT_SCORE_WEIGHTS)
    if score_weights is not None:
        unknown_weights = set(score_weights) - set(weights)
        if unknown_weights:
            raise ValueError(f"Unknown opportunity score weights: {sorted(unknown_weights)}")
        for name, value in score_weights.items():
            if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 100:
                raise ValueError(f"Opportunity score weight '{name}' must be an integer from 0 to 100.")
            weights[name] = value

    candidates = _statement_evidence(papers) + _inconsistent_finding_evidence(papers)
    gaps = [
        _score_gap(candidate, weights)
        for candidate in candidates
    ]
    gaps.sort(
        key=lambda item: (
            -item["opportunity_score"],
            item["type"],
            _normalize(item["statement"]),
        )
    )
    return {
        "paper_ids": list(papers),
        "gaps": gaps,
        "scoring": {
            "label": "heuristic",
            "weights": weights,
            "formula": (
                "base evidence points + up to 30 recurrence points from "
                "additional distinct papers, capped to 0–100"
            ),
            "limitations": [
                "Scores prioritize explicit source statements and repeated "
                "signals within only the selected papers; they are not "
                "probabilities or validated measures of research value.",
                "Potentially inconsistent findings are lexical screening "
                "signals, not verified contradictions.",
                "No gap is inferred merely because a topic or comparison is "
                "absent from the selected papers.",
            ],
        },
    }
