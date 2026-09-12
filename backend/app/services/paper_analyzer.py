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
    score = 25
    if statistics:
        score += 30
    if methodology["available"]:
        score += 25
    if methodology["method_terms"]:
        score += 10
    if claims:
        score += 10

    score = min(score, 100)
    label = "high" if score >= 75 else "moderate" if score >= 50 else "low"
    return {"score": score, "label": label}


def analyze_paper(text: str, sections: dict[str, str]) -> dict[str, object]:
    statistics = extract_statistics(text)
    methodology = extract_methodology(sections)
    claims = _matching_sentences(text, _CLAIM_MARKERS)
    research_gaps = _matching_sentences(text, _GAP_MARKERS)
    evidence_score = calculate_evidence_score(statistics, methodology, claims)

    return {
        "statistics": statistics,
        "methodology": methodology,
        "evidence_score": evidence_score,
        "claims": claims,
        "research_gaps": research_gaps,
    }