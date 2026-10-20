"""Essay project: data model and prompt builders for each stage."""
import re
from dataclasses import asdict, dataclass, field
from typing import Callable, Iterator

from app.ai.ollama_client import OllamaClient
from app.ai.prompts import system_prompt, with_context
from app.storage.classes import now
from app.storage.index import Chunk

ESSAY_TYPES = ["Argumentative", "Analytical", "Expository", "Compare & contrast", "Narrative",
               "Research paper", "Reflection"]
STYLES = ["MLA", "APA", "Chicago"]
STAGES = ["thesis", "outline", "draft", "feedback", "citations"]


@dataclass
class EssayProject:
    title: str = "Untitled essay"
    prompt: str = ""
    rubric: str = ""
    essay_type: str = "Argumentative"
    length: str = "5 paragraphs"
    citation_style: str = "MLA"
    thesis: str = ""
    thesis_ideas: str = ""
    outline: str = ""
    draft: str = ""
    user_draft: str = ""
    feedback: str = ""
    citations: str = ""
    sources: list[str] = field(default_factory=list)  # selected source ids
    id: str = ""
    created: str = field(default_factory=now)
    updated: str = ""

    def to_dict(self) -> dict:
        self.updated = now()
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "EssayProject":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def brief(self) -> str:
        parts = [f"Assignment: {self.prompt.strip() or '(not given)'}",
                 f"Essay type: {self.essay_type}", f"Length: {self.length}",
                 f"Citation style: {self.citation_style}"]
        if self.rubric.strip():
            parts.append(f"Grading rubric:\n{self.rubric.strip()}")
        return "\n".join(parts)

    def search_query(self, extra: str = "") -> str:
        return f"{self.prompt} {self.thesis} {extra}".strip()[:1500]


def _msgs(task: str, user: str, learning: bool, chunks: list[Chunk]) -> list[dict]:
    return [{"role": "system", "content": system_prompt(learning, task)},
            {"role": "user", "content": with_context(user, chunks)}]


def thesis_messages(p: EssayProject, chunks, learning: bool) -> list[dict]:
    return _msgs("Help the student find a strong thesis.", (
        f"{p.brief()}\n\nOffer 4 distinct, arguable thesis statements for this assignment. For each give: "
        "the thesis (one or two sentences), why it works, and the best evidence from the source material "
        "(cited). Finish by recommending one and saying why."), learning, chunks)


def outline_messages(p: EssayProject, chunks, learning: bool) -> list[dict]:
    return _msgs("Build a structured essay outline.", (
        f"{p.brief()}\n\nThesis: {p.thesis.strip() or '(propose one first)'}\n\n"
        "Write a clear outline. Use top-level headings like '## I. Introduction', '## II. ...' and bullets "
        "beneath. Under each body section list the claim, the evidence to use with its [source citation], "
        "and the analysis point. Match the requested length and the rubric."), learning, chunks)


def feedback_messages(p: EssayProject, chunks, learning: bool) -> list[dict]:
    return _msgs("Give honest, constructive feedback on the student's own draft.", (
        f"{p.brief()}\n\nStudent's draft:\n\"\"\"\n{p.user_draft.strip()}\n\"\"\"\n\n"
        "Give feedback with these headings: Overall impression; Thesis & argument; Structure & flow; "
        "Use of evidence (check it against the source material and flag unsupported claims); "
        "Rubric fit (if a rubric was given); Grammar & style (quote 3-5 specific lines with fixes); "
        "Top 3 priorities to revise. Do not rewrite the whole essay."), learning, chunks)


def citation_messages(p: EssayProject, entries: list[dict], learning: bool) -> list[dict]:
    lines = []
    for e in entries:
        lines.append("- " + "; ".join(f"{k}: {v}" for k, v in e.items() if v))
    return _msgs(f"Format a {p.citation_style} reference list.", (
        f"Format these sources as a {p.citation_style} "
        f"{'Works Cited' if p.citation_style == 'MLA' else 'reference list'}, alphabetized. "
        "Use ONLY the details given. If a detail (author, date, publisher, URL) is missing, leave it out and "
        "add a short '(missing: ...)' note instead of inventing it.\n\n" + "\n".join(lines)), learning, [])


def split_outline(outline: str) -> list[str]:
    """Split an outline into top-level sections (headings, roman numerals or numbered lines)."""
    top = re.compile(r"^(#{1,3}\s+|\*\*|[IVXivx]+[.)]\s|\d+[.)]\s)")
    sections, cur = [], []
    for line in outline.splitlines():
        if top.match(line.strip()) and cur:
            sections.append("\n".join(cur).strip())
            cur = []
        cur.append(line)
    if cur:
        sections.append("\n".join(cur).strip())
    sections = [s for s in sections if s]
    return sections if len(sections) >= 2 else [outline.strip()]


def draft_stream(client: OllamaClient, model: str, options: dict, p: EssayProject,
                 retrieve: Callable[[str], list[Chunk]], learning: bool) -> Iterator[str]:
    """Write the essay one outline section at a time so smaller models stay coherent."""
    sections = split_outline(p.outline) if p.outline.strip() else [""]
    written = ""
    for i, section in enumerate(sections, 1):
        chunks = retrieve(f"{p.search_query()} {section[:400]}")
        position = ("This is the opening section, so begin with the introduction and end it with the thesis."
                    if i == 1 else "This is the closing section, so end with a strong conclusion."
                    if i == len(sections) else "This is a middle section.")
        user = (f"{p.brief()}\n\nThesis: {p.thesis.strip() or '(infer from the outline)'}\n\n"
                f"Full outline:\n{p.outline.strip() or '(none - plan it yourself)'}\n\n"
                f"Essay so far:\n{written[-3500:] or '(nothing yet)'}\n\n"
                f"Now write ONLY section {i} of {len(sections)} as polished prose paragraphs "
                f"(no outline bullets, no heading labels like 'Section {i}'):\n{section or 'the entire essay'}\n"
                f"{position} Weave in evidence from the source material with {p.citation_style} in-text citations.")
        msgs = _msgs("Write one section of the student's essay.", user, learning, chunks)
        piece = ""
        for text in client.chat_stream(model, msgs, options):
            piece += text
            yield text
        written += piece + "\n\n"
        if i < len(sections):
            yield "\n\n"
