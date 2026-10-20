"""Practice quizzes, grading, question explanations, flashcards and study guides."""
from dataclasses import asdict, dataclass, field
from typing import Callable

from app.ai.ollama_client import OllamaClient, OllamaError, parse_json
from app.ai.prompts import format_context, system_prompt, with_context
from app.storage.classes import now
from app.storage.index import Chunk

QUESTION_TYPES = {"multiple_choice": "Multiple choice", "true_false": "True / false",
                  "short_answer": "Short answer"}
DIFFICULTIES = ["Easy", "Medium", "Hard"]

QUIZ_SCHEMA = {
    "type": "object",
    "properties": {"questions": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "type": {"type": "string", "enum": list(QUESTION_TYPES)},
            "question": {"type": "string"},
            "choices": {"type": "array", "items": {"type": "string"}},
            "answer": {"type": "string"},
            "explanation": {"type": "string"},
            "source": {"type": "string"},
        },
        "required": ["type", "question", "answer", "explanation"]}}},
    "required": ["questions"],
}
GRADE_SCHEMA = {"type": "object", "properties": {"correct": {"type": "boolean"}, "feedback": {"type": "string"}},
                "required": ["correct", "feedback"]}
CARDS_SCHEMA = {"type": "object", "properties": {"cards": {"type": "array", "items": {
    "type": "object", "properties": {"front": {"type": "string"}, "back": {"type": "string"}},
    "required": ["front", "back"]}}}, "required": ["cards"]}


@dataclass
class Question:
    type: str
    question: str
    answer: str
    choices: list[str] = field(default_factory=list)
    explanation: str = ""
    source: str = ""
    user_answer: str = ""
    correct: bool | None = None
    feedback: str = ""


@dataclass
class Quiz:
    title: str
    questions: list[Question]
    id: str = ""
    created: str = field(default_factory=now)
    updated: str = ""
    sources: list[str] = field(default_factory=list)
    score: float | None = None

    def to_dict(self) -> dict:
        self.updated = now()
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Quiz":
        qs = [Question(**{k: v for k, v in q.items() if k in Question.__dataclass_fields__})
              for q in d.get("questions", [])]
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__ and k != "questions"}, questions=qs)

    def text_for_index(self) -> str:
        return "\n\n".join(f"Q: {q.question}\nA: {q.answer}\n{q.explanation}" for q in self.questions)

    def missed(self) -> list[Question]:
        return [q for q in self.questions if q.correct is False]


def normalize_question(raw: dict) -> Question | None:
    """Clean one model-produced question; returns None if unusable."""
    qtype = raw.get("type")
    text = str(raw.get("question", "")).strip()
    answer = str(raw.get("answer", "")).strip()
    if qtype not in QUESTION_TYPES or not text or not answer:
        return None
    choices = [str(c).strip() for c in raw.get("choices") or [] if str(c).strip()]
    if qtype == "true_false":
        choices = ["True", "False"]
        answer = "True" if answer.lower().startswith("t") else "False"
    elif qtype == "multiple_choice":
        if len(choices) < 2:
            return None
        letters = {chr(65 + i): c for i, c in enumerate(choices)}
        key = answer.strip().rstrip(".)").upper()
        if key in letters:
            answer = letters[key]
        elif answer not in choices:
            match = [c for c in choices if c.lower() == answer.lower()]
            if not match:
                return None
            answer = match[0]
    else:
        choices = []
    return Question(qtype, text, answer, choices, str(raw.get("explanation", "")).strip(),
                    str(raw.get("source", "")).strip())


def generate_quiz(client: OllamaClient, model: str, options: dict, chunks: list[Chunk], n: int,
                  types: list[str], difficulty: str, learning: bool, title: str = "Practice quiz") -> Quiz:
    type_names = ", ".join(QUESTION_TYPES[t] for t in types)
    user = (f"Write a {difficulty.lower()} practice quiz of {n + 2} questions using ONLY the source material. "
            f"Question types to use (mix them): {type_names}. For multiple choice give 4 choices and set "
            "'answer' to the exact text of the correct choice. For true/false set 'answer' to 'True' or 'False'. "
            "For short answer, 'answer' is a model answer in one or two sentences. Every question needs a "
            "short 'explanation' and a 'source' naming where in the material it came from. "
            "Respond as JSON matching the schema.")
    msgs = [{"role": "system", "content": system_prompt(learning, "Write quiz questions.")},
            {"role": "user", "content": with_context(user, chunks)}]
    last_err: Exception | None = None
    for _ in range(2):  # one retry if the JSON comes back unusable
        try:
            data = parse_json(client.chat(model, msgs, options, fmt=QUIZ_SCHEMA))
            raw_list = data.get("questions", []) if isinstance(data, dict) else data
            questions = [q for q in (normalize_question(r) for r in raw_list if isinstance(r, dict)) if q]
            questions = [q for q in questions if q.type in types][:n]
            if questions:
                return Quiz(title=title, questions=questions)
            last_err = OllamaError("The AI didn't produce any usable questions.")
        except OllamaError as e:
            last_err = e
    raise last_err or OllamaError("Quiz generation failed.")


