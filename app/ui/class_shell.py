"""A class workspace: header, dashboard and the tool pages."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QFileDialog, QGridLayout, QHBoxLayout, QListWidget, QListWidgetItem, QMessageBox,
                               QPushButton, QStackedWidget, QVBoxLayout, QWidget)

from app.ai.ollama_client import OllamaClient
from app.config import Settings
from app.knowledge import Knowledge
from app.storage.classes import ClassStore, export_class
from app.tools.essay import EssayProject
from app.tools.quiz import Quiz
from app.ui.add_info import AddInfoDialog
from app.ui.common import ClassContext, error_box, label, run_task
from app.ui.convert_view import ConvertPage
from app.ui.essay_view import EssayPage
from app.ui.history_view import HistoryPage, pretty_date
from app.ui.library_view import LibraryPage
from app.ui.quiz_view import QuizPage


class Dashboard(QWidget):
    def __init__(self, shell: "ClassShell"):
        super().__init__()
        self.shell = shell
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.addWidget(label(shell.store.name, "title"))
        info = shell.store.load_info()
        lay.addWidget(label(" - ".join(x for x in (info.teacher, f"{info.citation_style} citations") if x), "subtitle"))
        grid = QGridLayout()
        grid.setSpacing(14)
        tiles = [("Essay help\nThesis, outline, draft, feedback, citations", shell.start_essay),
                 ("Quiz help\nPractice quizzes, explanations, flashcards", shell.start_quiz),
                 ("Convert to text\nSlides, PDFs, recordings, images", shell.show_convert),
                 ("Library\nYour notes and sources for this class", shell.show_library),
                 ("History\nPast essays, quizzes and decks", shell.show_history)]
        for i, (text, fn) in enumerate(tiles):
            b = QPushButton(text)
            b.setObjectName("tile")
            b.setMinimumHeight(90)
            b.clicked.connect(fn)
            grid.addWidget(b, i // 3, i % 3)
        lay.addLayout(grid)
        lay.addWidget(label("Recent activity", "h2"))
        self.recent = QListWidget()
        self.recent.setMaximumHeight(170)
        self.recent.itemDoubleClicked.connect(self.open_recent)
        lay.addWidget(self.recent)
        items = []
        for kind in ("essay", "quiz", "flashcards"):
            items += shell.store.list_history(kind)
        for item in sorted(items, key=lambda i: i["date"], reverse=True)[:6]:
            it = QListWidgetItem(f"{item['kind'].title()}: {item['title']}    ({pretty_date(item['date'])})")
            it.setData(Qt.UserRole, (item["kind"], item["id"]))
            self.recent.addItem(it)
        if not items:
            self.recent.addItem("Nothing yet - start an essay or quiz above.")
        lay.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        share = QPushButton("Export class (share with a friend)...")
        share.clicked.connect(shell.export)
        row.addWidget(share)
        lay.addLayout(row)

    def open_recent(self, item):
        data = item.data(Qt.UserRole)
        if data:
            self.shell.open_history(*data)


class ClassShell(QWidget):
    back_requested = Signal()
    settings_requested = Signal()

    def __init__(self, store: ClassStore, settings: Settings, parent=None):
        super().__init__(parent)
        self.store = store
        client = OllamaClient(settings.ollama_url)
        self.knowledge = Knowledge(store, client, settings)
        self.ctx = ClassContext(store, self.knowledge, client, settings, self)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(30, 20, 30, 20)
        head = QHBoxLayout()
        classes = QPushButton("< Classes")
        classes.clicked.connect(self.back_requested)
        home = QPushButton("Dashboard")
        home.clicked.connect(self.show_dashboard)
        sett = QPushButton("Settings")
        sett.clicked.connect(self.settings_requested)
        self.status = label("", "muted", wrap=False)
        head.addWidget(classes)
        head.addWidget(home)
        head.addWidget(self.status, 1)
        head.addWidget(sett)
        lay.addLayout(head)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)
        self.show_dashboard()
        self._sync()

    def _sync(self) -> None:
        self.status.setText("Checking library...")
        run_task(self, lambda t: self.knowledge.sync_library(lambda m: t.report(m)),
                 lambda n: self.status.setText(""), lambda m: self.status.setText(""),
                 lambda m: self.status.setText(str(m)))

    def close_class(self) -> None:
        self.knowledge.index.close()

    # ---- navigation ------------------------------------------------------------
    def _show(self, page: QWidget) -> QWidget:
        while self.stack.count():
            old = self.stack.widget(0)
            self.stack.removeWidget(old)
            old.deleteLater()
        self.stack.addWidget(page)
        return page

    def show_dashboard(self):
        self._show(Dashboard(self))

    def show_convert(self):
        self._show(ConvertPage(self.ctx))

    def show_library(self):
        self._show(LibraryPage(self.ctx))

    def show_history(self):
        self._show(HistoryPage(self.ctx))

    def _ask_for_info(self, task: str) -> bool:
        dlg = AddInfoDialog(self.ctx, f"Before we start {task} - anything to add to {self.store.name}'s library?",
                            parent=self)
        dlg.exec()
        return True

    def start_essay(self):
        self._ask_for_info("your essay")
        self._show(EssayPage(self.ctx))

    def start_quiz(self):
        self._ask_for_info("your quiz")
        self._show(QuizPage(self.ctx))

    def open_history(self, kind: str, hid: str) -> None:
        try:
            data = self.store.load_history(kind, hid)
        except (OSError, ValueError) as e:
            error_box(self, f"Couldn't open that item: {e}")
            return
        if kind == "essay":
            self._show(EssayPage(self.ctx, EssayProject.from_dict(data)))
        elif kind == "quiz":
            page = self._show(QuizPage(self.ctx))
            page.open_quiz(Quiz.from_dict(data))
        else:
            data["id"] = hid
            page = self._show(QuizPage(self.ctx))
            page.open_flashcards(data)

    def export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export class", f"{self.store.name}.zip", "Zip (*.zip)")
        if path:
            try:
                export_class(self.store, path)
            except Exception as e:
                error_box(self, str(e), "Export failed")
                return
            QMessageBox.information(self, "Exported", "Send this zip to a friend - they can use "
                                                      "'Import class...' on the start screen.")
