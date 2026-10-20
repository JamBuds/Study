"""Ties a class's files, its search index and Ollama together."""
from typing import Callable, Iterator

from app.ai.ollama_client import OllamaClient, OllamaError
from app.config import Settings
from app.storage.classes import ClassStore
from app.storage.index import Chunk, Index, chunk_text

EMBED_BATCH = 16


class Knowledge:
    def __init__(self, store: ClassStore, client: OllamaClient, settings: Settings):
        self.store, self.client, self.settings = store, client, settings
        self.index = Index(store.index_path)
        self.embeddings_ok = True

    # ---- ids --------------------------------------------------------
    @staticmethod
    def library_id(name: str) -> str:
        return f"lib:{name}"

    @staticmethod
    def history_id(kind: str, hid: str) -> str:
        return f"hist:{kind}:{hid}"

    # ---- embeddings -------------------------------------------------
    def embed(self, texts: list[str]) -> list | None:
        """Embeddings for texts, or None if Ollama/the model isn't available (keyword search is used)."""
        if not texts or not self.embeddings_ok:
            return None
        out = []
        try:
            for i in range(0, len(texts), EMBED_BATCH):
                out += self.client.embed(self.settings.embed_model, texts[i:i + EMBED_BATCH])
            return out
        except (OllamaError, KeyError):
            self.embeddings_ok = False
            return None

    def retry_embeddings(self) -> None:
        self.embeddings_ok = True

    # ---- adding content --------------------------------------------
    def add_document(self, source_id: str, kind: str, name: str, text: str) -> None:
        chunks = chunk_text(text)
        vectors = self.embed([c[1] for c in chunks])
        self.index.add_source(source_id, kind, name, chunks, vectors)

    def add_to_library(self, name: str, text: str, original=None) -> str:
        saved = self.store.add_library_text(name, text, original)
        self.add_document(self.library_id(saved), "library", saved, text)
        return saved

    def remove_from_library(self, name: str) -> None:
        self.store.delete_library(name)
        self.index.remove_source(self.library_id(name))

    def add_history(self, kind: str, hid: str, title: str, text: str) -> None:
        if text.strip():
            self.add_document(self.history_id(kind, hid), "history", f"{kind.title()}: {title}", text)

    def remove_history(self, kind: str, hid: str) -> None:
        self.index.remove_source(self.history_id(kind, hid))

    def sync_library(self, report: Callable[[str], None] | None = None) -> int:
        """Index library files that aren't indexed yet (e.g. dropped into the folder by hand)."""
        on_disk = set(self.store.list_library())
        for s in self.index.sources("library"):
            if s["name"] not in on_disk:
                self.index.remove_source(s["id"])
        added = 0
        for name in sorted(on_disk):
            if not self.index.has_source(self.library_id(name)):
                if report:
                    report(f"Indexing {name}...")
                self.add_document(self.library_id(name), "library", name, self.store.read_library_text(name))
                added += 1
        return added

    def reindex_all(self, report: Callable[[str], None] | None = None) -> None:
        """Rebuild vectors (e.g. after the embedding model changed or came online)."""
        self.retry_embeddings()
        for name in self.store.list_library():
            if report:
                report(f"Indexing {name}...")
            self.add_document(self.library_id(name), "library", name, self.store.read_library_text(name))

    # ---- querying ---------------------------------------------------
    def all_sources(self) -> list[dict]:
        return self.index.sources()

    def retrieve(self, query: str, source_ids: list[str] | None, k: int = 6) -> list[Chunk]:
        if source_ids is not None and not source_ids:
            return []
        qvec = None
        vecs = self.embed([query[:2000]])
        if vecs:
            qvec = vecs[0]
        return self.index.search(query, qvec, source_ids, k)

    def sample(self, source_ids: list[str] | None, max_chars: int = 12000) -> list[Chunk]:
        return self.index.sample(source_ids, max_chars)

    def chat_options(self) -> dict:
        return {"num_ctx": self.settings.num_ctx}
