$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (!(Test-Path .\.venv\Scripts\python.exe)) { throw '請先執行 scripts\setup-windows.ps1' }
& .\.venv\Scripts\python.exe -m voice_changer.app
if ($LASTEXITCODE -ne 0) { throw '程式結束異常，請查看上方輸出' }
