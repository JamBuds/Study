# PyInstaller spec - run:  .venv\Scripts\pyinstaller build.spec --noconfirm
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], []
for pkg in ("faster_whisper", "ctranslate2", "rapidocr", "onnxruntime", "av", "tokenizers", "pptx", "docx"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    ["app/main.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + ["app.convert.slides", "app.convert.pdf", "app.convert.word",
                                   "app.convert.captions", "app.convert.media", "app.convert.ocr"],
    excludes=["tkinter", "matplotlib", "pytest"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="StudyBuddy", console=False)
coll = COLLECT(exe, a.binaries, a.datas, name="StudyBuddy")
