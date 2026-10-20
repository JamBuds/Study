"""Browse, add, edit citation details for, and delete library items."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QSplitter, QVBoxLayout,
                               QWidget)

from app.ui.add_info import AddInfoDialog
from app.ui.common import ClassContext, label, primary, run_task

META_FIELDS = [("author", "Author"), ("title", "Title"), ("year", "Year"), ("publisher", "Publisher / site"),
               ("url", "URL")]


class MetadataDialog(QDialog):
    def __init__(self, name: str, meta: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Citation details - {name}")
        self.edits = {k: QLineEdit(meta.get(k, "")) for k, _ in META_FIELDS}
        form = QFormLayout()
        for k, text in META_FIELDS:
            form.addRow(text, self.edits[k])
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(label("Used to build your Works Cited. Leave blank anything you don't know.", "muted"))
        lay.addLayout(form)
        lay.addWidget(buttons)

    def values(self) -> dict:
        return {k: e.text().strip() for k, e in self.edits.items() if e.text().strip()}


class LibraryPage(QWidget):
    def __init__(self, ctx: ClassContext, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        lay = QVBoxLayout(self)
        lay.addWidget(label(f"{ctx.store.name} - Library", "title"))
        lay.addWidget(label("Everything the AI can draw on for this class. Files you drop into the Library folder "
                            "are picked up automatically.", "subtitle"))
        bar = QHBoxLayout()
        add = primary("Add files / text...")
        add.clicked.connect(self.add)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter...")
        self.search.textChanged.connect(self.refresh)
        meta = QPushButton("Citation details...")
        meta.clicked.connect(self.edit_meta)
        rm = QPushButton("Delete")
        rm.clicked.connect(self.delete)
        bar.addWidget(add)
        bar.addWidget(self.search, 1)
        bar.addWidget(meta)
        bar.addWidget(rm)
        lay.addLayout(bar)
        split = QSplitter(Qt.Horizontal)
        self.list = QListWidget()
        self.list.currentItemChanged.connect(self.show_item)
        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        split.addWidget(self.list)
        split.addWidget(self.view)
        split.setStretchFactor(1, 3)
        lay.addWidget(split, 1)
        self.status = label("", "muted")
        lay.addWidget(self.status)
        self.sync()

    def sync(self) -> None:
        self.status.setText("Checking library...")
        run_task(self, lambda t: self.ctx.knowledge.sync_library(lambda m: t.report(m)),
                 lambda n: (self.refresh(), self.status.setText(f"{n} new file(s) indexed." if n else "")),
                 lambda m: (self.refresh(), self.status.setText(m)), lambda m: self.status.setText(str(m)))

    def refresh(self, *_):
        text = self.search.text().lower()
        self.list.clear()
        for name in self.ctx.store.list_library():
            if text in name.lower():
                self.list.addItem(QListWidgetItem(name))

    def _name(self) -> str | None:
        it = self.list.currentItem()
        return it.text() if it else None

    def show_item(self, current, _prev=None):
        self.view.setPlainText(self.ctx.store.read_library_text(current.text()) if current else "")

    def add(self):
        dlg = AddInfoDialog(self.ctx, "Add to the library", can_skip=False, parent=self)
        dlg.exec()
        self.refresh()

    def edit_meta(self):
        name = self._name()
        if not name:
            return
        meta = self.ctx.store.load_metadata()
        dlg = MetadataDialog(name, meta.get(name, {}), self)
        if dlg.exec():
            meta[name] = dlg.values()
            self.ctx.store.save_metadata(meta)

    def delete(self):
        name = self._name()
        if name and QMessageBox.question(self, "Delete", f'Remove "{name}" from the library?') == QMessageBox.Yes:
            self.ctx.knowledge.remove_from_library(name)
            self.refresh()
