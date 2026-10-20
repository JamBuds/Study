"""Convert slides, documents, transcripts, recordings and images to plain text."""
from pathlib import Path

SLIDES = {".pptx"}
PDF = {".pdf"}
WORD = {".docx"}
CAPTIONS = {".srt", ".vtt", ".txt", ".md"}
AUDIO_VIDEO = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac", ".mp4", ".mkv", ".mov", ".webm", ".avi"}
IMAGES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
SUPPORTED = SLIDES | PDF | WORD | CAPTIONS | AUDIO_VIDEO | IMAGES


def file_dialog_filter() -> str:
    exts = " ".join(f"*{e}" for e in sorted(SUPPORTED))
    return f"Supported files ({exts});;All files (*)"


def convert_file(path, whisper_model: str = "base", report=None, cancelled=lambda: False) -> str:
    """Return plain text for any supported file. Raises ValueError for unsupported types."""
    path = Path(path)
    ext = path.suffix.lower()
    if ext in SLIDES:
        from app.convert.slides import convert_pptx
        return convert_pptx(path)
    if ext in PDF:
        from app.convert.pdf import convert_pdf
        return convert_pdf(path, report, cancelled)
    if ext in WORD:
        from app.convert.word import convert_docx
        return convert_docx(path)
    if ext in CAPTIONS:
        from app.convert.captions import convert_captions
        return convert_captions(path)
    if ext in AUDIO_VIDEO:
        from app.convert.media import transcribe
        return transcribe(path, whisper_model, report, cancelled)
    if ext in IMAGES:
        from app.convert.ocr import ocr_image
        if report:
            report("Reading text from image...")
        return ocr_image(path)
    raise ValueError(f"Unsupported file type: {ext or path.name}")
