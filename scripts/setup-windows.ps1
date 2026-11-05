$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
py -3.11 -m venv .venv
if ($LASTEXITCODE -ne 0) { throw '請先安裝 Python 3.11（含 Tcl/Tk 與 py launcher）' }
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw '依賴安裝失敗' }
& .\.venv\Scripts\python.exe -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw '測試失敗，請查看上方輸出' }
Write-Host '完成。執行 scripts\start-windows.ps1，再於 VoiceChange 選擇 AI 引擎。'
