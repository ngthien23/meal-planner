# setup.ps1 - Quick setup script for meal-planner on PowerShell
Write-Host "Installing meal-planner and registering global 'meals' shortcut..." -ForegroundColor Cyan

if (Get-Command uv -ErrorAction SilentlyContinue) {
    uv pip install -e .
} else {
    python -m pip install -e .
}

$repoRoot = $PSScriptRoot
$pyExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pyExe)) {
    $pyCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pyCmd) { $pyExe = $pyCmd.Source } else { $pyExe = "python" }
}

# 1. Register meals in $HOME\.local\bin (in user PATH)
$localBin = Join-Path $HOME ".local\bin"
if (-not (Test-Path $localBin)) {
    New-Item -ItemType Directory -Path $localBin -Force | Out-Null
}
$cmdContent = "@echo off`n`"$pyExe`" `"$repoRoot\main.py`" %*"
Set-Content -Path (Join-Path $localBin "meals.cmd") -Value $cmdContent -Force
Remove-Item -Path (Join-Path $localBin "meals.ps1") -Force -ErrorAction SilentlyContinue

# 2. Register meals function in PowerShell profile
$profileFunc = "`nfunction meals { & `"$pyExe`" `"$repoRoot\main.py`" @args }`n"
$profilePaths = @(
    $PROFILE,
    (Join-Path $HOME "Documents\PowerShell\Microsoft.PowerShell_profile.ps1"),
    (Join-Path $HOME "Documents\WindowsPowerShell\Microsoft.PowerShell_profile.ps1")
) | Select-Object -Unique

foreach ($p in $profilePaths) {
    if ($p) {
        $pDir = Split-Path $p
        if (-not (Test-Path $pDir)) { New-Item -ItemType Directory -Path $pDir -Force | Out-Null }
        if (-not (Test-Path $p)) { New-Item -ItemType File -Path $p -Force | Out-Null }
        $content = Get-Content $p -Raw -ErrorAction SilentlyContinue
        if (-not $content -or $content -notmatch "function meals") {
            Add-Content -Path $p -Value $profileFunc -Force
        }
    }
}

Write-Host "`n[OK] Setup complete! Global 'meals' shortcut is active." -ForegroundColor Green
Write-Host "You can now open a freshly launched terminal from anywhere and run: meals`n" -ForegroundColor Cyan
