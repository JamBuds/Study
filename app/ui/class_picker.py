"""Start screen: choose a class to continue, or create a new one."""
from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QGridLayout,
                               QHBoxLayout, QLineEdit, QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget)

from app.storage.classes import ClassInfo, create_class, delete_class, import_class, list_classes
from app.tools.essay import STYLES
from app.ui.common import card, error_box, label, primary


class NewClassDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New class")
        self.setMinimumWidth(380)
        self.name = QLineEdit()
        self.name.setPlaceholderText("e.g. AP Biology")
        self.teacher = QLineEdit()
        self.teacher.setPlaceholderText("optional")
        self.style = QComboBox()
        self.style.addItems(STYLES)
        form = QFormLayout()
        form.addRow("Class name", self.name)
        form.addRow("Teacher", self.teacher)
        form.addRow("Citation style", self.style)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(buttons)

    def create(self):
        return create_class(self.name.text(), self.teacher.text(), self.style.currentText())


def _when(info: ClassInfo) -> str:
    stamp = info.last_opened or info.created
    try:
        return "Last opened " + datetime.fromisoformat(stamp).strftime("%b %d")
    except ValueError:
        return ""


class ClassPicker(QWidget):
    class_chosen = Signal(str)
    open_settings = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 30, 40, 30)
        head = QHBoxLayout()
        titles = QVBoxLayout()
        titles.addWidget(label("StudyBuddy", "title"))
        self.subtitle = label("", "subtitle")
        titles.addWidget(self.subtitle)
        head.addLayout(titles, 1)
        settings_btn = QPushButton("Settings")
        settings_btn.clicked.connect(self.open_settings)
        import_btn = QPushButton("Import class...")
        import_btn.clicked.connect(self.import_zip)
        new_btn = primary("+ New class")
        new_btn.clicked.connect(self.new_class)
        for b in (settings_btn, import_btn, new_btn):
            head.addWidget(b, 0, Qt.AlignTop)
        outer.addLayout(head)
        self.body = QWidget()
        self.grid = QGridLayout(self.body)
        self.grid.setAlignment(Qt.AlignTop)
        self.grid.setSpacing(14)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.body)
        outer.addWidget(scroll, 1)
        self.refresh()

    def refresh(self) -> None:
        while self.grid.count():
            self.grid.takeAt(0).widget().deleteLater()
        classes = list_classes()
        if not classes:
            self.subtitle.setText("Welcome! Create your first class to get started.")
            box = card()
            lay = QVBoxLayout(box)
            lay.setContentsMargins(30, 30, 30, 30)
            lay.addWidget(label("No classes yet", "h2"))
            lay.addWidget(label("A class keeps its own library of notes, slides and transcripts, plus a history "
                                "of your past essays and quizzes, so the AI can build on them."))
            b = primary("Create my first class")
            b.clicked.connect(self.new_class)
            lay.addWidget(b, 0, Qt.AlignLeft)
            self.grid.addWidget(box, 0, 0)
            return
        self.subtitle.setText("Which class are we working on?")
        for i, info in enumerate(classes):
            self.grid.addWidget(self._tile(info), i // 3, i % 3)

    def _tile(self, info: ClassInfo) -> QWidget:
        box = card()
        box.setMinimumWidth(220)
        lay = QVBoxLayout(box)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.addWidget(label(info.name, "h2"))
        lay.addWidget(label(" - ".join(x for x in (info.teacher, info.citation_style) if x), "muted"))
        lay.addWidget(label(_when(info), "muted"))
        row = QHBoxLayout()
        go = primary("Continue")
        go.clicked.connect(lambda: self.class_chosen.emit(info.name))
        rm = QPushButton("Delete")
        rm.clicked.connect(lambda: self.remove(info.name))
        row.addWidget(go, 1)
        row.addWidget(rm)
        lay.addLayout(row)
        return box

    def new_class(self) -> None:
        dlg = NewClassDialog(self)
        while dlg.exec():
            try:
                store = dlg.create()
            except (ValueError, FileExistsError) as e:
                error_box(self, str(e), "Can't create class")
                continue
            self.class_chosen.emit(store.name)
            return

    def remove(self, name: str) -> None:
        if QMessageBox.question(self, "Delete class",
                                f'Delete "{name}" and everything in it (library and history)? This can\'t be undone.'
                                ) == QMessageBox.Yes:
            delete_class(name)
            self.refresh()

    def import_zip(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import a class", "", "StudyBuddy class (*.zip)")
        if path:
            try:
                name = import_class(path)
            except Exception as e:
                error_box(self, str(e), "Import failed")
                return
            self.refresh()
            QMessageBox.information(self, "Imported", f'Imported "{name}".')
