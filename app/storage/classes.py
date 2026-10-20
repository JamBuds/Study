"""Class folders: library, history, citation metadata, zip export/import."""
import json
import re
import shutil
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from app.config import data_root

_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
HISTORY_KINDS = {"essay": "Essays", "quiz": "Quizzes", "flashcards": "Flashcards"}


def safe_name(name: str, fallback: str = "Untitled") -> str:
    name = _INVALID.sub("", name or "")
    name = re.sub(r"\s+", " ", name).strip().strip(".")
    return name[:80] or fallback


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class ClassInfo:
    name: str
    teacher: str = ""
    citation_style: str = "MLA"
    created: str = field(default_factory=now)
    last_opened: str = ""


class ClassStore:
    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.sources_dir = self.folder / "Library" / "sources"
        self.text_dir = self.folder / "Library" / "text"
        self.history_dir = self.folder / "History"
        self.index_path = self.folder / "index.db"
        for d in (self.sources_dir, self.text_dir,
                  *(self.history_dir / v for v in HISTORY_KINDS.values())):
            d.mkdir(parents=True, exist_ok=True)

    # ---- class info -------------------------------------------------
    @property
    def name(self) -> str:
        return self.folder.name

    def load_info(self) -> ClassInfo:
        try:
            data = json.loads((self.folder / "class.json").read_text(encoding="utf-8"))
            return ClassInfo(**{k: v for k, v in data.items() if k in ClassInfo.__dataclass_fields__})
        except (OSError, ValueError, TypeError):
            return ClassInfo(name=self.name)

    def save_info(self, info: ClassInfo) -> None:
        (self.folder / "class.json").write_text(json.dumps(asdict(info), indent=2), encoding="utf-8")

    def touch(self) -> None:
        info = self.load_info()
        info.last_opened = now()
        self.save_info(info)

    # ---- library ----------------------------------------------------
    def list_library(self) -> list[str]:
        return sorted(p.stem for p in self.text_dir.glob("*.txt"))

    def _unique(self, name: str) -> str:
        base, n = safe_name(name), 2
        cand = base
        while (self.text_dir / f"{cand}.txt").exists():
            cand = f"{base} ({n})"
            n += 1
        return cand

    def add_library_text(self, name: str, text: str, original: Path | None = None,
                         replace: bool = False) -> str:
        name = safe_name(name) if replace else self._unique(name)
        (self.text_dir / f"{name}.txt").write_text(text, encoding="utf-8")
        if original and Path(original).is_file():
            shutil.copy2(original, self.sources_dir / f"{name}{Path(original).suffix}")
        return name

    def read_library_text(self, name: str) -> str:
        return (self.text_dir / f"{name}.txt").read_text(encoding="utf-8", errors="replace")

    def delete_library(self, name: str) -> None:
        (self.text_dir / f"{name}.txt").unlink(missing_ok=True)
        for p in self.sources_dir.glob(f"{name}.*"):
            if p.stem == name:
                p.unlink(missing_ok=True)
        meta = self.load_metadata()
        if meta.pop(name, None) is not None:
            self.save_metadata(meta)

    def load_metadata(self) -> dict:
        try:
            return json.loads((self.folder / "sources.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def save_metadata(self, meta: dict) -> None:
        (self.folder / "sources.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    # ---- history ----------------------------------------------------
    def _history_target(self, kind: str, hid: str) -> Path:
        base = self.history_dir / HISTORY_KINDS[kind]
        return base / hid / "essay.json" if kind == "essay" else base / f"{hid}.json"

    def new_history_id(self, kind: str, title: str) -> str:
        stem = f"{datetime.now():%Y-%m-%d}_{safe_name(title)}"
        hid, n = stem, 2
        while self._history_target(kind, hid).exists():
            hid = f"{stem} ({n})"
            n += 1
        return hid

    def save_history(self, kind: str, hid: str, data: dict) -> None:
        path = self._history_target(kind, hid)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        if kind == "essay":  # human-readable copies next to the json
            for key in ("outline", "draft", "feedback"):
                if data.get(key):
                    (path.parent / f"{key}.md").write_text(data[key], encoding="utf-8")

    def load_history(self, kind: str, hid: str) -> dict:
        return json.loads(self._history_target(kind, hid).read_text(encoding="utf-8"))

    def list_history(self, kind: str) -> list[dict]:
        base = self.history_dir / HISTORY_KINDS[kind]
        items = []
        for p in base.iterdir():
            f = p / "essay.json" if p.is_dir() else p
            if not f.is_file() or f.suffix != ".json":
                continue
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            hid = p.name if p.is_dir() else p.stem
            items.append({"kind": kind, "id": hid, "title": data.get("title") or hid,
                          "date": data.get("updated") or data.get("created") or ""})
        return sorted(items, key=lambda i: i["date"], reverse=True)

    def delete_history(self, kind: str, hid: str) -> None:
        path = self._history_target(kind, hid)
        if kind == "essay":
            shutil.rmtree(path.parent, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)


# ---- class management ----------------------------------------------------
def list_classes() -> list[ClassInfo]:
    out = []
    for p in (data_root() / "Classes").iterdir():
        if p.is_dir():
            info = ClassStore(p).load_info()
            info.name = p.name
            out.append(info)
    return sorted(out, key=lambda c: (c.last_opened or c.created), reverse=True)


def open_class(name: str) -> ClassStore:
    folder = data_root() / "Classes" / name
    if not folder.is_dir():
        raise FileNotFoundError(name)
    store = ClassStore(folder)
    store.touch()
    return store


def create_class(name: str, teacher: str = "", citation_style: str = "MLA") -> ClassStore:
    clean = safe_name(name, "")
    if not clean:
        raise ValueError("Please enter a class name.")
    folder = data_root() / "Classes" / clean
    if folder.exists():
        raise FileExistsError(f'A class named "{clean}" already exists.')
    store = ClassStore(folder)
    store.save_info(ClassInfo(name=clean, teacher=teacher, citation_style=citation_style,
                              last_opened=now()))
    return store


def delete_class(name: str) -> None:
    shutil.rmtree(data_root() / "Classes" / name, ignore_errors=True)


def export_class(store: ClassStore, zip_path: Path) -> None:
    """Zip a class (library + history; the search index is rebuilt on import)."""
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p in store.folder.rglob("*"):
            if p.is_file() and p.name != "index.db":
                z.write(p, Path(store.name) / p.relative_to(store.folder))


def import_class(zip_path: Path) -> str:
    with zipfile.ZipFile(zip_path) as z:
        tops = {n.split("/")[0] for n in z.namelist() if n.strip("/")}
        if len(tops) != 1:
            raise ValueError("This zip doesn't look like an exported StudyBuddy class.")
        base = safe_name(tops.pop())
        name, n = base, 2
        while (data_root() / "Classes" / name).exists():
            name = f"{base} ({n})"
            n += 1
        dest = data_root() / "Classes" / name
        for member in z.infolist():
            if member.is_dir():
                continue
            rel = Path(*Path(member.filename).parts[1:])
            target = (dest / rel).resolve()
            if dest.resolve() not in target.parents:  # zip-slip guard
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(z.read(member))
    store = ClassStore(dest)
    info = store.load_info()
    info.name = name
    store.save_info(info)
    return name
