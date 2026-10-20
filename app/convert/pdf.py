"""PDF -> plain text, falling back to OCR for scanned pages."""
import fitz  # pymupdf

MIN_TEXT_CHARS = 20


def convert_pdf(path, report=None, cancelled=lambda: False) -> str:
    parts = []
    with fitz.open(str(path)) as doc:
        total = len(doc)
        for i, page in enumerate(doc, 1):
            if cancelled():
                break
            if report:
                report(f"Reading page {i} of {total}")
            text = page.get_text().strip()
            if len(text) < MIN_TEXT_CHARS:  # scanned page: render and OCR
                from app.convert.ocr import ocr_image
                if report:
                    report(f"Running OCR on page {i} of {total}")
                text = ocr_image(page.get_pixmap(dpi=200).tobytes("png")) or text
            parts.append(f"[Page {i}]\n{text}")
    return "\n\n".join(parts)
