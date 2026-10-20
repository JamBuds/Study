"""Shared UI helpers and widgets."""
from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QFrame, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget)

from app.ai.ollama_client import OllamaClient
from app.ai.workers import StreamWorker, TaskWorker
from app.config import Settings
from app.knowledge import Knowledge
from app.storage.classes import ClassStore


@dataclass
class ClassContext:
    store: ClassStore
    knowledge: Knowledge
    client: OllamaClient
    settings: Settings
    shell: object  # ClassShell (navigation); typed loosely to avoid an import cycle


def label(text: str, name: str = "", wrap: bool = True) -> QLabel:
    lab = QLabel(text)
    if name:
        lab.setObjectName(name)
    lab.setWordWrap(wrap)
    return lab


def primary(text: str) -> QPushButton:
    b = QPushButton(text)
    b.setObjectName("primary")
    return b


def card() -> QFrame:
    f = QFrame()
    f.setObjectName("card")
    return f


def error_box(parent, message: str, title: str = "Something went wrong") -> None:
    QMessageBox.warning(parent, title, message)


def run_task(owner: QWidget, fn: Callable, on_result: Callable | None = None,
             on_error: Callable[[str], None] | None = None,
             on_progress: Callable | None = None) -> TaskWorker:
    w = TaskWorker(fn, owner)
    if on_result:
        w.result.connect(on_result)
    w.failed.connect(on_error or (lambda m: error_box(owner, m)))
    if on_progress:
        w.progress.connect(on_progress)
    w.start()
    return w


class StreamBox(QWidget):
    """A text area plus Generate/Stop buttons that streams a model reply into it."""

    def __init__(self, generate_text="Generate", placeholder="", parent=None):
        super().__init__(parent)
        self.edit = QPlainTextEdit()
        self.edit.setPlaceholderText(placeholder)
        self.btn = primary(generate_text)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setVisible(False)
        self.status = label("", "muted")
        row = QHBoxLayout()
        row.addWidget(self.btn)
        row.addWidget(self.stop_btn)
        row.addWidget(self.status, 1)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(row)
        lay.addWidget(self.edit, 1)
        self._worker: StreamWorker | None = None
        self.stop_btn.clicked.connect(self.stop)
        self.on_done: Callable[[str], None] | None = None

    @property
    def busy(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def text(self) -> str:
        return self.edit.toPlainText()

    def set_text(self, text: str) -> None:
        self.edit.setPlainText(text)

    def start(self, make_stream: Callable) -> None:
        if self.busy:
            return
        self.edit.clear()
        self.btn.setEnabled(False)
        self.stop_btn.setVisible(True)
        self.status.setText("Thinking...")
        w = StreamWorker(make_stream, self)
        w.chunk.connect(self._on_chunk)
        w.done.connect(self._on_done)
        w.failed.connect(self._on_failed)
        self._worker = w
        w.start()

    def stop(self) -> None:
        if self._worker:
            self._worker.cancel()
            self.status.setText("Stopping...")

    def _on_chunk(self, piece: str) -> None:
        self.status.setText("Writing...")
        self.edit.moveCursor(self.edit.textCursor().MoveOperation.End)
        self.edit.insertPlainText(piece)
        self.edit.ensureCursorVisible()

    def _finish(self) -> None:
        self.btn.setEnabled(True)
        self.stop_btn.setVisible(False)

    def _on_done(self, text: str) -> None:
        self._finish()
        self.status.setText("Done.")
        if self.on_done:
            self.on_done(text)

    def _on_failed(self, msg: str) -> None:
        self._finish()
        self.status.setText("")
        error_box(self, msg)


class ContextPicker(QGroupBox):
    """Checklist of library + history items the AI may draw from."""

    def __init__(self, ctx: ClassContext, parent=None):
        super().__init__("Sources the AI can use", parent)
        self.ctx = ctx
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter...")
        self.search.textChanged.connect(self._filter)
        self.list = QListWidget()
        self.list.setMinimumHeight(110)
        self.all_box = QCheckBox("Select all")
        self.all_box.setChecked(True)
        self.all_box.toggled.connect(self._toggle_all)
        self.hint = label("", "muted")
        lay = QVBoxLayout(self)
        lay.addWidget(self.search)
        lay.addWidget(self.all_box)
        lay.addWidget(self.list, 1)
        lay.addWidget(self.hint)
        self.refresh()

    def refresh(self, keep_checked: set[str] | None = None) -> None:
        previous = keep_checked if keep_checked is not None else set(self.selected_ids())
        first = self.list.count() == 0 and keep_checked is None
        self.list.clear()
        for s in self.ctx.knowledge.all_sources():
            prefix = "History - " if s["kind"] == "history" else ""
            it = QListWidgetItem(prefix + s["name"])
            it.setData(Qt.UserRole, s["id"])
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if first or s["id"] in previous else Qt.Unchecked)
            self.list.addItem(it)
        self.hint.setText("" if self.list.count() else
                          "Nothing in this class's library yet - add notes, slides or transcripts first.")
        self._filter(self.search.text())

    def _filter(self, text: str) -> None:
        for i in range(self.list.count()):
            it = self.list.item(i)
            it.setHidden(text.lower() not in it.text().lower())

    def _toggle_all(self, on: bool) -> None:
        for i in range(self.list.count()):
            if not self.list.item(i).isHidden():
                self.list.item(i).setCheckState(Qt.Checked if on else Qt.Unchecked)

    def selected_ids(self) -> list[str]:
        return [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())
                if self.list.item(i).checkState() == Qt.Checked]

    def set_selected(self, ids: list[str]) -> None:
        wanted = set(ids)
        for i in range(self.list.count()):
            self.list.item(i).setCheckState(Qt.Checked if self.list.item(i).data(Qt.UserRole) in wanted
                                            else Qt.Unchecked)
