"""Past essays, quizzes and flashcard decks for a class."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QHBoxLayout, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QTabWidget,
                               QVBoxLayout, QWidget)

from app.ui.common import ClassContext, label, primary

KINDS = [("essay", "Essays"), ("quiz", "Quizzes"), ("flashcards", "Flashcards")]


def pretty_date(stamp: str) -> str:
    return stamp[:10] if stamp else ""


class HistoryPage(QWidget):
    def __init__(self, ctx: ClassContext, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.lists: dict[str, QListWidget] = {}
        lay = QVBoxLayout(self)
        lay.addWidget(label(f"{ctx.store.name} - History", "title"))
        lay.addWidget(label("Everything you've made in this class. The AI can also draw on these when you pick "
                            "them as sources.", "subtitle"))
        self.tabs = QTabWidget()
        for kind, title in KINDS:
            lst = QListWidget()
            lst.itemDoubleClicked.connect(lambda _it: self.open_selected())
            self.lists[kind] = lst
            self.tabs.addTab(lst, title)
        lay.addWidget(self.tabs, 1)
        bar = QHBoxLayout()
        bar.addStretch(1)
        rm = QPushButton("Delete")
        rm.clicked.connect(self.delete)
        op = primary("Open")
        op.clicked.connect(self.open_selected)
        bar.addWidget(rm)
        bar.addWidget(op)
        lay.addLayout(bar)
        self.refresh()

    def refresh(self) -> None:
        for kind, _ in KINDS:
            lst = self.lists[kind]
            lst.clear()
            for item in self.ctx.store.list_history(kind):
                it = QListWidgetItem(f"{item['title']}    ({pretty_date(item['date'])})")
                it.setData(Qt.UserRole, item["id"])
                lst.addItem(it)

    def _current(self):
        kind = KINDS[self.tabs.currentIndex()][0]
        it = self.lists[kind].currentItem()
        return (kind, it.data(Qt.UserRole)) if it else (kind, None)

    def open_selected(self) -> None:
        kind, hid = self._current()
        if hid:
            self.ctx.shell.open_history(kind, hid)

    def delete(self) -> None:
        kind, hid = self._current()
        if hid and QMessageBox.question(self, "Delete", "Delete this item from history?") == QMessageBox.Yes:
            self.ctx.store.delete_history(kind, hid)
            self.ctx.knowledge.remove_history(kind, hid)
            self.refresh()
