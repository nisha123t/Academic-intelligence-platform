import fitz

from app.services.section_detector import detect_sections
from app.services.metadata_extractor import extract_metadata


def extract_pdf_content(pdf_path: str):
    document = fitz.open(pdf_path)

    pages = []
    all_text = []

    for page_number, page in enumerate(document, start=1):
        page_text = page.get_text("text")
        all_text.append(page_text)

        page_data = {
            "page_number": page_number,
            "text": page_text,
        }

        pages.append(page_data)

    document.close()

    full_text = "\n".join(all_text)
    sections = detect_sections(full_text)
    metadata = extract_metadata(full_text, sections)

    return {
        "text": full_text,
        "metadata": metadata,
        "sections": sections,
        "pages": pages
    }