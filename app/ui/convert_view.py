"""Transcript / slides -> plain text converter."""
from pathlib import Path

from PySide6.QtWidgets import (QCheckBox, QFileDialog, QHBoxLayout, QListWidget, QListWidgetItem, QMessageBox,
                               QPlainTextEdit, QProgressBar, QPushButton, QSplitter, QVBoxLayout, QWidget)
from PySide6.QtCore import Qt

from app.convert import SUPPORTED, convert_file, file_dialog_filter
from app.convert.cleanup import ai_cleanup
from app.ui.common import ClassContext, error_box, label, primary, run_task


class ConvertPage(QWidget):
    def __init__(self, ctx: ClassContext, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.results: dict[str, str] = {}
        self.setAcceptDrops(True)
        lay = QVBoxLayout(self)
        lay.addWidget(label("Convert to plain text", "title"))
        lay.addWidget(label("Slides (.pptx), PDFs, Word docs, caption files, recordings (audio/video) and images "
                            "become plain text. Drag files in or use Add files.", "subtitle"))
        top = QHBoxLayout()
        add = QPushButton("Add files...")
        add.clicked.connect(self.pick)
        rm = QPushButton("Remove")
        rm.clicked.connect(self.remove_selected)
        self.cleanup = QCheckBox("AI cleanup (fix punctuation & paragraphs)")
        self.convert_btn = primary("Convert")
        self.convert_btn.clicked.connect(self.convert)
        for w in (add, rm, self.cleanup):
            top.addWidget(w)
        top.addStretch(1)
        top.addWidget(self.convert_btn)
        lay.addLayout(top)

        split = QSplitter(Qt.Horizontal)
        self.queue = QListWidget()
        self.queue.currentItemChanged.connect(self.show_result)
        self.preview = QPlainTextEdit()
        self.preview.setPlaceholderText("Converted text appears here. You can edit it before saving.")
        self.preview.textChanged.connect(self._store_edit)
        split.addWidget(self.queue)
        split.addWidget(self.preview)
        split.setStretchFactor(1, 3)
        lay.addWidget(split, 1)
        self.status = label("", "muted")
        self.bar = QProgressBar()
        self.bar.setVisible(False)
        lay.addWidget(self.status)
        lay.addWidget(self.bar)
        bottom = QHBoxLayout()
        save_txt = QPushButton("Save as .txt...")
        save_txt.clicked.connect(self.save_txt)
        save_lib = primary("Save to class library")
        save_lib.clicked.connect(self.save_library)
        bottom.addStretch(1)
        bottom.addWidget(save_txt)
        bottom.addWidget(save_lib)
        lay.addLayout(bottom)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        self.add_paths([Path(u.toLocalFile()) for u in e.mimeData().urls() if u.isLocalFile()])

    def pick(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Choose files", "", file_dialog_filter())
        self.add_paths([Path(p) for p in paths])

    def add_paths(self, paths: list[Path]) -> None:
        for p in paths:
            if not p.is_file():
                continue
            if p.suffix.lower() not in SUPPORTED:
                error_box(self, f"{p.name}: this file type isn't supported.", "Skipped")
                continue
            if any(self.queue.item(i).data(Qt.UserRole) == str(p) for i in range(self.queue.count())):
                continue
            it = QListWidgetItem(p.name)
            it.setData(Qt.UserRole, str(p))
            self.queue.addItem(it)

    def remove_selected(self):
        for it in self.queue.selectedItems():
            self.results.pop(it.data(Qt.UserRole), None)
            self.queue.takeItem(self.queue.row(it))

    def _current_key(self) -> str | None:
        it = self.queue.currentItem()
        return it.data(Qt.UserRole) if it else None

    def show_result(self, current, _prev=None):
        self.preview.blockSignals(True)
        self.preview.setPlainText(self.results.get(current.data(Qt.UserRole), "") if current else "")
        self.preview.blockSignals(False)

    def _store_edit(self):
        key = self._current_key()
        if key in self.results:
            self.results[key] = self.preview.toPlainText()

    def convert(self) -> None:
        keys = [self.queue.item(i).data(Qt.UserRole) for i in range(self.queue.count())]
        if not keys:
            error_box(self, "Add some files first.", "Nothing to convert")
            return
        whisper, ai, do_clean = self.ctx.settings.whisper_model, self.ctx, self.cleanup.isChecked()
        self.convert_btn.setEnabled(False)
        self.bar.setVisible(True)
        self.bar.setRange(0, 0)

        def work(task):
            out = {}
            for key in keys:
                name = Path(key).name
                try:
                    text = convert_file(key, whisper, lambda m: task.report(f"{name}: {m}"), lambda: task.cancelled)
                    if do_clean and text.strip():
                        text = ai_cleanup(ai.client, ai.settings.chat_model, text,
                                          lambda m: task.report(f"{name}: {m}"), lambda: task.cancelled)
                    out[key] = text or "(No text found in this file.)"
                except Exception as e:  # keep going with the other files
                    out[key] = f"(Couldn't convert this file: {e})"
            return out

        def done(res):
            self.results.update(res)
            self.convert_btn.setEnabled(True)
            self.bar.setVisible(False)
            self.status.setText(f"Converted {len(res)} file(s).")
            if self.queue.currentItem() is None and self.queue.count():
                self.queue.setCurrentRow(0)
            else:
                self.show_result(self.queue.currentItem())

        def failed(msg):
            self.convert_btn.setEnabled(True)
            self.bar.setVisible(False)
            error_box(self, msg)

        run_task(self, work, done, failed, lambda m: self.status.setText(str(m)))

    def save_txt(self):
        key = self._current_key()
        if not key or key not in self.results:
            error_box(self, "Convert a file and select it first.", "Nothing to save")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save text", str(Path(key).with_suffix(".txt")), "Text (*.txt)")
        if path:
            Path(path).write_text(self.results[key], encoding="utf-8")

    def save_library(self):
        ready = {k: v for k, v in self.results.items() if v.strip() and not v.startswith("(")}
        if not ready:
            error_box(self, "Convert some files first.", "Nothing to save")
            return
        k = self.ctx.knowledge

        def work(task):
            names = []
            for key, text in ready.items():
                task.report(f"Indexing {Path(key).name}...")
                names.append(k.add_to_library(Path(key).stem, text, Path(key)))
            return names

        def done(names):
            self.status.setText(f"Saved to library: {', '.join(names)}")
            QMessageBox.information(self, "Saved", f"Added {len(names)} item(s) to {self.ctx.store.name}'s library.")

        run_task(self, work, done, None, lambda m: self.status.setText(str(m)))
