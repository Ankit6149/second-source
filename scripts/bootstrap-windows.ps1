# Prepare Second Source's isolated Windows Python environment.
# Does NOT prompt for, access, or run billable Meta API credentials.
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File scripts/bootstrap-windows.ps1
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Confirm-Success([string]$description) {
    if ($LASTEXITCODE -ne 0) {
        throw "$description failed (exit code $LASTEXITCODE)"
    }
}

if (-not (Test-Path "pyproject.toml") -or -not (Test-Path "src/second_source")) {
    throw "Run from the second-source repository root (pyproject.toml and src/second_source are required)."
}
if (-not (Test-Path "src/second_source/live_experiment.py")) {
    throw "G2 live experiment not found. Fetch and switch to integrate/g2-discovery, then run this script again."
}

$basePython = Get-Command python -ErrorAction SilentlyContinue
if (-not $basePython) {
    throw "Python executable not found. Install Python 3.11+ or activate a compatible Python environment."
}
& python -c "import sys; assert sys.version_info >= (3,11), 'Python 3.11 or later required'; print('Base Python:',sys.executable,sys.version.split()[0])"
Confirm-Success "Python version preflight"

$venvPython = Join-Path (Get-Location).Path ".venv/Scripts/python.exe"
if (-not (Test-Path $venvPython)) {
    & python -m venv .venv
    Confirm-Success "Virtual environment creation"
}
if (-not (Test-Path $venvPython)) {
    throw "Virtual environment Python missing at $venvPython"
}

& $venvPython -m pip install -e ".[dev]"
Confirm-Success "Editable package installation"

& $venvPython -c "import second_source, second_source.live_experiment, sys; print('Package import OK:', second_source.__file__); print('Isolated Python:',sys.executable)"
Confirm-Success "Package import smoke test"

& $venvPython -m pytest -q
Confirm-Success "Complete non-billable test suite"

Write-Host ""
Write-Host "BOOTSTRAP_OK: package imports and non-billable tests passed." -ForegroundColor Green
Write-Host "Run the billable experiment ONLY in an interactive PowerShell session after authorizing the key and budget."
Write-Host "Use .\.venv\Scripts\python.exe to avoid the global C:\miniconda interpreter."
