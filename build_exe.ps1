$ErrorActionPreference = 'Stop'

$python = (Get-Command python -ErrorAction Stop).Source
$venv = Join-Path $PSScriptRoot '.venv-build'

if (-not (Test-Path (Join-Path $venv 'Scripts\python.exe'))) {
    & $python -m venv $venv
}

& (Join-Path $venv 'Scripts\python.exe') -m pip install --disable-pip-version-check --upgrade pip
& (Join-Path $venv 'Scripts\python.exe') -m pip install --disable-pip-version-check pyinstaller pywebview

& (Join-Path $venv 'Scripts\pyinstaller.exe') --noconfirm --clean --onefile --name CodexQuotaReport --collect-all webview --add-data "codex_quota\web;codex_quota\web" (Join-Path $PSScriptRoot 'run.py')

Write-Host ''
Write-Host 'Build complete:'
Write-Host (Join-Path $PSScriptRoot 'dist\CodexQuotaReport.exe')

$desktop = [Environment]::GetFolderPath('Desktop')
$lnkPath = Join-Path $desktop 'CodexQuotaReport.lnk'
$ws = New-Object -ComObject WScript.Shell
$shortcut = $ws.CreateShortcut($lnkPath)
$shortcut.TargetPath = Join-Path $PSScriptRoot 'dist\CodexQuotaReport.exe'
$shortcut.WorkingDirectory = Join-Path $PSScriptRoot 'dist'
$shortcut.Description = 'Codex Quota Client'
$shortcut.Save()
Write-Host "Desktop shortcut: $lnkPath"
