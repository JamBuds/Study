"""Caption (.srt/.vtt) and raw transcript cleanup."""
import re

_TIMESTAMP = re.compile(r"^\s*(?:\d{1,2}:)?\d{1,2}:\d{2}(?:[.,]\d{1,3})?\s*(?:-->.*)?$")
_INLINE_STAMP = re.compile(r"^\s*[\[(]?(?:\d{1,2}:)?\d{1,2}:\d{2}(?::\d{2})?[\])]?\s+")
_TAG = re.compile(r"<[^>]+>|\{\\[^}]*\}")
_CUE_NUMBER = re.compile(r"^\d+$")
LINES_PER_PARAGRAPH = 6


def clean_captions(raw: str) -> str:
    lines: list[str] = []
    skip_block = False
    for line in raw.replace("﻿", "").splitlines():
        s = line.strip()
        if not s:
            skip_block = False
            continue
        if skip_block or s.upper().startswith(("WEBVTT", "STYLE", "REGION")) or s.startswith("NOTE"):
            skip_block = s.startswith(("NOTE", "STYLE", "REGION"))
            continue
        if _TIMESTAMP.match(s) or _CUE_NUMBER.match(s):
            continue
        s = _INLINE_STAMP.sub("", _TAG.sub("", s)).strip()
        if s and (not lines or lines[-1] != s):  # auto-captions repeat lines
            lines.append(s)
    paragraphs = [" ".join(lines[i:i + LINES_PER_PARAGRAPH]) for i in range(0, len(lines), LINES_PER_PARAGRAPH)]
    return "\n\n".join(paragraphs)


def convert_captions(path) -> str:
    raw = open(path, "r", encoding="utf-8", errors="replace").read()
    return clean_captions(raw)
