$ErrorActionPreference = 'Stop'

$python = (Get-Command python -ErrorAction Stop).Source
$venv = Join-Path $PSScriptRoot '.venv-build'

if (-not (Test-Path (Join-Path $venv 'Scripts\python.exe'))) {
    & $python -m venv $venv
}

& (Join-Path $venv 'Scripts\python.exe') -m pip install --disable-pip-version-check --upgrade pip
& (Join-Path $venv 'Scripts\python.exe') -m pip install --disable-pip-version-check pyinstaller pywebview pillow

& (Join-Path $venv 'Scripts\python.exe') (Join-Path $PSScriptRoot 'scripts\generate_icon.py')

& (Join-Path $venv 'Scripts\pyinstaller.exe') `
    --noconfirm `
    --clean `
    --onefile `
    --name CodexQuota `
    --icon (Join-Path $PSScriptRoot 'build\icon.ico') `
    --version-file (Join-Path $PSScriptRoot 'scripts\version_info.txt') `
    --collect-all webview `
    --add-data "codex_quota\web;codex_quota\web" `
    (Join-Path $PSScriptRoot 'run.py')

Write-Host ''
Write-Host 'Build complete:'
Write-Host (Join-Path $PSScriptRoot 'dist\CodexQuota.exe')

$desktop = [Environment]::GetFolderPath('Desktop')
$cn = [string][char]0x989D + [string][char]0x5EA6 + [string][char]0x7BA1 + [string][char]0x5BB6
$lnkPath = Join-Path $desktop ('Codex' + $cn + '.lnk')
$ws = New-Object -ComObject WScript.Shell
$shortcut = $ws.CreateShortcut($lnkPath)
$shortcut.TargetPath = Join-Path $PSScriptRoot 'dist\CodexQuota.exe'
$shortcut.WorkingDirectory = Join-Path $PSScriptRoot 'dist'
$shortcut.Description = 'Codex Quota Desktop Client'
$shortcut.Save()
Write-Host "Desktop shortcut: $lnkPath"
