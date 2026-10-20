"""Essay help: thesis -> outline -> draft -> feedback -> works cited."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLineEdit,
                               QPlainTextEdit, QPushButton, QSplitter, QTabWidget, QVBoxLayout, QWidget)

from app.ai.ollama_client import OllamaError
from app.export.docx_export import export_text
from app.tools import essay as E
from app.ui.common import ClassContext, ContextPicker, StreamBox, error_box, label, primary, run_task


class EssayPage(QWidget):
    def __init__(self, ctx: ClassContext, project: E.EssayProject | None = None, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.project = project or E.EssayProject(citation_style=ctx.store.load_info().citation_style)
        lay = QVBoxLayout(self)
        lay.addWidget(label("Essay help", "title"))
        split = QSplitter(Qt.Horizontal)
        lay.addWidget(split, 1)

        # ---- left: assignment + sources
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 8, 0)
        box = QGroupBox("Assignment")
        form = QFormLayout(box)
        self.title = QLineEdit()
        self.title.setPlaceholderText("Essay title / nickname")
        self.prompt = QPlainTextEdit()
        self.prompt.setPlaceholderText("Paste the assignment prompt...")
        self.prompt.setMinimumHeight(90)
        self.rubric = QPlainTextEdit()
        self.rubric.setPlaceholderText("Paste the grading rubric (optional)")
        self.rubric.setMaximumHeight(80)
        self.etype = QComboBox()
        self.etype.addItems(E.ESSAY_TYPES)
        self.length = QLineEdit()
        self.length.setPlaceholderText("e.g. 5 paragraphs, 1000 words")
        self.style = QComboBox()
        self.style.addItems(E.STYLES)
        for lab, w in (("Title", self.title), ("Prompt", self.prompt), ("Rubric", self.rubric),
                       ("Type", self.etype), ("Length", self.length), ("Citations", self.style)):
            form.addRow(lab, w)
        ll.addWidget(box)
        self.picker = ContextPicker(ctx)
        ll.addWidget(self.picker, 1)
        split.addWidget(left)

        # ---- right: stages
        self.tabs = QTabWidget()
        self.thesis = StreamBox("Brainstorm thesis ideas", "Thesis options appear here. Edit freely, "
                                "then paste the one you choose into the box below.")
        self.thesis_pick = QLineEdit()
        self.thesis_pick.setPlaceholderText("Your chosen thesis (used by the outline and draft)")
        t1 = QWidget()
        l1 = QVBoxLayout(t1)
        l1.addWidget(self.thesis, 1)
        l1.addWidget(self.thesis_pick)
        self.outline = StreamBox("Build outline", "Your outline appears here and stays editable.")
        self.draft = StreamBox("Write full draft", "A draft is written section by section from your outline.")
        self.feedback = StreamBox("Get feedback", "Feedback on your draft appears here.")
        self.user_draft = QPlainTextEdit()
        self.user_draft.setPlaceholderText("Paste your own draft here (or load a file)...")
        load = QPushButton("Load draft from file...")
        load.clicked.connect(self.load_draft)
        t4 = QWidget()
        l4 = QVBoxLayout(t4)
        l4.addWidget(load, 0, Qt.AlignLeft)
        sp = QSplitter(Qt.Vertical)
        sp.addWidget(self.user_draft)
        sp.addWidget(self.feedback)
        l4.addWidget(sp, 1)
        self.cites = StreamBox("Format works cited", "Select sources on the left and fill in their citation "
                               "details in the Library, then generate your reference list.")
        for w, name in ((t1, "1. Thesis"), (self.outline, "2. Outline"), (self.draft, "3. Draft"),
                        (t4, "4. Feedback"), (self.cites, "5. Works cited")):
            self.tabs.addTab(w, name)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(8, 0, 0, 0)
        rl.addWidget(self.tabs, 1)
        bar = QHBoxLayout()
        self.saved = label("", "muted")
        save = QPushButton("Save to history")
        save.clicked.connect(self.save)
        export = primary("Export...")
        export.clicked.connect(self.export)
        bar.addWidget(self.saved, 1)
        bar.addWidget(save)
        bar.addWidget(export)
        rl.addLayout(bar)
        split.addWidget(right)
        split.setStretchFactor(1, 3)

        self.thesis.btn.clicked.connect(self.gen_thesis)
        self.outline.btn.clicked.connect(self.gen_outline)
        self.draft.btn.clicked.connect(self.gen_draft)
        self.feedback.btn.clicked.connect(self.gen_feedback)
        self.cites.btn.clicked.connect(self.gen_cites)
        for sb in (self.thesis, self.outline, self.draft, self.feedback, self.cites):
            sb.on_done = lambda _t: self.save()
        self.load_project(self.project)

    # ---- project <-> form ----------------------------------------------
    def load_project(self, p: E.EssayProject) -> None:
        self.project = p
        self.title.setText(p.title if p.id else "")
        self.prompt.setPlainText(p.prompt)
        self.rubric.setPlainText(p.rubric)
        self.etype.setCurrentText(p.essay_type)
        self.length.setText(p.length)
        self.style.setCurrentText(p.citation_style)
        self.thesis.set_text(p.thesis_ideas)
        self.thesis_pick.setText(p.thesis)
        self.outline.set_text(p.outline)
        self.draft.set_text(p.draft)
        self.user_draft.setPlainText(p.user_draft)
        self.feedback.set_text(p.feedback)
        self.cites.set_text(p.citations)
        if p.sources:
            self.picker.set_selected(p.sources)

    def collect(self) -> E.EssayProject:
        p = self.project
        p.title = self.title.text().strip() or p.title or "Untitled essay"
        p.prompt, p.rubric = self.prompt.toPlainText(), self.rubric.toPlainText()
        p.essay_type, p.length, p.citation_style = self.etype.currentText(), self.length.text(), self.style.currentText()
        p.thesis, p.thesis_ideas = self.thesis_pick.text().strip(), self.thesis.text()
        p.outline, p.draft, p.citations = self.outline.text(), self.draft.text(), self.cites.text()
        p.user_draft, p.feedback = self.user_draft.toPlainText(), self.feedback.text()
        p.sources = self.picker.selected_ids()
        return p

    def save(self) -> None:
        p = self.collect()
        store = self.ctx.store
        if not p.id:
            p.id = store.new_history_id("essay", p.title)
        store.save_history("essay", p.id, p.to_dict())
        self.saved.setText(f"Saved to history as {p.id}")
        text = "\n\n".join(x for x in (p.outline, p.draft, p.user_draft) if x.strip())
        k = self.ctx.knowledge
        run_task(self, lambda _t: k.add_history("essay", p.id, p.title, text), None, lambda _m: None)

    # ---- generation ------------------------------------------------------
    def _opts(self):
        k = self.ctx.knowledge
        return self.ctx.client, self.ctx.settings.chat_model, k.chat_options(), self.ctx.settings.learning_mode

    def _retriever(self, p: E.EssayProject, ids: list[str]):
        return lambda query, k=6: self.ctx.knowledge.retrieve(query, ids, k)

    def _need_prompt(self) -> bool:
        if not self.prompt.toPlainText().strip():
            error_box(self, "Paste the assignment prompt first.", "Need a prompt")
            return True
        return False

    def gen_thesis(self):
        if self._need_prompt():
            return
        p, ids = self.collect(), self.picker.selected_ids()
        client, model, opts, learn = self._opts()
        retrieve = self._retriever(p, ids)
        self.thesis.start(lambda: client.chat_stream(
            model, E.thesis_messages(p, retrieve(p.search_query()), learn), opts))

    def gen_outline(self):
        if self._need_prompt():
            return
        p, ids = self.collect(), self.picker.selected_ids()
        client, model, opts, learn = self._opts()
        retrieve = self._retriever(p, ids)
        self.outline.start(lambda: client.chat_stream(
            model, E.outline_messages(p, retrieve(p.search_query(), 8), learn), opts))

    def gen_draft(self):
        if self._need_prompt():
            return
        p, ids = self.collect(), self.picker.selected_ids()
        client, model, opts, learn = self._opts()
        retrieve = self._retriever(p, ids)
        self.draft.start(lambda: E.draft_stream(client, model, opts, p, retrieve, learn))

    def gen_feedback(self):
        p = self.collect()
        if not p.user_draft.strip():
            error_box(self, "Paste your own draft in the top box first.", "No draft to review")
            return
        ids = self.picker.selected_ids()
        client, model, opts, learn = self._opts()
        retrieve = self._retriever(p, ids)
        self.feedback.start(lambda: client.chat_stream(
            model, E.feedback_messages(p, retrieve(p.user_draft[:1500], 6), learn), opts))

    def gen_cites(self):
        p = self.collect()
        meta = self.ctx.store.load_metadata()
        names = [i[4:] for i in p.sources if i.startswith("lib:")]
        if not names:
            error_box(self, "Select at least one library source on the left.", "No sources")
            return
        entries = [{"source file": n, **meta.get(n, {})} for n in names]
        client, model, opts, learn = self._opts()
        self.cites.start(lambda: client.chat_stream(model, E.citation_messages(p, entries, learn), opts))

    # ---- misc --------------------------------------------------------------
    def load_draft(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load your draft", "", "Documents (*.txt *.md *.docx)")
        if not path:
            return
        try:
            from app.convert import convert_file
            self.user_draft.setPlainText(convert_file(path))
        except Exception as e:
            error_box(self, str(e))

    def export(self):
        p = self.collect()
        stage = self.tabs.currentIndex()
        text = [p.thesis_ideas, p.outline, p.draft, p.user_draft + "\n\n" + p.feedback, p.citations][stage].strip()
        if not text:
            error_box(self, "There's nothing in this tab to export yet.", "Nothing to export")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export", f"{p.title}.docx",
                                              "Word document (*.docx);;Markdown (*.md);;Text (*.txt)")
        if path:
            try:
                export_text(p.title, text, Path(path))
            except Exception as e:
                error_box(self, str(e), "Export failed")
