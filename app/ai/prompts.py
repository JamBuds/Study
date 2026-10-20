"""Shared prompt pieces."""
from app.storage.index import Chunk

BASE = (
    "You are StudyBuddy, a patient, accurate study assistant for a student. "
    "Ground your answers in the SOURCE MATERIAL provided when it is relevant, and cite sources "
    "in square brackets like [Lecture 4 - Slide 12]. If the material doesn't cover something, say so "
    "plainly instead of guessing, and never invent quotes, facts, page numbers or references."
)

LEARNING = (
    " The student is in learning mode: briefly explain your reasoning and teach the underlying skill "
    "alongside the result, and finish with one or two things for the student to try themselves."
)


def system_prompt(learning_mode: bool, task: str = "") -> str:
    return BASE + (LEARNING if learning_mode else "") + (f"\n\nTask: {task}" if task else "")


def format_context(chunks: list[Chunk], empty: str = "(No source material was selected.)") -> str:
    if not chunks:
        return empty
    return "\n\n".join(f"[{c.citation}]\n{c.text}" for c in chunks)


def with_context(user_text: str, chunks: list[Chunk]) -> str:
    return f"SOURCE MATERIAL:\n{format_context(chunks)}\n\n---\n{user_text}"
