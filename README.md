# StudyBuddy

A private homework helper for Windows. Everything runs on your own PC: the AI is a local
[Ollama](https://ollama.com) model, so nothing you type leaves your computer.

## For friends (using the app)

1. Install **Ollama** from <https://ollama.com/download> and open it once.
2. Install StudyBuddy (run `StudyBuddy-Setup.exe`, or unzip the `StudyBuddy` folder and run `StudyBuddy.exe`).
3. On first launch the setup screen checks Ollama and lets you click **Download chat model** and
   **Download search model** (a few GB, one time). On an older laptop choose a smaller one such as `llama3.2:3b` as the chat model.
4. Create a class, then pick **Essay help**, **Quiz help** or **Convert to text**.

Your files live in `Documents\StudyBuddy\Classes\<Class>\`:

```
Library\sources   original files you added
Library\text      plain-text versions the AI reads (drop .txt files here too)
History\          past essays, quizzes, flashcard decks
```

### What it does

- **Essay help** - thesis ideas, outline, section-by-section draft, feedback on your own draft, Works Cited
  (MLA/APA/Chicago). Export to Word.
- **Quiz help** - practice quizzes (multiple choice, true/false, short answer) with grading and explanations,
  "explain this question", flashcards, study guides.
- **Convert to text** - PowerPoint, PDF (scanned pages via OCR), Word, .srt/.vtt captions, audio/video
  (local Whisper) and images to plain text. Save to the class library or a .txt file.
- **Learning mode** (Settings, on by default) makes the AI explain its reasoning so you learn the material.
  Always check AI answers against your sources and follow your teacher's rules on AI use.
- Share a class with a classmate via **Export class** / **Import class**.

## For the developer

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest          # uses a fake Ollama server, no models needed
run.bat                                 # run from source
build.bat                               # PyInstaller (dist\StudyBuddy) + Inno Setup installer if iscc is on PATH
```

Layout: `app/storage` (class folders, SQLite index), `app/ai` (Ollama client, prompts, Qt workers),
`app/convert` (one module per file type), `app/tools` (essay and quiz logic), `app/ui` (PySide6 screens).
Set `STUDYBUDDY_HOME` to relocate the data folder.
