"""Quiz help: practice quizzes, explain-a-question, flashcards and study guides."""
import random
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
                               QPlainTextEdit, QPushButton, QRadioButton, QScrollArea, QSpinBox, QSplitter,
                               QTabWidget, QVBoxLayout, QWidget)

from app.export.docx_export import export_text
from app.tools import quiz as Q
from app.ui.common import (ClassContext, ContextPicker, StreamBox, card, error_box, label, primary, run_task)
from app.ui.theme import palette


class QuestionCard(QWidget):
    def __init__(self, index: int, q: Q.Question):
        super().__init__()
        self.q = q
        box = card()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 8)
        outer.addWidget(box)
        lay = QVBoxLayout(box)
        lay.addWidget(label(f"{index}. {q.question}", "h2"))
        self.group = None
        self.radios: list[QRadioButton] = []
        self.text = None
        if q.type in ("multiple_choice", "true_false"):
            self.group = QButtonGroup(self)
            for c in q.choices:
                r = QRadioButton(c)
                self.group.addButton(r)
                self.radios.append(r)
                lay.addWidget(r)
        else:
            self.text = QPlainTextEdit()
            self.text.setMaximumHeight(80)
            self.text.setPlaceholderText("Your answer...")
            lay.addWidget(self.text)
        self.result = label("")
        self.result.setVisible(False)
        lay.addWidget(self.result)

    def read_answer(self) -> str:
        if self.text is not None:
            return self.text.toPlainText().strip()
        for r in self.radios:
            if r.isChecked():
                return r.text()
        return ""

    def lock(self, theme: str) -> None:
        p = palette(theme)
        for w in (*self.radios, self.text):
            if w is not None:
                w.setEnabled(False)
        q = self.q
        colour = p["good"] if q.correct else p["bad"] if q.correct is False else p["muted"]
        verdict = "Correct" if q.correct else "Not quite" if q.correct is False else "Ungraded"
        extra = f"<br>{q.explanation}" if q.explanation else ""
        src = f"<br><i>Source: {q.source}</i>" if q.source else ""
        self.result.setText(f"<b style='color:{colour}'>{verdict}.</b> {q.feedback}{extra}{src}")
        self.result.setVisible(True)


class PracticeTab(QWidget):
    def __init__(self, page: "QuizPage"):
        super().__init__()
        self.page, self.ctx = page, page.ctx
        self.quiz: Q.Quiz | None = None
        self.cards: list[QuestionCard] = []
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        self.count = QSpinBox()
        self.count.setRange(3, 30)
        self.count.setValue(8)
        self.types = {t: QCheckBox(name) for t, name in Q.QUESTION_TYPES.items()}
        for cb in self.types.values():
            cb.setChecked(True)
        self.diff = QComboBox()
        self.diff.addItems(Q.DIFFICULTIES)
        self.diff.setCurrentText("Medium")
        self.gen = primary("Generate quiz")
        self.gen.clicked.connect(self.generate)
        row.addWidget(QLabel("Questions"))
        row.addWidget(self.count)
        for cb in self.types.values():
            row.addWidget(cb)
        row.addWidget(self.diff)
        row.addStretch(1)
        row.addWidget(self.gen)
        lay.addLayout(row)
        self.status = label("", "muted")
        lay.addWidget(self.status)
        self.holder = QWidget()
        self.holder_lay = QVBoxLayout(self.holder)
        self.holder_lay.setAlignment(Qt.AlignTop)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.holder)
        lay.addWidget(scroll, 1)
        bar = QHBoxLayout()
        self.submit = primary("Submit answers")
        self.submit.clicked.connect(self.grade)
        self.submit.setVisible(False)
        self.review = QPushButton("Review missed questions")
        self.review.clicked.connect(self.review_missed)
        self.review.setVisible(False)
        self.retake = QPushButton("Retake")
        self.retake.clicked.connect(lambda: self.show_quiz(self.quiz, reset=True))
        self.retake.setVisible(False)
        bar.addStretch(1)
        for b in (self.retake, self.review, self.submit):
            bar.addWidget(b)
        lay.addLayout(bar)

    # ---- building ---------------------------------------------------------
    def _clear(self):
        while self.holder_lay.count():
            self.holder_lay.takeAt(0).widget().deleteLater()
        self.cards = []

    def show_quiz(self, quiz: Q.Quiz, reset: bool = False, only: list[Q.Question] | None = None) -> None:
        self.quiz = quiz
        if reset:
            for q in quiz.questions:
                q.user_answer, q.correct, q.feedback = "", None, ""
            quiz.score = None
        self._clear()
        graded = any(q.correct is not None for q in quiz.questions)
        for i, q in enumerate(only or quiz.questions, 1):
            c = QuestionCard(i, q)
            if graded:
                c.lock(self.ctx.settings.theme)
            self.holder_lay.addWidget(c)
            self.cards.append(c)
        self.submit.setVisible(not graded)
        self.retake.setVisible(graded)
        self.review.setVisible(graded and bool(quiz.missed()) and only is None)
        if graded and quiz.score is not None:
            self.status.setText(f"Score: {quiz.score:.0f}%  ({len(quiz.questions) - len(quiz.missed())} of "
                                f"{len(quiz.questions)} correct)")
        elif not graded:
            self.status.setText(f"{quiz.title} - answer the questions, then submit.")

    def review_missed(self):
        self.show_quiz(self.quiz, only=self.quiz.missed())

    # ---- actions ----------------------------------------------------------
    def generate(self):
        types = [t for t, cb in self.types.items() if cb.isChecked()]
        if not types:
            error_box(self, "Pick at least one question type.")
            return
        ids = self.page.picker.selected_ids()
        if not ids:
            error_box(self, "Select at least one source on the left so the quiz has material to draw from.",
                      "No sources")
            return
        k, c, s = self.ctx.knowledge, self.ctx.client, self.ctx.settings
        n, diff = self.count.value(), self.diff.currentText()
        self.gen.setEnabled(False)
        self.status.setText("Generating quiz... (this can take a minute)")

        def work(_t):
            chunks = k.sample(ids)
            if not chunks:
                raise Q.OllamaError("The selected sources are empty.")
            quiz = Q.generate_quiz(c, s.chat_model, k.chat_options(), chunks, n, types, diff, s.learning_mode,
                                   title=f"{diff} quiz ({n} questions)")
            quiz.sources = ids
            return quiz

        def done(quiz):
            self.gen.setEnabled(True)
            self.save(quiz)
            self.show_quiz(quiz)

        def failed(msg):
            self.gen.setEnabled(True)
            self.status.setText("")
            error_box(self, msg)

        run_task(self, work, done, failed)

    def grade(self):
        quiz = self.quiz
        for card_ in self.cards:
            card_.q.user_answer = card_.read_answer()
        self.submit.setEnabled(False)
        self.status.setText("Grading...")
        c, s, k = self.ctx.client, self.ctx.settings, self.ctx.knowledge

        def work(task):
            return Q.grade_quiz(c, s.chat_model, k.chat_options(), quiz, task.report)

        def done(q):
            self.submit.setEnabled(True)
            self.save(q)
            self.show_quiz(q)

        def failed(msg):
            self.submit.setEnabled(True)
            self.status.setText("")
            error_box(self, msg)

        run_task(self, work, done, failed, lambda m: self.status.setText(str(m)))

    def save(self, quiz: Q.Quiz) -> None:
        store, k = self.ctx.store, self.ctx.knowledge
        if not quiz.id:
            quiz.id = store.new_history_id("quiz", quiz.title)
        store.save_history("quiz", quiz.id, quiz.to_dict())
        run_task(self, lambda _t: k.add_history("quiz", quiz.id, quiz.title, quiz.text_for_index()),
                 None, lambda _m: None)


