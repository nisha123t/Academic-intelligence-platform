import re


def extract_metadata(text: str, sections: dict):
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    title = extract_title(lines)
    authors = extract_authors(lines)
    year = extract_year(lines)
    doi = extract_doi(text)
    keywords = extract_keywords(lines)

    return {
        "title": title,
        "authors": authors,
        "year": year,
        "doi": doi,
        "keywords": keywords,
    }


def _is_probably_title(line: str) -> bool:
    if len(line) < 20 or len(line) > 250:
        return False

    lower = line.lower()
    if any(token in lower for token in [
        "doi:", "keywords:", "abstract", "introduction",
        "method", "results", "discussion", "references",
        "journal", "university", "department", "school",
        "science direct", "elsevier", "homepage"
    ]):
        return False

    if re.fullmatch(r"[A-Z0-9\s:;\-]+", line) and len(line.split()) <= 3:
        return False

    words = re.findall(r"\S+", line)
    if len(words) < 4:
        return False

    return True


def _is_journal_banner(line: str) -> bool:
    clean = re.sub(r"[^a-z0-9]+", " ", line.lower()).strip()
    if not clean:
        return True

    banner_terms = [
        "contents lists",
        "science direct",
        "sciencedirect",
        "journal homepage",
        "elsevier",
        "article info",
        "highlights",
        "keywords",
        "abstract",
        "introduction",
        "results",
        "discussion",
        "references",
        "applied energy",
        "department",
        "university",
        "school",
        "vol",
        "issue",
        "doi"
    ]

    return any(term in clean for term in banner_terms)


def extract_title(lines):
    if not lines:
        return None

    for index, line in enumerate(lines[:60]):
        clean = re.sub(r"\s+", " ", line).strip()
        if not clean or _is_journal_banner(clean):
            continue

        if _is_probably_title(clean):
            if index + 1 < len(lines[:60]):
                next_line = re.sub(r"\s+", " ", lines[index + 1]).strip()
                if next_line and not _is_journal_banner(next_line) and not _is_probably_title(next_line):
                    combined = f"{clean} {next_line}"
                    if len(combined.split()) >= 6:
                        return combined
            return clean

    for line in lines[:60]:
        clean = re.sub(r"\s+", " ", line).strip()
        if len(clean) > 20 and len(clean) < 300 and not _is_journal_banner(clean):
            return clean

    return None


def _clean_author_name(name: str):
    cleaned = name.strip().strip(".,;:()[]{}")
    cleaned = cleaned.replace("∗", "").replace("•", "")
    cleaned = re.sub(r"^(?:and|&)\s+", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+[a-zA-Z]\s*(?:iD)?$", "", cleaned)
    cleaned = re.sub(r"\s+[a-zA-Z]$", "", cleaned)
    cleaned = re.sub(r"\s+and\s+$", "", cleaned, flags=re.I)
    return cleaned.strip()


def extract_authors(lines):
    seen = set()

    for line in lines[:60]:
        if not line or len(line) > 300:
            continue

        lower = line.lower()
        if any(token in lower for token in [
            "journal", "department", "university", "school",
            "abstract", "introduction", "method", "results",
            "discussion", "references", "keywords", "doi",
            "contents lists", "science direct", "elsevier",
            "homepage", "applied energy"
        ]):
            continue

        if not re.search(r"[A-Z][a-z]", line):
            continue

        if re.search(r"\d", line):
            continue

        if line.count(" ") < 2:
            continue

        candidates = re.split(r"\s+and\s+|,\s*", line)
        authors = []

        for part in candidates:
            clean = _clean_author_name(part)
            if not clean:
                continue
            if len(clean.split()) < 2:
                continue
            if any(token in clean.lower() for token in [
                "university", "department", "school", "institute",
                "journal", "vol", "pp", "science", "elsevier",
                "sustainable", "green", "energy-aware", "client",
                "selection", "learning", "iot"
            ]):
                continue
            if clean not in seen:
                authors.append(clean)
                seen.add(clean)

        if len(authors) >= 2:
            return authors

    return []


def extract_year(lines):
    for line in lines[:50]:
        match = re.search(r"\b(19\d{2}|20\d{2})\b", line)
        if match:
            return int(match.group(1))

    text = "\n".join(lines)
    match = re.search(r"\b(19\d{2}|20\d{2})\b", text)
    if match:
        return int(match.group(1))

    return None


def extract_doi(text):
    pattern = r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b"
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        return match.group(0).rstrip(".,)")
    return None


def _normalized_header_name(value: str) -> str:
    return re.sub(r"[^a-z]", "", value.lower())


def extract_keywords(lines):
    for index, line in enumerate(lines):
        match = re.search(r"(?:^|\s)(keywords?)\s*[:\-]?\s*(.*)$", line, re.I)
        if not match:
            continue

        keyword_values = []
        remaining = match.group(2).strip()

        if remaining:
            parts = re.split(r"[,;]", remaining)
            keyword_values.extend(
                keyword.strip().strip(";,")
                for keyword in parts
                if keyword.strip()
            )

        cursor = index + 1
        while cursor < len(lines):
            candidate = lines[cursor].strip()
            if not candidate:
                cursor += 1
                continue

            candidate_header = _normalized_header_name(candidate)
            if candidate_header in {
                "abstract",
                "introduction",
                "relatedwork",
                "literaturereview",
                "method",
                "methodology",
                "methods",
                "materialsandmethods",
                "results",
                "discussion",
                "limitations",
                "conclusion",
                "conclusions",
                "references",
                "bibliography",
            }:
                break

            candidate_clean = candidate.strip("•- ")
            if candidate_clean:
                keyword_values.extend(
                    item.strip().strip(";,")
                    for item in re.split(r"[,;]", candidate_clean)
                    if item.strip()
                )

            cursor += 1

        cleaned = []
        seen = set()
        for keyword in keyword_values:
            normalized = re.sub(r"\s+", " ", keyword).strip()
            if not normalized:
                continue
            if normalized.lower() in seen:
                continue
            seen.add(normalized.lower())
            cleaned.append(normalized)

        if cleaned:
            return cleaned

    return []
