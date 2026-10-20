@echo off
cd /d "%~dp0"
.venv\Scripts\pyinstaller build.spec --noconfirm || exit /b 1
where iscc >nul 2>nul && iscc installer.iss || echo Inno Setup not found: share the dist\StudyBuddy folder as a zip instead.
