<#
  Privacy MCP Agent - one-click launcher (Windows)

  .\start.ps1            Production mode: builds the UI and serves everything at http://127.0.0.1:8000
  .\start.ps1 -Dev       Dev mode: backend on :8000 + Vite hot-reload UI on :5173
  .\start.ps1 -Model qwen2.5   Use a different Ollama model (pulled automatically)
#>
param(
  [switch]$Dev,
  [string]$Model = "llama3.2"
)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$backend = Join-Path $root "backend"
$py = Join-Path $backend ".venv\Scripts\python.exe"

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }

# 1. Ollama -----------------------------------------------------------------
Step "Checking Ollama"
$ollama = (Get-Command ollama -ErrorAction SilentlyContinue).Source
if (-not $ollama) { $ollama = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe" }
if (-not (Test-Path $ollama)) {
  Write-Host "Ollama is not installed. Installing via winget..." -ForegroundColor Yellow
  winget install --id Ollama.Ollama -e --accept-source-agreements --accept-package-agreements
  $ollama = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
}
try { Invoke-RestMethod http://127.0.0.1:11434/api/tags -TimeoutSec 3 | Out-Null }
catch {
  Write-Host "Starting Ollama server..."
  Start-Process $ollama -ArgumentList "serve" -WindowStyle Hidden
  Start-Sleep 4
}
$tags = (Invoke-RestMethod http://127.0.0.1:11434/api/tags).models.name
if (-not ($tags | Where-Object { $_ -like "$Model*" })) {
  Step "Downloading model '$Model' (one-time, ~2 GB)"
  & $ollama pull $Model
}

# 2. Python backend ---------------------------------------------------------
Step "Preparing Python backend"
if (-not (Test-Path $py)) { python -m venv (Join-Path $backend ".venv") }
& $py -m pip install -q --disable-pip-version-check -r (Join-Path $backend "requirements.txt")

# 3. Frontend ---------------------------------------------------------------
Push-Location $root
if (-not (Test-Path "node_modules")) { Step "Installing UI dependencies"; npm install }
$env:AGENT_MODEL = $Model

if ($Dev) {
  Step "Starting backend (:8000) and Vite dev server (:5173)"
  Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$backend'; `$env:AGENT_MODEL='$Model'; & '$py' main.py"
  Start-Sleep 3
  Start-Process "http://localhost:5173"
  npm run dev
} else {
  Step "Building UI"
  npm run build
  Step "Privacy MCP Agent running at http://127.0.0.1:8000  (Ctrl+C to stop)"
  Start-Process "http://127.0.0.1:8000"
  Set-Location $backend
  & $py main.py
}
Pop-Location
