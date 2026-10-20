"""Paths and user settings."""
import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

APP_NAME = "StudyBuddy"
DEFAULT_CHAT_MODEL = "qwen3.5:4b"
LOW_END_CHAT_MODEL = "llama3.2:3b"
DEFAULT_EMBED_MODEL = "nomic-embed-text"
OLLAMA_DOWNLOAD_URL = "https://ollama.com/download"


def data_root() -> Path:
    """Folder holding settings.json and all classes (override with STUDYBUDDY_HOME)."""
    env = os.environ.get("STUDYBUDDY_HOME")
    root = Path(env) if env else Path.home() / "Documents" / APP_NAME
    (root / "Classes").mkdir(parents=True, exist_ok=True)
    return root


@dataclass
class Settings:
    ollama_url: str = "http://localhost:11434"
    chat_model: str = DEFAULT_CHAT_MODEL
    embed_model: str = DEFAULT_EMBED_MODEL
    num_ctx: int = 8192
    learning_mode: bool = True
    theme: str = "light"
    whisper_model: str = "base"
    setup_done: bool = False

    @staticmethod
    def path() -> Path:
        return data_root() / "settings.json"

    @classmethod
    def load(cls) -> "Settings":
        s = cls()
        try:
            data = json.loads(cls.path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return s
        for f in fields(cls):
            if f.name in data and isinstance(data[f.name], type(getattr(s, f.name))):
                setattr(s, f.name, data[f.name])
        return s

    def save(self) -> None:
        self.path().write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
