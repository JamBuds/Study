"""Audio/video -> text with faster-whisper (runs locally; model downloads on first use)."""
PARAGRAPH_GAP_SECONDS = 2.0
PARAGRAPH_MAX_CHARS = 500


def transcribe(path, model_size: str = "base", report=None, cancelled=lambda: False) -> str:
    from faster_whisper import WhisperModel

    if report:
        report(f"Loading Whisper '{model_size}' model (first use downloads it)...")
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, info = model.transcribe(str(path), vad_filter=True)
    paragraphs, cur, last_end = [], "", 0.0
    for seg in segments:
        if cancelled():
            break
        text = seg.text.strip()
        if cur and (seg.start - last_end > PARAGRAPH_GAP_SECONDS or len(cur) > PARAGRAPH_MAX_CHARS):
            paragraphs.append(cur)
            cur = ""
        cur = f"{cur} {text}".strip()
        last_end = seg.end
        if report and info.duration:
            report(f"Transcribing... {min(99, int(100 * seg.end / info.duration))}%")
    if cur:
        paragraphs.append(cur)
    return "\n\n".join(paragraphs)
