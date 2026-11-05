@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo Python environment not found. Run setup first. See README.md.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install -r requirements-build.txt
if errorlevel 1 goto fail
".venv\Scripts\python.exe" -m unittest discover -s tests -v
if errorlevel 1 goto fail
".venv\Scripts\python.exe" -m PyInstaller --noconfirm VoiceChange.spec
if errorlevel 1 goto fail
powershell.exe -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([IO.Path]::Combine([Environment]::GetFolderPath('Desktop'),'VoiceChange.lnk')); $s.TargetPath=[IO.Path]::GetFullPath('dist\VoiceChange\VoiceChange.exe'); $s.WorkingDirectory=[IO.Path]::GetFullPath('dist\VoiceChange'); $s.Save()"
if errorlevel 1 goto fail
echo Done! Open VoiceChange from your desktop shortcut.
pause
exit /b 0
:fail
echo Build failed. See the messages above.
pause
exit /b 1
