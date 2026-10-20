"""Optional AI pass that fixes punctuation/paragraphing of raw transcripts."""
from app.ai.ollama_client import OllamaClient

PIECE_CHARS = 3000
PROMPT = (
    "Fix punctuation, capitalization and paragraph breaks in the transcript below. "
    "Do NOT summarize, reword, add or remove content. Output only the corrected text."
)


def _pieces(text: str):
    cur = ""
    for para in text.split("\n\n"):
        if cur and len(cur) + len(para) > PIECE_CHARS:
            yield cur
            cur = ""
        cur = f"{cur}\n\n{para}" if cur else para
    if cur:
        yield cur


def ai_cleanup(client: OllamaClient, model: str, text: str, report=None, cancelled=lambda: False) -> str:
    pieces = list(_pieces(text))
    out = []
    for i, piece in enumerate(pieces, 1):
        if cancelled():
            out.append(piece)
            continue
        if report:
            report(f"AI cleanup {i}/{len(pieces)}...")
        fixed = client.chat(model, [{"role": "system", "content": PROMPT},
                                    {"role": "user", "content": piece}], {"temperature": 0.1})
        out.append(fixed.strip() or piece)
    return "\n\n".join(out)
