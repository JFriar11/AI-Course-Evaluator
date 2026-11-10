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
    # One report at a time and the model kept resident: parallel Ollama calls
    # split the CPU thread budget, so the same PDF scores differently run to run.
    export OLLAMA_NUM_PARALLEL=1
    export OLLAMA_KEEP_ALIVE=-1
    export EVAL_MODEL="${EVAL_MODEL:-qwen3:8b}"

    if ! curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
        echo "Starting the local model server (ollama serve)..."
        OLLAMA_NUM_PARALLEL=1 OLLAMA_KEEP_ALIVE=-1 ollama serve >/dev/null 2>&1 &
        for _ in 1 2 3 4 5 6 7 8 9 10; do
            curl -s http://localhost:11434/api/tags >/dev/null 2>&1 && break
            sleep 1
        done
    fi
    if ! curl -s http://localhost:11434/api/tags | grep -q "$EVAL_MODEL"; then
        echo "Pulling $EVAL_MODEL (one time, stays on disk)..."
        ollama pull "$EVAL_MODEL"
    fi
fi

echo "Open http://127.0.0.1:8000 in your browser."
./.venv/bin/python backend/server.py
