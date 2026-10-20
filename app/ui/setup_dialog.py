"""Settings + first-run setup: checks Ollama, downloads models."""
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
                               QLineEdit, QProgressBar, QPushButton, QSpinBox, QVBoxLayout)

from app.ai.ollama_client import OllamaClient
from app.config import DEFAULT_CHAT_MODEL, DEFAULT_EMBED_MODEL, LOW_END_CHAT_MODEL, OLLAMA_DOWNLOAD_URL, Settings
from app.ui.common import error_box, label, primary, run_task


class SetupDialog(QDialog):
    def __init__(self, settings: Settings, first_run: bool = False, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Welcome to StudyBuddy" if first_run else "Settings")
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)
        if first_run:
            lay.addWidget(label("Let's get the AI ready", "title"))
            lay.addWidget(label(
                "StudyBuddy uses Ollama, a free app that runs AI models privately on your own computer. "
                "Nothing you type leaves your PC.", "subtitle"))
        self.status = label("")
        lay.addWidget(self.status)
        self.install_btn = QPushButton("Download Ollama (opens website)")
        self.install_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(OLLAMA_DOWNLOAD_URL)))
        lay.addWidget(self.install_btn)

        form = QFormLayout()
        self.url = QLineEdit(settings.ollama_url)
        self.chat = QComboBox()
        self.chat.setEditable(True)
        self.embed = QComboBox()
        self.embed.setEditable(True)
        self.ctx_spin = QSpinBox()
        self.ctx_spin.setRange(2048, 32768)
        self.ctx_spin.setSingleStep(1024)
        self.ctx_spin.setValue(settings.num_ctx)
        self.learning = QCheckBox("Learning mode (explain first, so you actually learn it)")
        self.learning.setChecked(settings.learning_mode)
        self.theme = QComboBox()
        self.theme.addItems(["light", "dark"])
        self.theme.setCurrentText(settings.theme)
        self.whisper = QComboBox()
        self.whisper.addItems(["tiny", "base", "small", "medium"])
        self.whisper.setCurrentText(settings.whisper_model)
        form.addRow("Ollama address", self.url)
        form.addRow("Chat model", self.chat)
        form.addRow("Search model", self.embed)
        form.addRow("Context size", self.ctx_spin)
        form.addRow("Recording transcriber", self.whisper)
        form.addRow("Theme", self.theme)
        form.addRow("", self.learning)
        lay.addLayout(form)
        lay.addWidget(label(f"Tip: {DEFAULT_CHAT_MODEL} needs about 6 GB of RAM. On an older laptop pick "
                            f"{LOW_END_CHAT_MODEL}.", "muted"))

        row = QHBoxLayout()
        self.check_btn = QPushButton("Check connection")
        self.check_btn.clicked.connect(self.check)
        self.pull_chat = primary("Download chat model")
        self.pull_chat.clicked.connect(lambda: self.pull(self.chat.currentText().strip()))
        self.pull_embed = QPushButton("Download search model")
        self.pull_embed.clicked.connect(lambda: self.pull(self.embed.currentText().strip()))
        for b in (self.check_btn, self.pull_chat, self.pull_embed):
            row.addWidget(b)
        lay.addLayout(row)
        self.bar = QProgressBar()
        self.bar.setVisible(False)
        lay.addWidget(self.bar)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self._fill_models([])
        self.check()

    def client(self) -> OllamaClient:
        return OllamaClient(self.url.text().strip() or "http://localhost:11434")

    def _fill_models(self, installed: list[str]) -> None:
        for combo, current, default in ((self.chat, self.settings.chat_model, DEFAULT_CHAT_MODEL),
                                        (self.embed, self.settings.embed_model, DEFAULT_EMBED_MODEL)):
            text = combo.currentText() or current
            combo.clear()
            names = list(dict.fromkeys([current, default, *(LOW_END_CHAT_MODEL,) * (combo is self.chat), *installed]))
            combo.addItems(names)
            combo.setCurrentText(text)

    def check(self) -> None:
        client = self.client()
        self.status.setText("Checking Ollama...")

        def work(_ctx):
            return client.list_models() if client.health() else None

        def done(models):
            if models is None:
                self.status.setText("Ollama isn't running. Install it, open it once, then press Check connection.")
                self.install_btn.setVisible(True)
                return
            self._fill_models(models)
            self.install_btn.setVisible(False)
            missing = [m for m in (self.chat.currentText(), self.embed.currentText())
                       if m and not _has(models, m)]
            self.status.setText("Ollama is running. All models are ready." if not missing else
                                f"Ollama is running. Still to download: {', '.join(missing)}")

        run_task(self, work, done, lambda m: self.status.setText(m))

    def pull(self, model: str) -> None:
        if not model:
            return
        client = self.client()
        self.bar.setVisible(True)
        self.bar.setRange(0, 0)
        for b in (self.pull_chat, self.pull_embed):
            b.setEnabled(False)

        def work(ctx):
            for data in client.pull(model):
                ctx.report(data)
            return model

        def progress(data):
            total, done = data.get("total"), data.get("completed")
            self.status.setText(f"{model}: {data.get('status', '')}")
            if total:
                self.bar.setRange(0, 100)
                self.bar.setValue(int(100 * (done or 0) / total))

        def finished(_):
            self.bar.setVisible(False)
            for b in (self.pull_chat, self.pull_embed):
                b.setEnabled(True)
            self.check()

        def failed(msg):
            finished(None)
            error_box(self, msg, "Download failed")

        run_task(self, work, finished, failed, progress)

    def save(self) -> None:
        s = self.settings
        s.ollama_url = self.url.text().strip() or s.ollama_url
        s.chat_model = self.chat.currentText().strip() or s.chat_model
        s.embed_model = self.embed.currentText().strip() or s.embed_model
        s.num_ctx = self.ctx_spin.value()
        s.learning_mode = self.learning.isChecked()
        s.theme = self.theme.currentText()
        s.whisper_model = self.whisper.currentText()
        s.setup_done = True
        s.save()
        self.accept()


def _has(models: list[str], name: str) -> bool:
    norm = lambda m: m if ":" in m else f"{m}:latest"
    return any(norm(name) == norm(m) for m in models)
