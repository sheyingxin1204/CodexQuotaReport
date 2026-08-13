param(
    [Parameter(Mandatory)]
    [string]$ExePath,
    [string]$Thumbprint,
    [string]$CertificatePath,
    [string]$Password,
    [string]$TimestampUrl = "http://timestamp.digicert.com"
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $ExePath)) {
    throw "EXE not found: $ExePath"
}

$signtool = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin" -Recurse -Filter signtool.exe -ErrorAction SilentlyContinue |
    Sort-Object FullName -Descending | Select-Object -First 1 -ExpandProperty FullName
if (-not $signtool) {
    throw "signtool.exe not found. Install Windows SDK or pass SigntoolPath."
}

if ($Thumbprint) {
    & $signtool sign /fd SHA256 /tr $TimestampUrl /td SHA256 /sha1 $Thumbprint $ExePath
}
elseif ($CertificatePath) {
    $signArgs = @('sign', '/fd', 'SHA256', '/tr', $TimestampUrl, '/td', 'SHA256')
    if ($Password) {
        $signArgs += @('/p', $Password)
    }
    $signArgs += @($CertificatePath, $ExePath)
    & $signtool @signArgs
}
else {
    throw "Provide -Thumbprint or -CertificatePath."
}

if ($LASTEXITCODE -eq 0) {
    Write-Host "Signed: $ExePath"
}
else {
    throw "Signing failed with exit code $LASTEXITCODE"
}
