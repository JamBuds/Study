import zipfile

import pytest

from app.ai.ollama_client import OllamaClient, OllamaError, _ThinkFilter, parse_json
from app.knowledge import Knowledge
from app.storage import classes as C
from app.storage.index import Index, chunk_text


# ---- storage ------------------------------------------------------------------
def test_class_lifecycle_and_library():
    store = C.create_class("AP Bio / Period 3", "Ms. Lee", "APA")
    assert store.name == "AP Bio Period 3"
    with pytest.raises(FileExistsError):
        C.create_class("AP Bio Period 3")
    with pytest.raises(ValueError):
        C.create_class("???")
    name = store.add_library_text("Lecture 1", "hello world")
    assert store.add_library_text("Lecture 1", "again") == "Lecture 1 (2)"
    assert store.read_library_text(name) == "hello world"
    assert [c.name for c in C.list_classes()] == ["AP Bio Period 3"]
    assert C.list_classes()[0].citation_style == "APA"
    store.delete_library(name)
    assert store.list_library() == ["Lecture 1 (2)"]


def test_history_roundtrip():
    store = C.create_class("History")
    hid = store.new_history_id("essay", "Causes of WWI")
    store.save_history("essay", hid, {"title": "Causes of WWI", "outline": "# Intro", "updated": "2026-01-02"})
    qid = store.new_history_id("quiz", "Quiz 1")
    store.save_history("quiz", qid, {"title": "Quiz 1", "updated": "2026-01-03"})
    assert (store.history_dir / "Essays" / hid / "outline.md").read_text() == "# Intro"
    assert [i["title"] for i in store.list_history("essay")] == ["Causes of WWI"]
    assert store.load_history("quiz", qid)["title"] == "Quiz 1"
    store.delete_history("essay", hid)
    assert store.list_history("essay") == []


def test_export_import_and_zip_slip(tmp_path):
    store = C.create_class("Chem")
    store.add_library_text("Notes", "moles")
    z = tmp_path / "chem.zip"
    C.export_class(store, z)
    assert C.import_class(z) == "Chem (2)"
    assert C.open_class("Chem (2)").read_library_text("Notes") == "moles"
    evil = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil, "w") as f:
        f.writestr("Evil/ok.txt", "x")
        f.writestr("Evil/../../escaped.txt", "x")
    C.import_class(evil)
    assert not (tmp_path / "escaped.txt").exists()
    assert not (C.data_root().parent / "escaped.txt").exists()


# ---- chunking & search ---------------------------------------------------------
def test_chunking_labels_and_overlap():
    text = "[Slide 1]\nIntro to cells\n\n[Slide 2]\n" + "\n\n".join(f"Paragraph {i} " + "x" * 500 for i in range(12))
    chunks = chunk_text(text, size=1500, overlap=100)
    assert len(chunks) > 2
    assert chunks[0][0] == "Slide 1"
    assert all(len(c[1]) < 2200 for c in chunks)
    assert any(c[0] == "Slide 2" for c in chunks)
    assert chunk_text("") == []


def test_index_keyword_and_vector_search(tmp_path):
    idx = Index(tmp_path / "i.db")
    idx.add_source("a", "library", "Cells", [("", "mitochondria make ATP energy")], [[1, 0, 0]])
    idx.add_source("b", "library", "Wars", [("", "the treaty ended the war")], [[0, 1, 0]])
    assert idx.search("x", [0.9, 0.1, 0], None, 1)[0].source_name == "Cells"
    kw = Index(tmp_path / "k.db")
    kw.add_source("a", "library", "Cells", [("", "mitochondria make ATP energy")])
    kw.add_source("b", "library", "Wars", [("", "the treaty ended the war")])
    assert kw.search("what does the mitochondria do", None, None, 1)[0].source_name == "Cells"
    assert kw.search("war treaty", None, ["a"], 5)[0].source_name == "Cells"  # restricted to chosen sources
    assert kw.search("anything", None, [], 5) == []
    assert len(kw.sample(None, 10_000)) == 2


def test_knowledge_sync_and_retrieval(settings):
    store = C.create_class("Bio")
    store.add_library_text("Dropped in by hand", "ribosomes build proteins")
    k = Knowledge(store, OllamaClient(settings.ollama_url), settings)
    assert k.sync_library() == 1
    assert k.sync_library() == 0
    k.add_to_library("Notes", "[Slide 2]\nmitochondria make ATP")
    hits = k.retrieve("mitochondria ATP", [k.library_id("Notes")])
    assert hits and hits[0].citation == "Notes - Slide 2"
    k.remove_from_library("Notes")
    assert [s["name"] for s in k.all_sources()] == ["Dropped in by hand"]


def test_knowledge_falls_back_without_ollama(settings):
    store = C.create_class("Offline")
    k = Knowledge(store, OllamaClient("http://127.0.0.1:9"), settings)
    k.add_to_library("Notes", "mitochondria make ATP")
    assert k.embeddings_ok is False
    assert k.retrieve("ATP", None)[0].source_name == "Notes"


# ---- ollama client -------------------------------------------------------------
def test_client_basics(ollama_url):
    c = OllamaClient(ollama_url)
    assert c.health()
    assert c.has_model("fake-chat") and c.has_model("nomic-embed-text:latest")
    assert not OllamaClient("http://127.0.0.1:9").health()
    assert c.chat("fake-chat", [{"role": "user", "content": "hi"}]) == "Here is a helpful answer [Bio notes - Slide 2]."
    assert len(c.embed("nomic-embed-text", ["a", "b"])) == 2
    progress = list(c.pull("fake-chat"))
    assert progress[-1]["status"] == "success"


def test_client_errors(ollama_url):
    with pytest.raises(OllamaError, match="isn't downloaded"):
        OllamaClient(ollama_url).chat("missing", [{"role": "user", "content": "hi"}])
    with pytest.raises(OllamaError, match="Can't reach Ollama"):
        OllamaClient("http://127.0.0.1:9").list_models()


def test_think_filter_and_json():
    f = _ThinkFilter()
    out = "".join(f.feed(p) for p in ["<thi", "nk>secret</th", "ink>Answer ", "1 < 2"]) + f.flush()
    assert out == "Answer 1 < 2"
    assert parse_json('Sure!\n```json\n{"a": 1}\n```') == {"a": 1}
    with pytest.raises(OllamaError):
        parse_json("no json here")
