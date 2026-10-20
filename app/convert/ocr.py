"""Text from images (OCR) using RapidOCR (downloads nothing extra; models ship with the package)."""
_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        try:
            from rapidocr import RapidOCR
        except ImportError as e:  # e.g. a Windows Application Control policy blocking a DLL
            raise RuntimeError(f"Reading text from images isn't available on this PC ({e}).") from e
        _engine = RapidOCR()
    return _engine


def ocr_image(image) -> str:
    """image: file path (str/Path), bytes, or numpy array."""
    if hasattr(image, "__fspath__"):
        image = str(image)
    result = _get_engine()(image)
    texts = getattr(result, "txts", None)
    if texts is None and isinstance(result, tuple):  # older API: (list of [box, text, score], elapsed)
        texts = [r[1] for r in (result[0] or [])]
    return "\n".join(texts or [])
