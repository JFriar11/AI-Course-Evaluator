"""Single source of truth for paths and settings.

Every path is resolved relative to this file, so the app behaves the same
no matter which directory the launcher is run from.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent

# --------------------------------------------------------------------------
# Directories
# --------------------------------------------------------------------------
EVALUATE_DIR = PROJECT_ROOT / "Evaluate"
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", str(PROJECT_ROOT / "Output")))
RUBRICS_DIR = BACKEND_DIR / "Rubrics"
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
EMAIL_CONFIG_PATH = BACKEND_DIR / "email_config.json"

SCORECARD_TEMPLATE_JSON_PATH = BACKEND_DIR / "scorecard-output-template.json"
SCORECARD_TEMPLATE_MARKDOWN_PATH = BACKEND_DIR / "scorecard-output-template.md"

# --------------------------------------------------------------------------
# Model settings (override with environment variables)
# --------------------------------------------------------------------------
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL_CONTEXT_TOKENS = int(os.environ.get("MODEL_CONTEXT_TOKENS", "16384"))
MAX_DOC_CHARS = int(os.environ.get("MAX_DOC_CHARS", "25000"))
TEMPERATURE = float(os.environ.get("EVAL_TEMPERATURE", "0.1"))
MODEL_TIMEOUT_SECONDS = int(os.environ.get("MODEL_TIMEOUT_SECONDS", "1800"))

# CPU inference is locked so every report behaves the same. One request at a
# time (OLLAMA_NUM_PARALLEL=1 in the launchers) plus these per-call options
# means a report never competes with another for threads.
OLLAMA_NUM_CTX = int(os.environ.get("OLLAMA_NUM_CTX", "8192"))
OLLAMA_NUM_THREAD = int(os.environ.get("OLLAMA_NUM_THREAD",
                                      str(max(1, (os.cpu_count() or 4) // 2))))

# A document is graded in a single pass only when it fits comfortably in the
# locked context window. Longer reports are split into overlapping chunks and
# reduced to evidence excerpts instead of being silently cut off.
SINGLE_PASS_CHAR_LIMIT = int(os.environ.get("SINGLE_PASS_CHAR_LIMIT", "12000"))
CHUNK_MAX_CHARS = int(os.environ.get("CHUNK_MAX_CHARS", "7500"))
CHUNK_OVERLAP_CHARS = int(os.environ.get("CHUNK_OVERLAP_CHARS", "500"))
MAX_CHUNKS = int(os.environ.get("MAX_CHUNKS", "24"))

# Pre-evaluation gates. STOP_ON_PROMPT_INJECTION=false redacts the offending
# text instead of stopping the run.
STOP_ON_PROMPT_INJECTION = os.getenv("STOP_ON_PROMPT_INJECTION", "true").lower() == "true"
PRE_EVAL_USE_MODEL = os.getenv("PRE_EVAL_USE_MODEL", "true").lower() not in ("0", "false", "no")
# Qwen3 can think or not think per call. Scoring is the only pass where the
# extra tokens are worth it.
QWEN_THINK_ON_SCORING = os.getenv("QWEN_THINK_ON_SCORING", "false").lower() == "true"

# Figure captions: embedded images are described by Gemini when a key is
# present, otherwise a plain placeholder is inserted so the reviewer knows a
# figure was skipped.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
VISION_MIN_IMAGE_BYTES = int(os.environ.get("VISION_MIN_IMAGE_BYTES", "10240"))

# After the first pass, every criterion whose quote could not be traced is
# re-asked once with the exact passages the script found. This catches most
# hallucinated citations without a full re-grade. Set RECHECK_UNVERIFIED=0 to
# disable it.
RECHECK_UNVERIFIED = os.environ.get("RECHECK_UNVERIFIED", "1") not in ("0", "false", "no")
# One pass covers up to this many criteria per error type. A full 23-criterion
# re-check prompt is only a few thousand tokens, so the whole rubric can be
# revisited in a single round trip.
RECHECK_MAX_CRITERIA = int(os.environ.get("RECHECK_MAX_CRITERIA", "23"))
RECHECK_TIMEOUT_SECONDS = int(os.environ.get("RECHECK_TIMEOUT_SECONDS", "900"))

# Prefer a model that is actually installed. Set EVAL_MODEL to pin one.
# Qwen3 8B is the intended default: it is small enough to run on CPU with the
# locked thread budget, and it supports per-call thinking control.
MODEL_CANDIDATES = [
    "qwen3:8b",
    "qwen3:14b",
    "deepseek-r1:8b",
    "qwen2.5:32b",
    "qwen2.5:14b",
    "qwq:latest",
    "llama3.1:latest",
    "mistral:latest",
]


def installed_models() -> list:
    import json
    import urllib.request

    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=5) as response:
            models = json.loads(response.read().decode()).get("models", [])
        return [{"name": m.get("name", ""), "size": int(m.get("size", 0))} for m in models]
    except Exception:
        return []


def _available_memory_bytes() -> int:
    """Best-effort free RAM, so we do not pick a model that will not fit."""
    try:
        with open("/proc/meminfo") as handle:
            for line in handle:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) * 1024
    except Exception:
        pass
    return 0


def is_thinking_model(name: str) -> bool:
    """Reasoning models can emit a separate thinking trace; others reject think=True."""
    return any(word in name.lower() for word in ("deepseek", "qwq", "r1", "qwen3"))


def _detect_model() -> str:
    installed = installed_models()
    if not installed:
        return MODEL_CANDIDATES[0]

    available = _available_memory_bytes()
    # A quantised model needs roughly its file size plus KV-cache headroom.
    fits = [m for m in installed if available == 0 or m["size"] < available * 0.6]
    if not fits:
        # Nothing fits comfortably; the smallest model is the one most likely
        # to finish a report in a reasonable time.
        pool = [min(installed, key=lambda m: m["size"])]
    else:
        pool = fits

    for candidate in MODEL_CANDIDATES:
        if candidate in {m["name"] for m in pool}:
            return candidate
    return min(pool, key=lambda m: m["size"])["name"] if pool else MODEL_CANDIDATES[0]


def _normalise_model_name(name: str) -> str:
    """Accept the shorthand people type (`qwen3.8b`) as Ollama's tag form."""
    name = (name or "").strip()
    if not name or ":" in name:
        return name
    match = re.fullmatch(r"([a-z0-9-]+)\.(\d+b)", name.lower())
    if match:
        return f"{match.group(1)}:{match.group(2)}"
    return name


