"""StudyBuddy entry point."""
import sys

from PySide6.QtWidgets import QApplication, QMainWindow, QStackedWidget

from app.ai.workers import finish_all_workers
from app.config import APP_NAME, Settings
from app.storage.classes import open_class
from app.ui.class_picker import ClassPicker
from app.ui.class_shell import ClassShell
from app.ui.common import error_box
from app.ui.setup_dialog import SetupDialog
from app.ui.theme import stylesheet


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self.setWindowTitle(APP_NAME)
        self.resize(1180, 780)
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self.picker = ClassPicker()
        self.picker.class_chosen.connect(self.open_class)
        self.picker.open_settings.connect(self.open_settings)
        self.stack.addWidget(self.picker)
        self.shell: ClassShell | None = None

    def open_class(self, name: str) -> None:
        try:
            store = open_class(name)
        except FileNotFoundError:
            error_box(self, f'Couldn\'t find the class "{name}".')
            self.picker.refresh()
            return
        self.close_shell()
        self.shell = ClassShell(store, self.settings)
        self.shell.back_requested.connect(self.show_picker)
        self.shell.settings_requested.connect(self.open_settings)
        self.stack.addWidget(self.shell)
        self.stack.setCurrentWidget(self.shell)

    def closeEvent(self, event) -> None:
        finish_all_workers()
        self.close_shell()
        super().closeEvent(event)

    def close_shell(self) -> None:
        if self.shell:
            self.stack.removeWidget(self.shell)
            self.shell.close_class()
            self.shell.deleteLater()
            self.shell = None

    def show_picker(self) -> None:
        self.close_shell()
        self.picker.refresh()
        self.stack.setCurrentWidget(self.picker)

    def open_settings(self) -> None:
        if SetupDialog(self.settings, parent=self).exec():
            apply_theme(self.settings)
            if self.shell:  # rebuild so the new Ollama address / models take effect
                self.open_class(self.shell.store.name)


def apply_theme(settings: Settings) -> None:
    QApplication.instance().setStyleSheet(stylesheet(settings.theme))


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    settings = Settings.load()
    apply_theme(settings)
    if not settings.setup_done:
        SetupDialog(settings, first_run=True).exec()
        settings.setup_done = True
        settings.save()
        apply_theme(settings)
    win = MainWindow(settings)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
