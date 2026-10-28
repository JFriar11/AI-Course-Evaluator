# One-command launcher for the Program Assessment Screener (Windows).
# Double-click, or run:  .\windows_start.ps1
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

# 1. Python environment
if (-not (Test-Path ".venv")) {
    Write-Host "Creating a Python environment (.venv)..."
    python -m venv .venv
}
& ".venv\Scripts\python.exe" -m pip install --quiet -r backend\requirements.txt

# 2. Web interface
if (-not (Test-Path "frontend\dist\index.html")) {
    if (Get-Command npm -ErrorAction SilentlyContinue) {
        Write-Host "Building the web interface..."
        Push-Location frontend
        npm install
        npm run build
        Pop-Location
    } else {
        Write-Host "[WARNING] Node/npm not found. The API works, but there is no interface."
    }
}

# 3. Ollama check
try {
    Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -TimeoutSec 5 -UseBasicParsing | Out-Null
} catch {
    Write-Host "[WARNING] Ollama is not running. Start it with: ollama serve"
}

& ".venv\Scripts\python.exe" backend\server.py
