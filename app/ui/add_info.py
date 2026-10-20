"""Add files / pasted text to a class library (used before essays and quizzes, and by the Library page)."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QLineEdit, QListWidget, QPlainTextEdit,
                               QProgressBar, QPushButton, QVBoxLayout)

from app.convert import SUPPORTED, convert_file, file_dialog_filter
from app.ui.common import ClassContext, error_box, label, primary, run_task


class AddInfoDialog(QDialog):
    """Drop files or paste text; they're converted and indexed into the class library."""

    def __init__(self, ctx: ClassContext, heading: str, can_skip: bool = True, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.added: list[str] = []
        self._files: list[Path] = []
        self.setWindowTitle("Add to library")
        self.setMinimumSize(520, 520)
        self.setAcceptDrops(True)
        lay = QVBoxLayout(self)
        lay.addWidget(label(heading, "h2"))
        lay.addWidget(label("Add anything that might help: lecture slides, notes, readings, a recording, a "
                            "photo of the board, the assignment sheet. Drag files here or use the buttons. "
                            "Everything is saved in this class's library for next time.", "muted"))
        self.file_list = QListWidget()
        self.file_list.setMaximumHeight(110)
        lay.addWidget(self.file_list)
        row = QHBoxLayout()
        pick = QPushButton("Choose files...")
        pick.clicked.connect(self.pick_files)
        clear = QPushButton("Clear")
        clear.clicked.connect(self._clear)
        row.addWidget(pick)
        row.addWidget(clear)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addWidget(label("...or paste text (notes, an article, the assignment):"))
        self.paste_name = QLineEdit()
        self.paste_name.setPlaceholderText("Name for the pasted text, e.g. Chapter 3 notes")
        self.paste = QPlainTextEdit()
        lay.addWidget(self.paste_name)
        lay.addWidget(self.paste, 1)
        self.status = label("", "muted")
        self.bar = QProgressBar()
        self.bar.setVisible(False)
        lay.addWidget(self.status)
        lay.addWidget(self.bar)
        buttons = QHBoxLayout()
        self.skip = QPushButton("Skip" if can_skip else "Cancel")
        self.skip.clicked.connect(self.reject)
        self.go = primary("Add & continue")
        self.go.clicked.connect(self.start)
        buttons.addStretch(1)
        buttons.addWidget(self.skip)
        buttons.addWidget(self.go)
        lay.addLayout(buttons)

    # ---- drag and drop ------------------------------------------------
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        self._add_paths([Path(u.toLocalFile()) for u in e.mimeData().urls() if u.isLocalFile()])

    def pick_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Choose files", "", file_dialog_filter())
        self._add_paths([Path(p) for p in paths])

    def _add_paths(self, paths: list[Path]) -> None:
        for p in paths:
            if p.is_file() and p.suffix.lower() in SUPPORTED and p not in self._files:
                self._files.append(p)
                self.file_list.addItem(p.name)
            elif p.is_file() and p.suffix.lower() not in SUPPORTED:
                error_box(self, f"{p.name}: this file type isn't supported yet.", "Skipped")

    def _clear(self):
        self._files.clear()
        self.file_list.clear()

    # ---- work ---------------------------------------------------------
    def start(self) -> None:
        text, name = self.paste.toPlainText().strip(), self.paste_name.text().strip() or "Pasted notes"
        files = list(self._files)
        if not files and not text:
            self.accept()
            return
        k, whisper = self.ctx.knowledge, self.ctx.settings.whisper_model
        self.go.setEnabled(False)
        self.skip.setEnabled(False)
        self.bar.setVisible(True)
        self.bar.setRange(0, 0)

        def work(task):
            added = []
            for p in files:
                task.report(f"Converting {p.name}...")
                body = convert_file(p, whisper, lambda m: task.report(f"{p.name}: {m}"), lambda: task.cancelled)
                if body.strip():
                    task.report(f"Indexing {p.name}...")
                    added.append(k.add_to_library(p.stem, body, p))
            if text:
                task.report(f"Indexing {name}...")
                added.append(k.add_to_library(name, text))
            return added

        def done(added):
            self.added = added
            self.accept()

        def failed(msg):
            self.go.setEnabled(True)
            self.skip.setEnabled(True)
            self.bar.setVisible(False)
            error_box(self, msg, "Couldn't add everything")

        run_task(self, work, done, failed, lambda m: self.status.setText(str(m)))
