import fitz

from app.services.section_detector import detect_sections
from app.services.metadata_extractor import extract_metadata


def _collect_page_layout(page):
    layout_blocks = []
    page_dict = page.get_text("dict")

    for block in page_dict.get("blocks", []):
        if block.get("type") != 0:
            continue

        block_data = {
            "bbox": block.get("bbox"),
            "lines": []
        }

        for line in block.get("lines", []):
            line_data = {
                "bbox": line.get("bbox"),
                "text": "".join(span.get("text", "") for span in line.get("spans", [])),
                "spans": []
            }

            for span in line.get("spans", []):
                line_data["spans"].append({
                    "text": span.get("text", ""),
                    "bbox": span.get("bbox"),
                    "font": span.get("font"),
                    "size": span.get("size"),
                    "flags": span.get("flags")
                })

            block_data["lines"].append(line_data)

        if block_data["lines"]:
            layout_blocks.append(block_data)

    return layout_blocks


def extract_pdf_content(pdf_path: str):
    document = fitz.open(pdf_path)

    pages = []
    all_text = []

    for page_number, page in enumerate(document, start=1):
        page_text = page.get_text("text")
        all_text.append(page_text)

        page_data = {
            "page_number": page_number,
            "width": page.rect.width,
            "height": page.rect.height,
            "blocks": _collect_page_layout(page)
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