MODEL = _normalise_model_name(os.environ.get("EVAL_MODEL") or "") or _detect_model()
THINKING_MODEL = is_thinking_model(MODEL)

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))

# Which rubric file feeds each section of the scorecard template.
SECTION_RUBRICS = {
    "administrative": "administrative_rubric.txt",
    "tracking_information": "tracking_information_rubric.txt",
    "methodology": "methodology_rubric.txt",
    "results": "results_rubric.txt",
    "continuous_improvement": "ci_plan_rubric.txt",
}

SECTION_LABELS = {
    "administrative": "Section 1 - Administrative",
    "tracking_information": "Section 2 - Tracking Information",
    "methodology": "Section 3 - Methodology",
    "results": "Section 4 - Results",
    "continuous_improvement": "Section 5 - Continuous Improvement Plan",
}


def ensure_directories() -> None:
    for directory in (EVALUATE_DIR, OUTPUT_DIR, RUBRICS_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def ollama_is_running() -> bool:
    """Probe the local Ollama service without importing the client."""
    import urllib.request

    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=5) as response:
            return response.status == 200
    except Exception:
        return False


def model_is_available(model: Optional[str] = None) -> bool:
    target = model or MODEL
    import json
    import urllib.request

    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=5) as response:
            tags = json.loads(response.read().decode())
        return any(tag.get("name") == target for tag in tags.get("models", []))
    except Exception:
        return False
