# T0 baseline: benign + security runs on workspace subset
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "Missing venv. Run: python -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt"
}

$EnvFile = Join-Path $Root ".env"
if (-not (Test-Path $EnvFile)) {
    throw "Missing .env with OPENAI_API_KEY. Copy .env.example to .env and set your key."
}

Get-Content $EnvFile | ForEach-Object {
    if ($_ -match '^\s*#' -or $_ -match '^\s*$') { return }
    $parts = $_ -split '=', 2
    if ($parts.Count -eq 2) {
        Set-Item -Path "Env:$($parts[0].Trim())" -Value $parts[1].Trim()
    }
}

if (-not $env:OPENAI_API_KEY) {
    throw "OPENAI_API_KEY not set in .env"
}

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:RICH_FORCE_TERMINAL = "0"

$Model = "GPT_4O_MINI_2024_07_18"
$Suite = "workspace"
$Version = "v1.2.2"
$Logdir = "./runs"
$Tasks = 0..9 | ForEach-Object { "-ut", "user_task_$_" }

Write-Host "=== T0-A: Benign (no attack) ===" -ForegroundColor Cyan
& $Python -m agentdojo.scripts.benchmark `
    -s $Suite `
    --benchmark-version $Version `
    --model $Model `
    --logdir $Logdir `
    @Tasks

Write-Host "`n=== T0-B: Security (important_instructions) ===" -ForegroundColor Cyan
& $Python -m agentdojo.scripts.benchmark `
    -s $Suite `
    --benchmark-version $Version `
    --model $Model `
    --attack important_instructions `
    --logdir $Logdir `
    @Tasks

Write-Host "`n=== Collecting results ===" -ForegroundColor Cyan
& $Python (Join-Path $Root "scripts\collect_t0_results.py")

Write-Host "`nDone. See results/T0_summary.md and results/traces/" -ForegroundColor Green