class ExplainTab(QWidget):
    def __init__(self, page: "QuizPage"):
        super().__init__()
        self.page, self.ctx = page, page.ctx
        lay = QVBoxLayout(self)
        lay.addWidget(label("Paste a question from your homework or study guide:"))
        self.question = QPlainTextEdit()
        self.question.setMaximumHeight(110)
        lay.addWidget(self.question)
        self.out = StreamBox("Explain it", "The explanation appears here.")
        self.out.btn.clicked.connect(self.explain)
        lay.addWidget(self.out, 1)

    def explain(self):
        q = self.question.toPlainText().strip()
        if not q:
            error_box(self, "Paste a question first.", "No question")
            return
        ids = self.page.picker.selected_ids()
        k, c, s = self.ctx.knowledge, self.ctx.client, self.ctx.settings

        def stream():
            chunks = k.retrieve(q, ids)
            return c.chat_stream(s.chat_model, Q.explain_messages(q, chunks, s.learning_mode), k.chat_options())

        self.out.start(stream)


class FlashcardsTab(QWidget):
    def __init__(self, page: "QuizPage"):
        super().__init__()
        self.page, self.ctx = page, page.ctx
        self.cards: list[dict] = []
        self.pos, self.flipped = 0, False
        self.deck_id = ""
        self.deck_title = "Flashcards"
        lay = QVBoxLayout(self)
        tabs = QTabWidget()
        lay.addWidget(tabs)

        cards_tab = QWidget()
        cl = QVBoxLayout(cards_tab)
        row = QHBoxLayout()
        self.count = QSpinBox()
        self.count.setRange(5, 50)
        self.count.setValue(15)
        self.gen = primary("Generate flashcards")
        self.gen.clicked.connect(self.generate)
        row.addWidget(QLabel("Cards"))
        row.addWidget(self.count)
        row.addStretch(1)
        row.addWidget(self.gen)
        cl.addLayout(row)
        self.status = label("", "muted")
        cl.addWidget(self.status)
        self.face = QPushButton("Generate or open a deck to start studying")
        self.face.setObjectName("tile")
        self.face.setMinimumHeight(200)
        self.face.setStyleSheet("font-size: 20px; text-align: center;")
        self.face.clicked.connect(self.flip)
        cl.addWidget(self.face, 1)
        nav = QHBoxLayout()
        self.counter = label("", "muted")
        prev, nxt, shuf = QPushButton("< Previous"), QPushButton("Next >"), QPushButton("Shuffle")
        prev.clicked.connect(lambda: self.move(-1))
        nxt.clicked.connect(lambda: self.move(1))
        shuf.clicked.connect(self.shuffle)
        nav.addWidget(prev)
        nav.addWidget(nxt)
        nav.addWidget(shuf)
        nav.addStretch(1)
        nav.addWidget(self.counter)
        cl.addLayout(nav)
        tabs.addTab(cards_tab, "Flashcards")

        self.guide = StreamBox("Write study guide", "A study guide built from the selected sources.")
        self.guide.btn.clicked.connect(self.make_guide)
        export = QPushButton("Export guide...")
        export.clicked.connect(self.export_guide)
        guide_tab = QWidget()
        gl = QVBoxLayout(guide_tab)
        gl.addWidget(self.guide, 1)
        gl.addWidget(export, 0, Qt.AlignRight)
        tabs.addTab(guide_tab, "Study guide")

    # ---- deck ---------------------------------------------------------------
    def open_deck(self, data: dict) -> None:
        self.cards = data.get("cards", [])
        self.deck_id, self.deck_title = data.get("id", ""), data.get("title", "Flashcards")
        self.pos, self.flipped = 0, False
        self.render()

    def render(self) -> None:
        if not self.cards:
            return
        c = self.cards[self.pos]
        self.face.setText(c["back"] if self.flipped else c["front"])
        self.counter.setText(f"{self.pos + 1} / {len(self.cards)}  -  click the card to flip")

    def flip(self):
        self.flipped = not self.flipped
        self.render()

    def move(self, step: int):
        if self.cards:
            self.pos, self.flipped = (self.pos + step) % len(self.cards), False
            self.render()

    def shuffle(self):
        random.shuffle(self.cards)
        self.pos, self.flipped = 0, False
        self.render()

    def generate(self):
        ids = self.page.picker.selected_ids()
        if not ids:
            error_box(self, "Select at least one source on the left.", "No sources")
            return
        k, c, s, n = self.ctx.knowledge, self.ctx.client, self.ctx.settings, self.count.value()
        self.gen.setEnabled(False)
        self.status.setText("Making flashcards...")

        def work(_t):
            return Q.generate_flashcards(c, s.chat_model, k.chat_options(), k.sample(ids), n, s.learning_mode)

        def done(cards):
            self.gen.setEnabled(True)
            self.status.setText(f"Made {len(cards)} cards.")
            store = self.ctx.store
            title = f"Flashcards ({len(cards)} cards)"
            hid = store.new_history_id("flashcards", title)
            data = {"id": hid, "title": title, "cards": cards, "sources": ids}
            from app.storage.classes import now
            store.save_history("flashcards", hid, {**data, "created": now()})
            run_task(self, lambda _t: k.add_history("flashcards", hid, title,
                                                    "\n".join(f"{x['front']}: {x['back']}" for x in cards)),
                     None, lambda _m: None)
            self.open_deck(data)

        def failed(msg):
            self.gen.setEnabled(True)
            self.status.setText("")
            error_box(self, msg)

        run_task(self, work, done, failed)

    def make_guide(self):
        ids = self.page.picker.selected_ids()
        if not ids:
            error_box(self, "Select at least one source on the left.", "No sources")
            return
        k, c, s = self.ctx.knowledge, self.ctx.client, self.ctx.settings
        self.guide.start(lambda: c.chat_stream(
            s.chat_model, Q.study_guide_messages(k.sample(ids, 14000), s.learning_mode), k.chat_options()))

    def export_guide(self):
        text = self.guide.text().strip()
        if not text:
            error_box(self, "Generate a study guide first.", "Nothing to export")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export study guide", "Study guide.docx",
                                              "Word document (*.docx);;Markdown (*.md);;Text (*.txt)")
        if path:
            try:
                export_text("Study guide", text, Path(path))
            except Exception as e:
                error_box(self, str(e), "Export failed")


class QuizPage(QWidget):
    def __init__(self, ctx: ClassContext, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        lay = QVBoxLayout(self)
        lay.addWidget(label("Quiz help", "title"))
        split = QSplitter(Qt.Horizontal)
        lay.addWidget(split, 1)
        self.picker = ContextPicker(ctx)
        self.picker.setMinimumWidth(240)
        split.addWidget(self.picker)
        self.tabs = QTabWidget()
        self.practice = PracticeTab(self)
        self.explain = ExplainTab(self)
        self.flash = FlashcardsTab(self)
        self.tabs.addTab(self.practice, "Practice quiz")
        self.tabs.addTab(self.explain, "Explain a question")
        self.tabs.addTab(self.flash, "Flashcards & study guide")
        split.addWidget(self.tabs)
        split.setStretchFactor(1, 4)

    def open_quiz(self, quiz: Q.Quiz) -> None:
        self.tabs.setCurrentWidget(self.practice)
        self.practice.show_quiz(quiz)

    def open_flashcards(self, data: dict) -> None:
        self.tabs.setCurrentWidget(self.flash)
        self.flash.open_deck(data)
