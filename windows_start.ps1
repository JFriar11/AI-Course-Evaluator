# One-command PowerShell launcher for the Program Assessment Screener (Windows).
# Installs what is missing, starts the model server, then opens the app.
#
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   .\windows_start.ps1
#
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$OllamaProcess = $null

try {
    # 1. Python environment
    if (-not (Test-Path ".venv\Scripts\python.exe")) {
        Write-Host "Creating a Python environment (.venv)..."
        if (Test-Path ".venv") {
            Remove-Item -Recurse -Force ".venv"
        }
        if (Get-Command python -ErrorAction SilentlyContinue) {
            python -m venv .venv
        } elseif (Get-Command py -ErrorAction SilentlyContinue) {
            py -3 -m venv .venv
        } else {
            Write-Error "Python is not installed or not in PATH. Please install Python 3 from https://python.org"
            exit 1
        }
    }
    & ".\.venv\Scripts\python.exe" -m pip install --quiet -r backend/requirements.txt

    # 2. Web interface
    if (-not (Test-Path "frontend\dist\index.html")) {
        if (Get-Command npm -ErrorAction SilentlyContinue) {
            Write-Host "Building the web interface..."
            Push-Location frontend
            try {
                npm install --silent
                npm run build
            } finally {
                Pop-Location
            }
        } else {
            Write-Host "[WARNING] No built interface found and Node/npm is not installed." -ForegroundColor Yellow
            Write-Host "          Ask someone to run 'npm run build' in the frontend folder once." -ForegroundColor Yellow
        }
    }

    # 3. Ollama: start it if installed but not running, and pull the model if missing.
    if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
        Write-Host "[WARNING] Ollama is not installed. Install it from https://ollama.com" -ForegroundColor Yellow
        Write-Host "          The app will still open, but grading needs a local model." -ForegroundColor Yellow
    } else {
        $env:OLLAMA_NUM_PARALLEL = "1"
        $env:OLLAMA_KEEP_ALIVE = "-1"
        if (-not $env:EVAL_MODEL) {
            $env:EVAL_MODEL = "qwen3:8b"
        }

        $ollamaRunning = $false
        try {
            $null = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -Method Get -TimeoutSec 2 -ErrorAction Stop
            $ollamaRunning = $true
        } catch {
            $ollamaRunning = $false
        }

        if (-not $ollamaRunning) {
            Write-Host "Starting the local model server (ollama serve)..."
            $OllamaProcess = Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden -PassThru
            for ($i = 0; $i -lt 10; $i++) {
                try {
                    $null = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -Method Get -TimeoutSec 2 -ErrorAction Stop
                    $ollamaRunning = $true
                    break
                } catch {
                    Start-Sleep -Seconds 1
                }
            }
        }

        try {
            $tagsResponse = Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
            if ($tagsResponse.Content -notmatch [regex]::Escape("`"$($env:EVAL_MODEL)`"")) {
                Write-Host "Pulling $($env:EVAL_MODEL) (one time, stays on disk)..."
                ollama pull $env:EVAL_MODEL
            }
        } catch {
            Write-Host "[WARNING] Could not verify Ollama models via API." -ForegroundColor Yellow
        }
    }

    Write-Host "Open http://127.0.0.1:8000 in your browser."
    $null = Start-Job -ScriptBlock {
        Start-Sleep -Seconds 2
        Start-Process "http://127.0.0.1:8000"
    }

    & ".\.venv\Scripts\python.exe" backend/server.py
} finally {
    if ($null -ne $OllamaProcess -and -not $OllamaProcess.HasExited) {
        Write-Host "Stopping background Ollama server (PID $($OllamaProcess.Id))..."
        Stop-Process -Id $OllamaProcess.Id -Force -ErrorAction SilentlyContinue
    }
}
