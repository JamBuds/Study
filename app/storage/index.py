"""Chunking plus a per-class SQLite index with embedding / keyword search."""
import re
import sqlite3
import threading
from dataclasses import dataclass

import numpy as np

CHUNK_CHARS = 3200      # roughly 800 tokens
OVERLAP_CHARS = 400
_HEADER = re.compile(r"^\[((?:Slide|Page|Section)\s+\d+[^\]]*)\]", re.I)
_WORD = re.compile(r"[a-z0-9']{3,}")


@dataclass
class Chunk:
    source_id: str
    source_name: str
    label: str
    text: str
    score: float = 0.0

    @property
    def citation(self) -> str:
        return f"{self.source_name} - {self.label}" if self.label else self.source_name


def chunk_text(text: str, size: int = CHUNK_CHARS, overlap: int = OVERLAP_CHARS) -> list[tuple[str, str]]:
    """Split text into (label, chunk) pairs; label is the last Slide/Page header seen."""
    pieces: list[tuple[str, str]] = []
    label = ""
    for para in re.split(r"\n\s*\n", text.strip()):
        para = para.strip()
        if not para:
            continue
        m = _HEADER.match(para)
        if m:
            label = m.group(1)
        while len(para) > size:  # hard-split giant paragraphs
            pieces.append((label, para[:size]))
            para = para[size:]
        pieces.append((label, para))

    chunks: list[tuple[str, str]] = []
    cur, cur_label, tail = "", "", ""
    for lab, para in pieces:
        if cur and len(cur) + len(para) + 2 > size:
            chunks.append((cur_label, cur))
            tail = cur[-overlap:] if overlap else ""
            cur, cur_label = tail, lab
        if not cur_label:
            cur_label = lab
        cur = f"{cur}\n\n{para}" if cur else para
    if cur.strip() and (not chunks or cur.strip() != tail.strip()):
        chunks.append((cur_label, cur))
    return chunks


def _normalize(v) -> np.ndarray:
    a = np.asarray(v, dtype=np.float32)
    n = np.linalg.norm(a)
    return a / n if n else a


class Index:
    def __init__(self, path):
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY, kind TEXT, name TEXT, added TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS chunks(id INTEGER PRIMARY KEY, source_id TEXT, label TEXT, text TEXT, vec BLOB);
            CREATE INDEX IF NOT EXISTS chunks_src ON chunks(source_id);
        """)

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def add_source(self, source_id: str, kind: str, name: str,
                   chunks: list[tuple[str, str]], vectors: list | None = None) -> None:
        with self._lock, self._db:
            self._db.execute("DELETE FROM chunks WHERE source_id=?", (source_id,))
            self._db.execute("INSERT OR REPLACE INTO sources(id,kind,name) VALUES(?,?,?)",
                             (source_id, kind, name))
            for i, (label, text) in enumerate(chunks):
                blob = _normalize(vectors[i]).tobytes() if vectors and i < len(vectors) else None
                self._db.execute("INSERT INTO chunks(source_id,label,text,vec) VALUES(?,?,?,?)",
                                 (source_id, label, text, blob))

    def remove_source(self, source_id: str) -> None:
        with self._lock, self._db:
            self._db.execute("DELETE FROM chunks WHERE source_id=?", (source_id,))
            self._db.execute("DELETE FROM sources WHERE id=?", (source_id,))

    def sources(self, kind: str | None = None) -> list[dict]:
        q, args = "SELECT id,kind,name,added FROM sources", ()
        if kind:
            q, args = q + " WHERE kind=?", (kind,)
        with self._lock:
            rows = self._db.execute(q + " ORDER BY name COLLATE NOCASE", args).fetchall()
        return [dict(id=r[0], kind=r[1], name=r[2], added=r[3]) for r in rows]

    def has_source(self, source_id: str) -> bool:
        with self._lock:
            return self._db.execute("SELECT 1 FROM sources WHERE id=?", (source_id,)).fetchone() is not None

    def _rows(self, source_ids: list[str] | None):
        q = ("SELECT c.source_id, s.name, c.label, c.text, c.vec FROM chunks c "
             "JOIN sources s ON s.id=c.source_id")
        args: list = []
        if source_ids is not None:
            if not source_ids:
                return []
            q += " WHERE c.source_id IN (%s)" % ",".join("?" * len(source_ids))
            args = list(source_ids)
        with self._lock:
            return self._db.execute(q + " ORDER BY c.source_id, c.id", args).fetchall()

    def search(self, query: str, qvec, source_ids: list[str] | None, k: int = 6) -> list[Chunk]:
        """Best chunks by cosine similarity; chunks lacking a vector fall back to keyword overlap."""
        qv = _normalize(qvec) if qvec is not None else None
        qwords = set(_WORD.findall(query.lower()))
        scored = []
        for sid, name, label, text, blob in self._rows(source_ids):
            if qv is not None and blob:
                v = np.frombuffer(blob, dtype=np.float32)
                score = float(v @ qv) if v.shape == qv.shape else 0.0
            else:
                words = set(_WORD.findall(text.lower()))
                score = 0.5 * len(qwords & words) / (len(qwords) or 1)
            scored.append(Chunk(sid, name, label, text, score))
        scored.sort(key=lambda c: c.score, reverse=True)
        return scored[:k]

    def sample(self, source_ids: list[str] | None, max_chars: int = 12000) -> list[Chunk]:
        """Evenly spread chunks across the chosen sources, in document order, up to max_chars."""
        rows = self._rows(source_ids)
        if not rows:
            return []
        total = sum(len(r[3]) for r in rows)
        step = max(1, -(-total // max_chars))  # take every Nth chunk when over budget
        picked, used = [], 0
        for i, (sid, name, label, text, _) in enumerate(rows):
            if i % step:
                continue
            if used + len(text) > max_chars and picked:
                break
            picked.append(Chunk(sid, name, label, text))
            used += len(text)
        return picked
