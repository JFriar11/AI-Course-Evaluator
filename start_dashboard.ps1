$ModelName = "deepseek-r1:8b"
$ApiUrl = "http://localhost:11434"

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " Starting AI Screening Pipeline" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

# 1. Check if Ollama is running
try {
    $null = Invoke-RestMethod -Uri "$ApiUrl/api/tags" -ErrorAction Stop
    Write-Host "[1/4] Ollama server is already running." -ForegroundColor Green
} catch {
    Write-Host "[1/4] Starting Ollama server in the background..." -ForegroundColor Yellow
    Start-Process ollama -ArgumentList "serve" -WindowStyle Hidden
    Start-Sleep -Seconds 3
}

# 2. Verify model availability
Write-Host "[2/4] Verifying model '$ModelName'..."
$Models = ollama list
if ($Models -notmatch$ModelName) {
    Write-Host "      Model not found. Pulling '$ModelName' now..." -ForegroundColor Yellow
    ollama pull $ModelName
}

# 3. Start the Python FastAPI Backend (Navigates to /backend and keeps window open)
Write-Host "[3/4] Launching Python FastAPI Backend..." -ForegroundColor Green
$BackendCmd = "-NoExit -Command `"& { cd backend; if (Test-Path '..\.venv\Scripts\activate.ps1') { ..\.venv\Scripts\activate.ps1 }; python server.py }`""
Start-Process powershell -ArgumentList $BackendCmd

# 4. Start the React WebUI (Navigates to /frontend and keeps window open)
Write-Host "[4/4] Launching React WebUI..." -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Cyan
$FrontendCmd = "-NoExit -Command `"& { cd frontend; pnpm run dev }`""
Start-Process powershell -ArgumentList $FrontendCmd