import re


SECTION_ALIASES = {
    "abstract": ["abstract", "a b s t r a c t"],
    "introduction": ["introduction", "intro"],
    "related work": ["related work", "literature review", "related literature"],
    "methodology": ["methodology", "method", "methods", "materials and methods", "material and methods"],
    "results": ["results", "findings", "experimental results"],
    "discussion": ["discussion", "interpretation"],
    "limitations": ["limitations", "study limitations"],
    "conclusion": ["conclusion", "conclusions"],
    "references": ["references", "reference list", "bibliography"],
    "keywords": ["keywords"],
}


def _normalize_section_label(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
    return " ".join(normalized.split())


def _collapsed_letters(value: str) -> str:
    return re.sub(r"[^a-z]", "", value.lower())


def detect_sections(text: str):
    sections = {"unknown": []}
    current_section = "unknown"

    lines = [line.strip() for line in text.splitlines() if line.strip()]

    for line in lines:
        normalized = _normalize_section_label(line)
        collapsed = _collapsed_letters(normalized)

        matched_section = None

        for canonical, aliases in SECTION_ALIASES.items():
            alias_values = [
                _normalize_section_label(alias)
                for alias in aliases
            ]

            if normalized in alias_values or collapsed in [
                _collapsed_letters(alias) for alias in alias_values
            ]:
                matched_section = canonical
                break

        if matched_section is None:
            if re.fullmatch(r"(?:[a-z]\s+){5,}[a-z]", normalized):
                collapsed = re.sub(r"\s+", "", normalized)
                for canonical, aliases in SECTION_ALIASES.items():
                    if collapsed in [_collapsed_letters(alias) for alias in aliases]:
                        matched_section = canonical
                        break

        if matched_section:
            current_section = matched_section
            sections.setdefault(current_section, [])
            sections[current_section] = []
        else:
            sections.setdefault(current_section, [])
            sections[current_section].append(line)

    for section_name in list(sections):
        sections[section_name] = "\n".join(sections[section_name]).strip()

    return {k: v for k, v in sections.items() if v or k == "unknown"}
