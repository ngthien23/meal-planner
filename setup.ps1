# setup.ps1 - Quick setup script for meal-planner on PowerShell
Write-Host "Installing meal-planner and registering the 'meals' shortcut..." -ForegroundColor Cyan

if (Get-Command uv -ErrorAction SilentlyContinue) {
    uv pip install -e .
} else {
    python -m pip install -e .
}

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n[OK] Installation successful! You can now type 'meals' directly in PowerShell." -ForegroundColor Green
} else {
    Write-Host "`n[!] Installation encountered an issue. You can always run '.\meals' in this directory." -ForegroundColor Yellow
}
