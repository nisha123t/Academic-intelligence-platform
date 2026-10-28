import re


_STATISTIC_PATTERNS = [
    r"\bp\s*[<=>]\s*0?\.\d+\b",
    r"\b\d+(?:\.\d+)?\s*%",
    r"\b(?:n|sample size)\s*[=:]\s*\d+\b",
    r"\b(?:mean|average|median|standard deviation|sd|confidence interval)\b",
]

_CLAIM_MARKERS = re.compile(
    r"\b(?:we find|we found|results show|findings show|demonstrate|suggest|indicate|"
    r"associated with|significantly|significant effect)\b",
    re.I,
)

_GAP_MARKERS = re.compile(
    r"\b(?:future work|further research|remains unclear|little is known|limited research|"
    r"research gap|limitation|limitations|underexplored|has not been studied)\b",
    re.I,
)

_HYPOTHESIS_MARKERS = re.compile(
    r"\b(?:we hypothesize|our hypothesis|hypotheses?|we expect|we predict)\b",
    re.I,
)
_LIMITATION_MARKERS = re.compile(
    r"\b(?:limitations?|limited by|we acknowledge|constraint(?:s)?)\b",
    re.I,
)
_CAUSAL_MARKERS = re.compile(
    r"\b(?:caus(?:e|es|ed|ing)|causal(?:ly)?|leads? to|led to|"
    r"results? in|resulted in|effect of|impact of)\b",
    re.I,
)
_CORRELATION_MARKERS = re.compile(
    r"\b(?:associated with|correlat(?:ed|ion)|relationship between|linked to)\b",
    re.I,
)


def _sentences(text: str) -> list[str]:
    return [
        re.sub(r"\s+", " ", sentence).strip()
        for sentence in re.split(r"(?<=[.!?])\s+", text)
        if sentence.strip()
    ]


def _matching_sentences(text: str, marker: re.Pattern[str]) -> list[str]:
    matches = []
    for sentence in _sentences(text):
        if marker.search(sentence):
            matches.append(sentence)
    return matches[:10]


def extract_statistics(text: str) -> list[str]:
    marker = re.compile("|".join(_STATISTIC_PATTERNS), re.I)
    return _matching_sentences(text, marker)


def _normalized_text(text: str) -> str:
    return " ".join(text.split()).casefold()


def _claim_classification(sentence: str) -> tuple[str, str]:
    for category, marker in (
        ("limitation", _LIMITATION_MARKERS),
        ("hypothesis", _HYPOTHESIS_MARKERS),
        ("causal", _CAUSAL_MARKERS),
        ("correlational", _CORRELATION_MARKERS),
        ("finding", _CLAIM_MARKERS),
    ):
        match = marker.search(sentence)
        if match:
            return category, match.group(0)
    return "finding", ""


def extract_claim_records(
    text: str,
    sections: dict[str, str],
    pages: list[dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    records = []
    source_sections = [
        (name, content) for name, content in sections.items() if content.strip()
    ] or [(None, text)]
    seen_sentences = set()

    for section_name, content in source_sections:
        for sentence in _sentences(content):
            if not any(
                marker.search(sentence)
                for marker in (
                    _CLAIM_MARKERS,
                    _HYPOTHESIS_MARKERS,
                    _LIMITATION_MARKERS,
                )
            ):
                continue

            normalized_sentence = _normalized_text(sentence)
            if normalized_sentence in seen_sentences:
                continue
            seen_sentences.add(normalized_sentence)
            page = next(
                (
                    page_data.get("page_number")
                    for page_data in pages or []
                    if normalized_sentence in _normalized_text(
                        str(page_data.get("text", ""))
                    )
                ),
                None,
            )
            category, classification_basis = _claim_classification(sentence)
            records.append(
                {
                    "text": sentence,
                    "category": category,
                    "classification_basis": classification_basis,
                    "classification_reason": (
                        "Heuristically classified from wording marker "
                        f"'{classification_basis}'; this does not "
                        "verify the scientific finding."
                    ),
                    "section": (
                        section_name if section_name != "unknown" else None
                    ),
                    "page": page,
                }
            )
            if len(records) == 10:
                return records

    return records


def extract_methodology(sections: dict[str, str]) -> dict[str, object]:
    methodology = sections.get("methodology", "")
    sentences = _sentences(methodology)
    lower_text = methodology.lower()

    method_terms = [
        term for term in [
            "qualitative", "quantitative", "survey", "experiment", "interview",
            "case study", "regression", "classification", "dataset", "participants",
        ]
        if term in lower_text
    ]

    return {
        "available": bool(methodology.strip()),
        "method_terms": method_terms,
        "summary": " ".join(sentences[:3]),
    }


def calculate_evidence_score(
    statistics: list[str], methodology: dict[str, object], claims: list[str]
) -> dict[str, object]:
    factors = [
        {
            "name": "base",
            "points": 25,
            "applied": True,
            "reason": "Fixed starting value for the heuristic score.",
        },
        {
            "name": "reported_statistics",
            "points": 30,
            "applied": bool(statistics),
            "reason": "At least one statistical signal was extracted."
            if statistics
            else "No statistical signal was extracted.",
        },
        {
            "name": "methodology_section",
            "points": 25,
            "applied": bool(methodology["available"]),
            "reason": "A methodology section was extracted."
            if methodology["available"]
            else "No methodology section was extracted.",
        },
        {
            "name": "method_terms",
            "points": 10,
            "applied": bool(methodology["method_terms"]),
            "reason": "At least one recognized method term was found."
            if methodology["method_terms"]
            else "No recognized method term was found.",
        },
        {
            "name": "claim_signals",
            "points": 10,
            "applied": bool(claims),
            "reason": "At least one claim marker was detected."
            if claims
            else "No claim marker was detected.",
        },
    ]
    raw_score = sum(
        factor["points"] for factor in factors if factor["applied"]
    )
    score = min(raw_score, 100)
    label = "high" if score >= 75 else "moderate" if score >= 50 else "low"
    return {
        "score": score,
        "label": label,
        "score_type": "evidence_stability_heuristic",
        "factors": factors,
        "normalization": {
            "formula": "min(100, sum of applied factor points)",
            "raw_score": raw_score,
            "applied_score": score,
            "label_thresholds": {
                "low": "0-49",
                "moderate": "50-74",
                "high": "75-100",
            },
        },
        "limitations": (
            "This heuristic measures detected reporting signals, not "
            "scientific validity, study quality, or calibrated confidence."
        ),
    }


def analyze_paper(
    text: str,
    sections: dict[str, str],
    pages: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    statistics = extract_statistics(text)
    methodology = extract_methodology(sections)
    claims = _matching_sentences(text, _CLAIM_MARKERS)
    claim_records = extract_claim_records(text, sections, pages)
    research_gaps = _matching_sentences(text, _GAP_MARKERS)
    evidence_score = calculate_evidence_score(statistics, methodology, claims)

    return {
        "statistics": statistics,
        "methodology": methodology,
        "evidence_score": evidence_score,
        "claims": claims,
        "claim_records": claim_records,
        "research_gaps": research_gaps,
    }