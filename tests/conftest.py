import hashlib
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def fake_vector(text: str, dim: int = 32):
    vec = [0.0] * dim
    for word in text.lower().split():
        h = int(hashlib.md5(word.encode()).hexdigest(), 16)
        vec[h % dim] += 1.0
    return vec


QUIZ = {"questions": [
    {"type": "multiple_choice", "question": "What organelle makes ATP?", "choices": ["Nucleus", "Mitochondria", "Ribosome", "Golgi"],
     "answer": "B", "explanation": "Mitochondria produce ATP.", "source": "Bio notes - Slide 2"},
    {"type": "true_false", "question": "Ribosomes make proteins.", "answer": "true", "explanation": "Yes.", "source": "Bio notes"},
    {"type": "short_answer", "question": "Why do cells need ATP?", "answer": "It is the energy currency of the cell.",
     "explanation": "Energy.", "source": "Bio notes"},
]}
CARDS = {"cards": [{"front": "ATP", "back": "Energy currency"}, {"front": "Ribosome", "back": "Makes proteins"}]}


class FakeOllama(BaseHTTPRequestHandler):
    models = ["fake-chat:latest", "nomic-embed-text:latest"]
    chat_log: list = []

    def log_message(self, *a):
        pass

    def _send(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/tags":
            self._send({"models": [{"name": m} for m in self.models]})
        else:
            self._send({"error": "nope"}, 404)

    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/api/embed":
            self._send({"embeddings": [fake_vector(t) for t in data["input"]]})
        elif self.path == "/api/pull":
            self.send_response(200)
            self.end_headers()
            for done in (0, 50, 100):
                self.wfile.write((json.dumps({"status": "downloading", "total": 100, "completed": done}) + "\n").encode())
            self.wfile.write(b'{"status": "success"}\n')
        elif self.path == "/api/chat":
            if data["model"] not in ("fake-chat", "fake-chat:latest"):
                self._send({"error": f"model '{data['model']}' not found"}, 404)
                return
            FakeOllama.chat_log.append(data)
            fmt = data.get("format")
            props = (fmt or {}).get("properties", {})
            if "questions" in props:
                text = json.dumps(QUIZ)
            elif "cards" in props:
                text = json.dumps(CARDS)
            elif "correct" in props:
                text = json.dumps({"correct": True, "feedback": "Good."})
            else:
                text = "<think>hidden</think>Here is a helpful answer [Bio notes - Slide 2]."
            self.send_response(200)
            self.end_headers()
            step = max(1, len(text) // 4)
            for i in range(0, len(text), step):
                self.wfile.write((json.dumps({"message": {"content": text[i:i + step]}, "done": False}) + "\n").encode())
            self.wfile.write(b'{"message": {"content": ""}, "done": true}\n')
        else:
            self._send({"error": "nope"}, 404)


@pytest.fixture(scope="session")
def ollama_url():
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeOllama)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("STUDYBUDDY_HOME", str(tmp_path / "home"))
    FakeOllama.chat_log.clear()
    return tmp_path / "home"


@pytest.fixture
def settings(ollama_url):
    from app.config import Settings
    return Settings(ollama_url=ollama_url, chat_model="fake-chat", embed_model="nomic-embed-text", setup_done=True)
