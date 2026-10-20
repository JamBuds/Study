"""Thin client for the local Ollama HTTP API."""
import json
import re
from typing import Iterator

import httpx


class OllamaError(Exception):
    """Raised with a message that is safe to show to the user."""


class _ThinkFilter:
    """Drops <think>...</think> blocks that some models stream inline."""

    def __init__(self):
        self.buf, self.inside = "", False

    def feed(self, piece: str) -> str:
        self.buf += piece
        out = ""
        while True:
            tag = "</think>" if self.inside else "<think>"
            i = self.buf.find(tag)
            if i >= 0:
                if not self.inside:
                    out += self.buf[:i]
                self.buf, self.inside = self.buf[i + len(tag):], not self.inside
                continue
            keep = max((n for n in range(1, len(tag)) if self.buf.endswith(tag[:n])), default=0)
            if not self.inside:
                out += self.buf[:len(self.buf) - keep]
            self.buf = self.buf[len(self.buf) - keep:]
            return out

    def flush(self) -> str:
        out = "" if self.inside else self.buf
        self.buf = ""
        return out


def strip_think(text: str) -> str:
    return re.sub(r"<think>.*?</think>\s*", "", text, flags=re.S).strip()


def _same_model(a: str, b: str) -> bool:
    norm = lambda m: m if ":" in m else f"{m}:latest"
    return norm(a) == norm(b)


class OllamaClient:
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url.rstrip("/")
        self._timeout = httpx.Timeout(connect=5, read=900, write=30, pool=5)

    # ---- helpers ----------------------------------------------------
    def _check(self, resp: httpx.Response, model: str | None = None) -> None:
        if resp.status_code < 400:
            return
        try:
            resp.read()
            msg = resp.json().get("error", resp.text)
        except Exception:
            msg = resp.text
        if resp.status_code == 404 and model:
            msg = f'The model "{model}" isn\'t downloaded yet. Open Settings and click "Download model".'
        raise OllamaError(msg or f"Ollama returned HTTP {resp.status_code}")

    def _wrap(self, exc: Exception) -> OllamaError:
        if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)):
            return OllamaError(f"Can't reach Ollama at {self.base_url}. Is it running?")
        if isinstance(exc, httpx.ReadTimeout):
            return OllamaError("Ollama took too long to answer. A smaller model may help.")
        return OllamaError(str(exc))

    # ---- status -----------------------------------------------------
    def health(self) -> bool:
        try:
            return httpx.get(f"{self.base_url}/api/tags", timeout=3).status_code == 200
        except httpx.HTTPError:
            return False

    def list_models(self) -> list[str]:
        try:
            r = httpx.get(f"{self.base_url}/api/tags", timeout=5)
            self._check(r)
            return [m["name"] for m in r.json().get("models", [])]
        except httpx.HTTPError as e:
            raise self._wrap(e)

    def has_model(self, name: str) -> bool:
        return any(_same_model(name, m) for m in self.list_models())

    # ---- pulling ----------------------------------------------------
    def pull(self, model: str) -> Iterator[dict]:
        """Yield progress dicts: {status, completed, total}."""
        try:
            with httpx.stream("POST", f"{self.base_url}/api/pull", json={"model": model, "stream": True},
                              timeout=httpx.Timeout(connect=5, read=None, write=30, pool=5)) as r:
                self._check(r)
                for line in r.iter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    if "error" in data:
                        raise OllamaError(data["error"])
                    yield data
        except httpx.HTTPError as e:
            raise self._wrap(e)

    # ---- chat -------------------------------------------------------
    def chat_stream(self, model: str, messages: list[dict], options: dict | None = None,
                    fmt=None) -> Iterator[str]:
        body = {"model": model, "messages": messages, "stream": True, "think": False,
                "options": options or {}}
        if fmt:
            body["format"] = fmt
        flt = _ThinkFilter()
        try:
            with httpx.stream("POST", f"{self.base_url}/api/chat", json=body, timeout=self._timeout) as r:
                self._check(r, model)
                for line in r.iter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    if "error" in data:
                        raise OllamaError(data["error"])
                    piece = flt.feed(data.get("message", {}).get("content", ""))
                    if piece:
                        yield piece
                tail = flt.flush()
                if tail:
                    yield tail
        except httpx.HTTPError as e:
            raise self._wrap(e)

    def chat(self, model: str, messages: list[dict], options: dict | None = None, fmt=None) -> str:
        return "".join(self.chat_stream(model, messages, options, fmt))

    def chat_json(self, model: str, messages: list[dict], schema: dict, options: dict | None = None):
        return parse_json(self.chat(model, messages, options, fmt=schema))

    # ---- embeddings -------------------------------------------------
    def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            r = httpx.post(f"{self.base_url}/api/embed", json={"model": model, "input": texts},
                           timeout=self._timeout)
            self._check(r, model)
            return r.json()["embeddings"]
        except httpx.HTTPError as e:
            raise self._wrap(e)


def parse_json(text: str):
    """Parse model output as JSON, tolerating code fences and surrounding prose."""
    text = strip_think(text)
    try:
        return json.loads(text)
    except ValueError:
        pass
    m = re.search(r"[\{\[]", text)
    end = max(text.rfind("}"), text.rfind("]"))
    if m and end > m.start():
        try:
            return json.loads(text[m.start():end + 1])
        except ValueError:
            pass
    raise OllamaError("The AI's reply wasn't in the expected format. Please try again.")
