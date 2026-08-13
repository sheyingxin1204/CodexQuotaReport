$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $root '.venv-build'
if (-not (Test-Path (Join-Path $venv 'Scripts\python.exe'))) {
    & (Get-Command python).Source -m venv $venv
}

& (Join-Path $venv 'Scripts\python.exe') -m pip install --disable-pip-version-check --upgrade pip
& (Join-Path $venv 'Scripts\python.exe') -m pip install --disable-pip-version-check pyinstaller pywebview pystray pillow
& (Join-Path $venv 'Scripts\python.exe') (Join-Path $root 'scripts\generate_icon.py')

& (Join-Path $venv 'Scripts\pyinstaller.exe') `
    --noconfirm `
    --clean `
    --onedir `
    --name QuotaSelfCheck `
    --icon (Join-Path $root 'build\icon.ico') `
    --version-file (Join-Path $root 'scripts\version_info.txt') `
    --collect-all webview `
    --add-data "quota_check\web;quota_check\web" `
    (Join-Path $root 'run.py')

$iscc = Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'
if (-not (Test-Path $iscc)) {
    $candidates = Get-ChildItem 'C:\Program Files (x86)\Inno Setup*','C:\Program Files\Inno Setup*' -Filter ISCC.exe -ErrorAction SilentlyContinue
    $iscc = $candidates | Select-Object -First 1 -ExpandProperty FullName
}
if (-not $iscc -or -not (Test-Path $iscc)) {
    throw 'Inno Setup ISCC.exe not found. Install Inno Setup 6 first.'
}

Push-Location (Join-Path $root 'scripts')
try {
    & $iscc (Join-Path $root 'scripts\setup.iss')
    if ($LASTEXITCODE -ne 0) {
        throw "Inno Setup failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

Write-Host ''
Write-Host 'Setup build complete:'
Write-Host (Join-Path $root 'dist\QuotaSelfCheck-Setup.exe')
