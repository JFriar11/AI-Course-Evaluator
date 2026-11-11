#!/usr/bin/env bash
# One-command launcher for the Program Assessment Screener (macOS).
# Installs what is missing, starts the model server, then opens the app.
#
#   ./mac_start.sh
#
set -euo pipefail
cd "$(dirname "$0")"

OLLAMA_PID=""
cleanup() {
    if [ -n "$OLLAMA_PID" ] && kill -0 "$OLLAMA_PID" 2>/dev/null; then
        echo "Stopping background Ollama server (PID $OLLAMA_PID)..."
        kill "$OLLAMA_PID"
    fi
}
trap cleanup EXIT INT TERM

# 1. Python environment
if [ ! -x ".venv/bin/python" ]; then
    echo "Creating a Python environment (.venv)..."
    rm -rf .venv
    python3 -m venv .venv
fi
./.venv/bin/python -m pip install --quiet -r backend/requirements.txt

# 2. Web interface
if [ ! -f "frontend/dist/index.html" ]; then
    if command -v npm >/dev/null 2>&1; then
        echo "Building the web interface..."
        (cd frontend && npm install --silent && npm run build)
    else
        echo "[WARNING] No built interface found and Node/npm is not installed."
        echo "          Ask someone to run 'npm run build' in the frontend folder once."
    fi
fi

# 3. Ollama: start it if installed but not running, and pull the model if missing.
if ! command -v ollama >/dev/null 2>&1; then
    echo "[WARNING] Ollama is not installed. Install it from https://ollama.com"
    echo "          The app will still open, but grading needs a local model."
else
    export OLLAMA_NUM_PARALLEL=1
    export OLLAMA_KEEP_ALIVE=-1
    export EVAL_MODEL="${EVAL_MODEL:-qwen3:8b}"

    if ! curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
        echo "Starting the local model server (ollama serve)..."
        OLLAMA_NUM_PARALLEL=1 OLLAMA_KEEP_ALIVE=-1 ollama serve >/dev/null 2>&1 &
        OLLAMA_PID=$!
        for _ in {1..10}; do
            curl -sf http://localhost:11434/api/tags >/dev/null 2>&1 && break
            sleep 1
        done
    fi

    if ! curl -sf http://localhost:11434/api/tags | grep -Fq "\"$EVAL_MODEL\""; then
        echo "Pulling $EVAL_MODEL (one time, stays on disk)..."
        ollama pull "$EVAL_MODEL"
    fi
fi

echo "Open http://127.0.0.1:8000 in your browser."
if command -v open >/dev/null 2>&1; then
    (sleep 2 && open "http://127.0.0.1:8000" >/dev/null 2>&1) &
fi

./.venv/bin/python backend/server.py
