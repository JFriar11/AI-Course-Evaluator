#!/usr/bin/env bash
# One-command launcher for the Program Assessment Screener.
# Installs what is missing, starts the model server, then opens the app.
#
#   ./linux_start.sh
#
set -euo pipefail
cd "$(dirname "$0")"

# 1. Python environment
if [ ! -d ".venv" ]; then
    echo "Creating a Python environment (.venv)..."
    python3 -m venv .venv
fi
./.venv/bin/python -m pip install --quiet -r backend/requirements.txt

# 2. Web interface. frontend/dist is committed, so npm is only needed if it
#    is somehow missing - a non-technical user never has to touch Node.
if [ ! -f "frontend/dist/index.html" ]; then
    if command -v npm >/dev/null 2>&1; then
        echo "Building the web interface..."
        (cd frontend && npm install --silent && npm run build)
    else
        echo "[WARNING] No built interface found and Node/npm is not installed."
        echo "          Ask someone to run 'npm run build' in the frontend folder once."
    fi
fi

# 3. Ollama: start it if installed but not running, and explain how to install
#    a model if none is present.
if ! command -v ollama >/dev/null 2>&1; then
    echo "[WARNING] Ollama is not installed. Install it from https://ollama.com"
    echo "          The app will still open, but grading needs a local model."
else
    if ! curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
        echo "Starting the local model server (ollama serve)..."
        ollama serve >/dev/null 2>&1 &
        for _ in 1 2 3 4 5 6 7 8 9 10; do
            curl -s http://localhost:11434/api/tags >/dev/null 2>&1 && break
            sleep 1
        done
    fi
    if ! curl -s http://localhost:11434/api/tags | grep -o '"name"' >/dev/null 2>&1; then
        echo "[ACTION REQUIRED] No models are installed in Ollama yet."
        echo "                Run:  ollama pull llama3.1"
        echo "                (about 4.9 GB, one time, then it stays on disk)"
    fi
fi

echo "Open http://127.0.0.1:8000 in your browser."
./.venv/bin/python backend/server.py