def grade_question(client: OllamaClient, model: str, options: dict, q: Question) -> Question:
    ua = q.user_answer.strip()
    if not ua:
        q.correct, q.feedback = False, "No answer given."
    elif q.type in ("multiple_choice", "true_false"):
        q.correct = ua.lower() == q.answer.lower()
        q.feedback = "Correct!" if q.correct else f"The correct answer is: {q.answer}"
    else:
        msgs = [{"role": "system", "content": "You grade short student answers fairly and briefly."},
                {"role": "user", "content": (
                    f"Question: {q.question}\nModel answer: {q.answer}\nStudent answer: {ua}\n\n"
                    "Mark correct if the student's answer captures the key idea, even if worded differently. "
                    "Give one or two sentences of feedback. Respond as JSON.")}]
        try:
            res = client.chat_json(model, msgs, GRADE_SCHEMA, options)
            q.correct = bool(res.get("correct"))
            q.feedback = str(res.get("feedback", "")).strip()
        except OllamaError as e:
            q.correct, q.feedback = None, f"Couldn't auto-grade ({e}). Model answer: {q.answer}"
    return q


def grade_quiz(client: OllamaClient, model: str, options: dict, quiz: Quiz,
               report: Callable[[str], None] | None = None) -> Quiz:
    for i, q in enumerate(quiz.questions, 1):
        if report:
            report(f"Grading {i}/{len(quiz.questions)}...")
        grade_question(client, model, options, q)
    graded = [q for q in quiz.questions if q.correct is not None]
    quiz.score = round(100 * sum(q.correct for q in graded) / len(graded), 1) if graded else None
    return quiz


def explain_messages(question: str, chunks: list[Chunk], learning: bool) -> list[dict]:
    user = (f"Student's question:\n{question.strip()}\n\n"
            "Answer it, then explain the concept behind it step by step so the student could solve a similar "
            "question alone. Use the source material where it applies and cite it. If the source material "
            "doesn't cover the question, say so and answer from general knowledge, clearly labelled.")
    return [{"role": "system", "content": system_prompt(learning, "Explain a question.")},
            {"role": "user", "content": with_context(user, chunks)}]


def generate_flashcards(client: OllamaClient, model: str, options: dict, chunks: list[Chunk],
                        n: int, learning: bool) -> list[dict]:
    user = (f"Make {n} flashcards covering the most important terms, concepts and facts in the source material. "
            "'front' is a short prompt or term; 'back' is a concise answer (1-3 sentences). Respond as JSON.")
    msgs = [{"role": "system", "content": system_prompt(learning, "Write flashcards.")},
            {"role": "user", "content": with_context(user, chunks)}]
    data = parse_json(client.chat(model, msgs, options, fmt=CARDS_SCHEMA))
    cards = data.get("cards", []) if isinstance(data, dict) else data
    out = [{"front": str(c["front"]).strip(), "back": str(c["back"]).strip()}
           for c in cards if isinstance(c, dict) and c.get("front") and c.get("back")]
    if not out:
        raise OllamaError("The AI didn't produce any usable flashcards.")
    return out[:n]


def study_guide_messages(chunks: list[Chunk], learning: bool) -> list[dict]:
    user = ("Write a study guide from the source material with these sections: Key terms (with definitions), "
            "Main concepts (short explanations), Important details/dates/formulas, Common mistakes to avoid, "
            "and 5 self-test questions. Use Markdown headings and bullets and cite sources.")
    return [{"role": "system", "content": system_prompt(learning, "Write a study guide.")},
            {"role": "user", "content": with_context(user, chunks)}]
