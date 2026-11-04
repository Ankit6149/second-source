# Second Source local end-to-end operator launcher (Windows PowerShell).
# Nothing here calls Meta: the operator must consent inside the app.
# Pass -Muse only if MODEL_API_KEY is already set in the current environment.
param([switch]$Muse)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$frontend = Join-Path $root "product"

if ($Muse -and [string]::IsNullOrWhiteSpace($env:MODEL_API_KEY)) {
    throw "MODEL_API_KEY is not set. Configure it securely in this terminal; do not paste it into chat or the repository."
}

Push-Location $root
try {
    Write-Host "Running zero-billing integration checks..."
    python -m pytest -q tests/test_muse_pipeline_repair.py tests/test_investigation_engine.py tests/test_vikunja_hybrid.py
    if ($LASTEXITCODE -ne 0) { throw "Python acceptance tests failed. No engine started." }

    # Keep the Meta key out of the npm build and frontend process environment.
    $modelKey = $env:MODEL_API_KEY
    Remove-Item Env:MODEL_API_KEY -ErrorAction SilentlyContinue
    Push-Location $frontend
    try {
        if (-not (Test-Path "node_modules")) {
            npm ci
            if ($LASTEXITCODE -ne 0) { throw "npm ci failed." }
        }
        npm run build
        if ($LASTEXITCODE -ne 0) { throw "Frontend typecheck/build failed." }
    } finally { Pop-Location }

    if ($Muse) {
        $env:MODEL_API_KEY = $modelKey
        $env:SECOND_SOURCE_ALLOW_MUSE_REPAIR = "true"
    } else {
        $env:SECOND_SOURCE_ALLOW_MUSE_REPAIR = "false"
    }

    # Never leave the old non-AI engine serving port 8765 while the new UI
    # appears to promise Muse mode. Fail visibly instead of silently racing.
    $occupied = Get-NetTCPConnection -LocalAddress "127.0.0.1" -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
    if ($occupied) {
        throw "Port 8765 is already in use. Stop the old local engine before running this branch."
    }
    Write-Host "Starting local Python engine..."
    Start-Process -FilePath "python" -ArgumentList @("scripts/investigation_engine.py") -WorkingDirectory $root
    Remove-Item Env:MODEL_API_KEY -ErrorAction SilentlyContinue
    $env:SECOND_SOURCE_ALLOW_MUSE_REPAIR = "false"
    Write-Host "Starting the local UI (no model credentials in this process)..."
    Start-Process -FilePath "npm.cmd" -ArgumentList @("run", "dev") -WorkingDirectory $frontend

    Write-Host ""
    Write-Host "Open http://127.0.0.1:5173/experiments/"
    if ($Muse) {
        Write-Host "Choose 'Muse-assisted Vikunja' and explicitly authorize the one-call cap."
        Write-Host "The model may fail or produce a rejected edit. This remains a real, auditable result."
    } else {
        Write-Host "This run is NON_AI; only deterministic local experiments are enabled."
    }
    Write-Host "Ensure the local Vikunja v2.4.0 reference is configured as required by scripts/vikunja_model_experiment.py."
} finally {
    Pop-Location
}
