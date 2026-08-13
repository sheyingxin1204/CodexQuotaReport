[CmdletBinding()]
param(
    [string]$ProfilePath = (Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'WindowsPowerShell\Microsoft.PowerShell_profile.ps1'),
    [string]$OutputDir,
    [switch]$SkipStatusRefresh,
    [switch]$PassThru
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($OutputDir)) {
    $OutputDir = [Environment]::GetFolderPath('Desktop')
}

function Resolve-CodexPath {
    param(
        [Parameter(Mandatory)]
        [string]$PathText
    )

    $resolved = [Environment]::ExpandEnvironmentVariables($PathText)
    $resolved = $resolved.Replace('$HOME', $HOME)
    $resolved = $resolved.Replace('${HOME}', $HOME)

    if ($resolved.StartsWith('~')) {
        $resolved = Join-Path $HOME $resolved.Substring(1).TrimStart('\', '/')
    }

    return $resolved
}

function Get-OptionalPropertyValue {
    param(
        $InputObject,
        [Parameter(Mandatory)]
        [string[]]$Names
    )

    if ($null -eq $InputObject) {
        return $null
    }

    foreach ($name in $Names) {
        $property = $InputObject.PSObject.Properties[$name]
        if ($null -ne $property) {
            return $property.Value
        }
    }

    return $null
}

function Convert-UnixTime {
    param(
        [AllowNull()]
        [Nullable[long]]$Value
    )

    if ($null -eq $Value) {
        return $null
    }

    return [DateTimeOffset]::FromUnixTimeSeconds($Value)
}

function Get-RemainingPercent {
    param([AllowNull()]$UsedPercent)

    if ($null -eq $UsedPercent) {
        return $null
    }

    $remaining = 100 - [double]$UsedPercent
    if ($remaining -lt 0) { $remaining = 0 }
    if ($remaining -gt 100) { $remaining = 100 }
    return [math]::Round($remaining, 2)
}

function Format-PercentText {
    param([AllowNull()]$Value)

    if ($null -eq $Value) {
        return ''
    }

    return ('{0}%' -f ([math]::Round([double]$Value, 2).ToString('0.##')))
}

function Format-DateText {
    param([AllowNull()]$Value)

    if ($null -eq $Value) {
        return ''
    }

    return ([datetime]$Value).ToString('yyyy-MM-dd')
}

function Format-DateTimeMinuteText {
    param([AllowNull()]$Value)

    if ($null -eq $Value) {
        return ''
    }

    return ([datetime]$Value).ToString('yyyy-MM-dd HH:mm')
}

function Convert-CodesToText {
    param(
        [Parameter(Mandatory)]
        [int[]]$Codes
    )

    return -join ($Codes | ForEach-Object { [char]$_ })
}

function Get-UiText {
    param(
        [Parameter(Mandatory)]
        [ValidateSet(
            'ReportFileBase',
            'SheetName',
            'ReportTitle',
            'UpdatedOnTitle',
            'HeaderEmail',
            'HeaderPlanType',
            'HeaderShortcut',
            'HeaderWeeklyRemaining',
            'HeaderWeeklyReset',
            'HeaderFiveHourRemaining',
            'HeaderFiveHourReset',
            'HeaderUpdatedOn',
            'ExcelComUnavailable'
        )]
        [string]$Key
    )

    $map = @{
        ReportFileBase          = @(99,111,100,101,120,39069,24230)
        SheetName               = @(39069,24230,24635,35272)
        ReportTitle             = @(67,111,100,101,120,32,36134,21495,39069,24230,24635,35272)
        UpdatedOnTitle          = @(26356,26032,26102,38388,58,32)
        HeaderEmail             = @(36134,21495,37038,31665)
        HeaderPlanType          = @(36134,21495,32,112,108,97,110,32,31867,22411)
        HeaderShortcut          = @(24555,25463,21629,20196)
        HeaderWeeklyRemaining   = @(21608,39069,24230,21097,20313,39069,24230,30334,20998,27604)
        HeaderWeeklyReset       = @(21608,39069,24230,37325,32622,26102,38388)
        HeaderFiveHourRemaining = @(53,23567,26102,21047,26032,39069,24230,21097,20313,30334,20998,27604)
        HeaderFiveHourReset     = @(53,23567,26102,21047,26032,39069,24230,37325,32622,26102,38388)
        HeaderUpdatedOn         = @(26356,26032,26102,38388)
        ExcelComUnavailable     = @(69,120,99,101,108,32,67,79,77,32,19981,21487,29992,65292,26412,27425,21482,23548,20986,20102,32,67,83,86,12290)
    }

    return Convert-CodesToText -Codes $map[$Key]
}

function New-EmptyRateLimitRecord {
    param(
        [Parameter(Mandatory)]
        [pscustomobject]$ShortcutInfo,
        [Parameter(Mandatory)]
        [string]$Status,
        [string]$Email,
        [string]$PlanType,
        [Parameter(Mandatory)]
        [string]$SourcePath,
        [Parameter(Mandatory)]
        [string]$ErrorMessage
    )

    [pscustomobject]@{
        Shortcut                 = $ShortcutInfo.Shortcut
        CodeHome                 = $ShortcutInfo.CodeHome
        Email                    = $Email
        PlanType                 = $PlanType
        Status                   = $Status
        SnapshotLoggedAtLocal    = $null
        WeeklyRemainingPercent   = $null
        WeeklyWindowMinutes      = $null
        WeeklyResetAtLocal       = $null
        FiveHourRemainingPercent = $null
        FiveHourWindowMinutes    = $null
        FiveHourResetAtLocal     = $null
        SourcePath               = $SourcePath
        Error                    = $ErrorMessage
    }
}

function Get-CodexShortcutsFromProfile {
    param(
        [Parameter(Mandatory)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Profile file not found: $Path"
    }

    $content = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
    $items = @()

    $helperPattern = '(?m)^\s*function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\{\s*Invoke-CodexHome\s+["'']([^"'']+)["'']'
    foreach ($match in [regex]::Matches($content, $helperPattern, [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)) {
        $items += [pscustomobject]@{
            Shortcut = $match.Groups[1].Value
            CodeHome = Resolve-CodexPath -PathText $match.Groups[2].Value
        }
    }

    $functionBlockPattern = '(?ms)^\s*function\s+(?<name>[A-Za-z_][A-Za-z0-9_]*)\s*\{(?<body>.*?)^\s*\}'
    foreach ($match in [regex]::Matches($content, $functionBlockPattern, [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)) {
        $body = $match.Groups['body'].Value
        $codeHomeMatch = [regex]::Match($body, '\$env:CODEX_HOME\s*=\s*["'']([^"'']+)["'']', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
        if ($codeHomeMatch.Success -and $body -match '\bcodex\b') {
            $items += [pscustomobject]@{
                Shortcut = $match.Groups['name'].Value
                CodeHome = Resolve-CodexPath -PathText $codeHomeMatch.Groups[1].Value
            }
        }
    }

    $items | Sort-Object Shortcut -Unique
}

function Invoke-CodexStatusRefresh {
    param(
        [Parameter(Mandatory)]
        [pscustomobject]$ShortcutInfo
    )

    $powerShellExe = [string](Get-Command powershell.exe -ErrorAction Stop).Source
    $codeHome = [string]$ShortcutInfo.CodeHome
    $homePath = [string]$HOME
    $escapedCodeHome = $codeHome.Replace("'", "''")
    $escapedHomePath = $homePath.Replace("'", "''")
    $command = ('$env:CODEX_HOME = ''{0}''; codex exec --skip-git-repo-check -C ''{1}'' --json "/status"' -f $escapedCodeHome, $escapedHomePath)

    $success = $false
    $output = $null
    try {
        $outputLines = & $powerShellExe -NoProfile -Command $command 2>&1
        $output = ((@($outputLines) | ForEach-Object { [string]$_ }) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }) -join [Environment]::NewLine
        $success = ($LASTEXITCODE -eq 0 -or $output -like '*Reading additional input from stdin...*')
    }
    catch {
        $success = $false
        $output = [string]$_.Exception.Message
    }

    [pscustomobject]@{
        Shortcut  = $ShortcutInfo.Shortcut
        CodeHome  = $ShortcutInfo.CodeHome
        Refreshed = $success
        Output    = ($output | Out-String).Trim()
    }
}

function Get-TokenPayloadObject {
    param(
        [AllowNull()]
        [string]$Token
    )

    if ([string]::IsNullOrWhiteSpace($Token)) {
        return $null
    }

    $parts = $Token -split '\.'
    if ($parts.Count -lt 2) {
        return $null
    }

    $payloadText = $parts[1].Replace('-', '+').Replace('_', '/')
    switch ($payloadText.Length % 4) {
        2 { $payloadText += '==' }
        3 { $payloadText += '=' }
    }

    try {
        $jsonText = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($payloadText))
        return $jsonText | ConvertFrom-Json
    }
    catch {
        return $null
    }
}

function Get-LatestRateLimitRecord {
    param(
        [Parameter(Mandatory)]
        [pscustomobject]$ShortcutInfo
    )

    $authPath = Join-Path $ShortcutInfo.CodeHome 'auth.json'
    $email = $null
    $planTypeAuth = $null

    if (Test-Path -LiteralPath $authPath) {
        $auth = Get-Content -LiteralPath $authPath -Raw -Encoding UTF8 | ConvertFrom-Json
        foreach ($payload in @(
            (Get-TokenPayloadObject -Token (Get-OptionalPropertyValue -InputObject $auth.tokens -Names @('access_token'))),
            (Get-TokenPayloadObject -Token (Get-OptionalPropertyValue -InputObject $auth.tokens -Names @('id_token')))
        )) {
            if ($null -eq $payload) {
                continue
            }

            if (-not $email) {
                $profile = Get-OptionalPropertyValue -InputObject $payload -Names @('https://api.openai.com/profile')
                $email = Get-OptionalPropertyValue -InputObject $profile -Names @('email')
                if (-not $email) {
                    $email = Get-OptionalPropertyValue -InputObject $payload -Names @('email')
                }
            }

            if (-not $planTypeAuth) {
                $authSection = Get-OptionalPropertyValue -InputObject $payload -Names @('https://api.openai.com/auth')
                $planTypeAuth = Get-OptionalPropertyValue -InputObject $authSection -Names @('chatgpt_plan_type')
            }
        }
    }

    $sessionsRoot = Join-Path $ShortcutInfo.CodeHome 'sessions'
    if (-not (Test-Path -LiteralPath $sessionsRoot)) {
        return New-EmptyRateLimitRecord -ShortcutInfo $ShortcutInfo -Status 'NoRateLimitEvent' -Email $email -PlanType $planTypeAuth -SourcePath $sessionsRoot -ErrorMessage 'sessions directory not found.'
    }

    $sessionFiles = Get-ChildItem -LiteralPath $sessionsRoot -Recurse -File -Filter '*.jsonl' -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending

    $snapshot = $null
    $sourcePath = $sessionsRoot

    foreach ($file in $sessionFiles) {
        $sourcePath = $file.FullName
        $lines = Get-Content -LiteralPath $file.FullName -Encoding UTF8
        for ($index = $lines.Count - 1; $index -ge 0; $index--) {
            $line = $lines[$index].Trim()
            if ([string]::IsNullOrWhiteSpace($line)) {
                continue
            }

            try {
                $item = $line | ConvertFrom-Json
            }
            catch {
                continue
            }

            if ((Get-OptionalPropertyValue -InputObject $item -Names @('type')) -ne 'event_msg') {
                continue
            }

            $payload = Get-OptionalPropertyValue -InputObject $item -Names @('payload')
            if ((Get-OptionalPropertyValue -InputObject $payload -Names @('type')) -ne 'token_count') {
                continue
            }

            $rateLimits = Get-OptionalPropertyValue -InputObject $payload -Names @('rate_limits')
            if ($null -eq $rateLimits) {
                continue
            }

            $snapshot = [pscustomobject]@{
                Email         = $email
                PlanTypeAuth  = $planTypeAuth
                PlanTypeEvent = Get-OptionalPropertyValue -InputObject $rateLimits -Names @('plan_type')
                TimestampUtc  = Get-OptionalPropertyValue -InputObject $item -Names @('timestamp')
                Primary       = Get-OptionalPropertyValue -InputObject $rateLimits -Names @('primary')
                Secondary     = Get-OptionalPropertyValue -InputObject $rateLimits -Names @('secondary')
            }
            break
        }

        if ($null -ne $snapshot) {
            break
        }
    }

    if ($null -eq $snapshot) {
        return New-EmptyRateLimitRecord `
            -ShortcutInfo $ShortcutInfo `
            -Status 'NoRateLimitEvent' `
            -Email $email `
            -PlanType $planTypeAuth `
            -SourcePath $sourcePath `
            -ErrorMessage 'No token_count rate-limit event was found in sessions.'
    }

    $loggedAt = if ($snapshot.TimestampUtc) { [DateTimeOffset]::Parse($snapshot.TimestampUtc) } else { $null }
    $planType = if ($snapshot.PlanTypeEvent) { $snapshot.PlanTypeEvent } else { $snapshot.PlanTypeAuth }

    $limits = @()
    foreach ($name in @('Primary', 'Secondary')) {
        $limit = Get-OptionalPropertyValue -InputObject $snapshot -Names @($name)
        if ($null -eq $limit) {
            continue
        }

        $windowMinutes = Get-OptionalPropertyValue -InputObject $limit -Names @('window_minutes')
        $usedPercent = Get-OptionalPropertyValue -InputObject $limit -Names @('used_percent')
        $resetAt = Get-OptionalPropertyValue -InputObject $limit -Names @('resets_at', 'reset_at')

        if ($null -eq $windowMinutes -and $null -eq $usedPercent -and $null -eq $resetAt) {
            continue
        }

        $limits += [pscustomobject]@{
            WindowMinutes    = if ($null -ne $windowMinutes) { [int]$windowMinutes } else { $null }
            UsedPercent      = if ($null -ne $usedPercent) { [double]$usedPercent } else { $null }
            RemainingPercent = Get-RemainingPercent -UsedPercent $usedPercent
            ResetAtLocal     = if ($resetAt) { (Convert-UnixTime -Value $resetAt).ToLocalTime().DateTime } else { $null }
        }
    }

    $weeklyLimit = $limits |
        Where-Object { $null -ne $_.WindowMinutes } |
        Sort-Object WindowMinutes -Descending |
        Select-Object -First 1

    $fiveHourLimit = $limits |
        Where-Object { $_.WindowMinutes -eq 300 } |
        Select-Object -First 1

    [pscustomobject]@{
        Shortcut                 = $ShortcutInfo.Shortcut
        CodeHome                 = $ShortcutInfo.CodeHome
        Email                    = $snapshot.Email
        PlanType                 = $planType
        Status                   = 'OK'
        SnapshotLoggedAtLocal    = if ($loggedAt) { $loggedAt.ToLocalTime().DateTime } else { $null }
        WeeklyRemainingPercent   = if ($weeklyLimit) { $weeklyLimit.RemainingPercent } else { $null }
        WeeklyWindowMinutes      = if ($weeklyLimit) { $weeklyLimit.WindowMinutes } else { $null }
        WeeklyResetAtLocal       = if ($weeklyLimit) { $weeklyLimit.ResetAtLocal } else { $null }
        FiveHourRemainingPercent = if ($fiveHourLimit) { $fiveHourLimit.RemainingPercent } else { $null }
        FiveHourWindowMinutes    = if ($fiveHourLimit) { $fiveHourLimit.WindowMinutes } else { $null }
        FiveHourResetAtLocal     = if ($fiveHourLimit) { $fiveHourLimit.ResetAtLocal } else { $null }
        SourcePath               = $sourcePath
        Error                    = $null
    }
}

function Convert-RowToDisplayRecord {
    param(
        [Parameter(Mandatory)]
        [pscustomobject]$Row
    )

    [pscustomobject]@{
        Email             = if ($Row.Email) { $Row.Email } else { '' }
        PlanType          = if ($Row.PlanType) { $Row.PlanType } else { '' }
        Shortcut          = $Row.Shortcut
        WeeklyRemaining   = Format-PercentText -Value $Row.WeeklyRemainingPercent
        WeeklyResetDate   = Format-DateText -Value $Row.WeeklyResetAtLocal
        FiveHourRemaining = Format-PercentText -Value $Row.FiveHourRemainingPercent
        FiveHourResetDate = Format-DateText -Value $Row.FiveHourResetAtLocal
        UpdatedOn         = Format-DateTimeMinuteText -Value $Row.SnapshotLoggedAtLocal
    }
}

function Clear-OldReportFiles {
    param(
        [Parameter(Mandatory)]
        [string[]]$Directories
    )

    foreach ($directory in $Directories | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique) {
        if (-not (Test-Path -LiteralPath $directory)) {
            continue
        }

        Get-ChildItem -LiteralPath $directory -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Extension -eq '.xlsx' } |
            Remove-Item -Force -ErrorAction SilentlyContinue
    }
}

function Export-ReportExcel {
    param(
        [Parameter(Mandatory)]
        [object[]]$Rows,
        [Parameter(Mandatory)]
        [string]$Directory
    )

    try {
        $excel = New-Object -ComObject Excel.Application
    }
    catch {
        return $null
    }

    if (-not (Test-Path -LiteralPath $Directory)) {
        New-Item -ItemType Directory -Path $Directory | Out-Null
    }

    $xlsxPath = Join-Path $Directory ((Get-UiText -Key 'ReportFileBase') + '.xlsx')
    if (Test-Path -LiteralPath $xlsxPath) {
        Remove-Item -LiteralPath $xlsxPath -Force -ErrorAction SilentlyContinue
    }
    $headers = @(
        [pscustomobject]@{ Label = Get-UiText -Key 'HeaderEmail'; Key = 'Email' },
        [pscustomobject]@{ Label = Get-UiText -Key 'HeaderPlanType'; Key = 'PlanType' },
        [pscustomobject]@{ Label = Get-UiText -Key 'HeaderShortcut'; Key = 'Shortcut' },
        [pscustomobject]@{ Label = Get-UiText -Key 'HeaderWeeklyRemaining'; Key = 'WeeklyRemaining' },
        [pscustomobject]@{ Label = Get-UiText -Key 'HeaderWeeklyReset'; Key = 'WeeklyResetDate' },
        [pscustomobject]@{ Label = Get-UiText -Key 'HeaderFiveHourRemaining'; Key = 'FiveHourRemaining' },
        [pscustomobject]@{ Label = Get-UiText -Key 'HeaderFiveHourReset'; Key = 'FiveHourResetDate' },
        [pscustomobject]@{ Label = Get-UiText -Key 'HeaderUpdatedOn'; Key = 'UpdatedOn' }
    )

    $workbook = $null
    $worksheet = $null

    try {
        $excel.Visible = $false
        $excel.DisplayAlerts = $false
        $workbook = $excel.Workbooks.Add()
        $worksheet = $workbook.Worksheets.Item(1)
        $worksheet.Name = Get-UiText -Key 'SheetName'

        $titleRange = $worksheet.Range('A1:H1')
        $titleRange.Merge()
        $titleRange.Value2 = Get-UiText -Key 'ReportTitle'
        $titleRange.Font.Bold = $true
        $titleRange.Font.Size = 16
        $titleRange.HorizontalAlignment = -4108
        $titleRange.VerticalAlignment = -4108
        $titleRange.Interior.Color = 14281463
        $titleRange.RowHeight = 26

        $subtitleRange = $worksheet.Range('A2:H2')
        $subtitleRange.Merge()
        $subtitleRange.Value2 = (Get-UiText -Key 'UpdatedOnTitle') + (Get-Date).ToString('yyyy-MM-dd HH:mm')
        $subtitleRange.Font.Size = 10
        $subtitleRange.Font.Color = 5592405
        $subtitleRange.HorizontalAlignment = -4108
        $subtitleRange.Interior.Color = 16249339
        $subtitleRange.RowHeight = 20

        for ($col = 0; $col -lt $headers.Count; $col++) {
            $cell = $worksheet.Cells.Item(3, $col + 1)
            $cell.Value2 = $headers[$col].Label
            $cell.Font.Bold = $true
            $cell.Font.Color = 16777215
            $cell.Interior.Color = 12868028
            $cell.HorizontalAlignment = -4108
            $cell.VerticalAlignment = -4108
        }

        $rowIndex = 4
        foreach ($row in $Rows) {
            for ($col = 0; $col -lt $headers.Count; $col++) {
                $cell = $worksheet.Cells.Item($rowIndex, $col + 1)
                $header = $headers[$col]
                $cell.Value2 = [string]$row.($header.Key)
                $cell.VerticalAlignment = -4160

                if (($rowIndex % 2) -eq 0) {
                    $cell.Interior.Color = 16710651
                }
            }

            foreach ($columnIndex in @(4, 6)) {
                $valueText = [string]$worksheet.Cells.Item($rowIndex, $columnIndex).Value2
                $value = $null
                if ($valueText -match '([0-9]+(?:\.[0-9]+)?)') {
                    $value = [double]$matches[1]
                }

                if ($null -eq $value) {
                    continue
                }

                $cell = $worksheet.Cells.Item($rowIndex, $columnIndex)
                if ($value -le 10) {
                    $cell.Font.Color = 393750
                    $cell.Interior.Color = 13551615
                }
                elseif ($value -le 30) {
                    $cell.Font.Color = 26112
                    $cell.Interior.Color = 10092543
                }
                else {
                    $cell.Font.Color = 25600
                    $cell.Interior.Color = 13561798
                }
            }

            $rowIndex++
        }

        $worksheet.Range('A3:H3').AutoFilter() | Out-Null
        $worksheet.Application.ActiveWindow.SplitRow = 3
        $worksheet.Application.ActiveWindow.FreezePanes = $true
        $worksheet.Columns.AutoFit() | Out-Null
        $worksheet.Columns.Item('A').ColumnWidth = 30
        $worksheet.Columns.Item('B').ColumnWidth = 16
        $worksheet.Columns.Item('D').ColumnWidth = 22
        $worksheet.Columns.Item('E').ColumnWidth = 18
        $worksheet.Columns.Item('F').ColumnWidth = 24
        $worksheet.Columns.Item('G').ColumnWidth = 18
        $worksheet.Columns.Item('H').ColumnWidth = 14
        $worksheet.Range('A1:H' + [Math]::Max($rowIndex - 1, 3)).Borders.LineStyle = 1

        $workbook.SaveAs($xlsxPath, 51)
        return $xlsxPath
    }
    catch {
        return $null
    }
    finally {
        if ($workbook) {
            $workbook.Close($false)
            [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($workbook)
        }

        if ($worksheet) {
            [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($worksheet)
        }

        if ($excel) {
            $excel.Quit()
            [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel)
        }

        [GC]::Collect()
        [GC]::WaitForPendingFinalizers()
    }
}

$scriptDirectory = if ($PSCommandPath) { Split-Path -Parent $PSCommandPath } else { $OutputDir }
if (-not (Test-Path -LiteralPath $scriptDirectory)) {
    New-Item -ItemType Directory -Path $scriptDirectory | Out-Null
}
if (-not (Test-Path -LiteralPath $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir | Out-Null
}

$shortcuts = @(Get-CodexShortcutsFromProfile -Path $ProfilePath)
if ($shortcuts.Count -eq 0) {
    throw "No Codex shortcuts that set CODEX_HOME were found in $ProfilePath"
}

$refreshResults = @()
if (-not $SkipStatusRefresh) {
    foreach ($shortcut in $shortcuts) {
        $refreshResults += Invoke-CodexStatusRefresh -ShortcutInfo $shortcut
    }
}

$rows = foreach ($shortcut in $shortcuts) {
    Get-LatestRateLimitRecord -ShortcutInfo $shortcut
}

$displayRows = foreach ($row in $rows) {
    Convert-RowToDisplayRecord -Row $row
}

$legacyOutputDir = Join-Path $HOME 'CodexQuotaReports'
Clear-OldReportFiles -Directories @($legacyOutputDir, $OutputDir)

$xlsxPath = Export-ReportExcel -Rows $displayRows -Directory $OutputDir

$result = [pscustomobject]@{
    ProfilePath     = $ProfilePath
    OutputDirectory = $OutputDir
    ExcelPath       = $xlsxPath
    Refreshed       = -not $SkipStatusRefresh
    RefreshResults  = $refreshResults
    Rows            = $rows
    DisplayRows     = $displayRows
}

if ($PassThru) {
    $result
    return
}

$summary = $displayRows | Select-Object Email, PlanType, Shortcut, WeeklyRemaining, FiveHourRemaining, UpdatedOn
$summary | Format-Table -AutoSize
Write-Host ''
if ($xlsxPath) {
    Write-Host "Excel: $xlsxPath"
}
else {
    Write-Warning (Get-UiText -Key 'ExcelComUnavailable')
}
