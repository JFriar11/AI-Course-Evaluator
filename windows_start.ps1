# One-command launcher for the Program Assessment Screener (Windows).
# Double-click, or run:  .\windows_start.ps1
# Use this first for Windows:
# Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
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

<<<<<<< Updated upstream
# 3. Start Ollama and load the configured evaluation model
$model = "deepseek-r1:8b"
$env:EVAL_MODEL = $model
$ollamaCommand = Get-Command ollama -ErrorAction SilentlyContinue

if (-not $ollamaCommand) {
    Write-Host "[WARNING] Ollama was not found. Install it from https://ollama.com/download/windows"
    Write-Host "          The app will start, but grading needs Ollama and the model '$model'."
} else {
    $ollamaReady = $false
    try {
        Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -TimeoutSec 2 -UseBasicParsing | Out-Null
        $ollamaReady = $true
    } catch {
        Write-Host "Starting the Ollama service..."
        Start-Process -FilePath $ollamaCommand.Source -ArgumentList "serve" -WindowStyle Hidden

        for ($attempt = 0; $attempt -lt 30; $attempt++) {
            Start-Sleep -Seconds 1
            try {
                Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -TimeoutSec 2 -UseBasicParsing | Out-Null
                $ollamaReady = $true
                break
            } catch {
                # Keep waiting for the local service to become available.
            }
        }
    }

    if ($ollamaReady) {
        Write-Host "Opening Ollama with $model. If it is not installed, Ollama will download it."
        Start-Process -FilePath $ollamaCommand.Source -ArgumentList @("run", $model)
    } else {
        Write-Host "[WARNING] Ollama did not start. Grading needs Ollama and the model '$model'."
        Write-Host "          Start the service with: ollama serve"
    }
=======
# 3. Ollama check
# One report at a time and the model kept resident: parallel Ollama calls split
# the CPU thread budget, so the same PDF scores differently run to run.
$env:OLLAMA_NUM_PARALLEL = "1"
$env:OLLAMA_KEEP_ALIVE = "-1"
if (-not $env:EVAL_MODEL) { $env:EVAL_MODEL = "qwen3:8b" }

try {
    Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -TimeoutSec 5 -UseBasicParsing | Out-Null
} catch {
    Write-Host "[WARNING] Ollama is not running. Start it with: ollama serve"
>>>>>>> Stashed changes
}

Write-Host "Ensuring model $env:EVAL_MODEL is available..."
ollama pull $env:EVAL_MODEL

& ".venv\Scripts\python.exe" backend\server.py
