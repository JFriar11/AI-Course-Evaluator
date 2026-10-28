"""Standalone web app for the AI report screener.

Runs the API and the built React front end from a single process, so a
non-technical user only needs Python and Ollama:

    python backend/server.py     ->  open http://127.0.0.1:8000

Grading is slow (a thinking model on a laptop), so uploads return a job id
immediately and the UI polls /api/jobs/<id> for progress.
"""
import json
import shutil
import smtplib
from email.message import EmailMessage
import threading
import time
import uuid
import webbrowser
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from config import (
    EMAIL_CONFIG_PATH,
    FRONTEND_DIST,
    HOST,
    MAX_DOC_CHARS,
    MODEL,
    OLLAMA_URL,
    OUTPUT_DIR,
    PORT,
    RUBRICS_DIR,
    SECTION_LABELS,
    ensure_directories,
    model_is_available,
    ollama_is_running,
)
from watcher import (EvaluationError, grade_pdf, load_criterion_texts, load_scorecard_templates,
                     compare_runs)


def _max_points() -> int:
    """Total possible score across every rubric criterion."""
    try:
        return sum(len(ids) for ids in load_scorecard_templates().sections.values())
    except Exception:
        return 23


app = FastAPI(title="Program Assessment Screener")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

JOBS: Dict[str, dict] = {}
JOBS_LOCK = threading.Lock()


@dataclass
class Job:
    id: str
    filename: str
    status: str = "queued"          # queued | extracting | grading | done | error
    phase: str = "Waiting to start"
    elapsed: int = 0
    characters: int = 0
    started_at: float = 0.0
    model: Optional[str] = None
    cancelled: bool = False
    result: Optional[dict] = None
    error: Optional[str] = None


def _set_job(job_id: str, **patch) -> None:
    with JOBS_LOCK:
        JOBS[job_id].update(patch)


def _run_grading(job_id: str, pdf_path: Path, output_stem: str, model: Optional[str] = None) -> None:
    def progress(phase: str, elapsed: int, characters: int) -> None:
        _set_job(job_id, status="grading", phase=phase, elapsed=elapsed, characters=characters)

    def should_stop() -> bool:
        with JOBS_LOCK:
            return bool(JOBS.get(job_id, {}).get("cancelled"))

    _set_job(job_id, status="extracting", phase="Extracting text from the PDF", model=model or MODEL)
    started = time.monotonic()
    try:
        result = grade_pdf(pdf_path, progress=progress, output_stem=output_stem,
                           should_stop=should_stop, model=model)
        _set_job(
            job_id,
            status="done",
            phase="Complete",
            elapsed=int(time.monotonic() - started),
            result=result,
        )
    except EvaluationError as exc:
        _set_job(job_id, status="error", phase=str(exc), error=str(exc),
                 elapsed=int(time.monotonic() - started))
    except Exception as exc:  # pragma: no cover - unexpected failures
        _set_job(job_id, status="error", phase=f"Unexpected failure: {exc}", error=f"{type(exc).__name__}: {exc}",
                 elapsed=int(time.monotonic() - started))
    finally:
        if pdf_path.exists():
            pdf_path.unlink()


@app.get("/api/health")
def health():
    templates = None
    try:
        templates = load_scorecard_templates()
        rubric_ready = True
        error = None
    except Exception as exc:
        rubric_ready = False
        error = str(exc)

    return {
        "status": "ok",
        "ollama_running": ollama_is_running(),
        "ollama_url": OLLAMA_URL,
        "model": MODEL,
        "model_available": model_is_available(),
        "rubric_ready": rubric_ready,
        "rubric_error": error,
        "sections": [SECTION_LABELS[key] for key in templates.sections] if templates else [],
        "max_points": templates.max_points if templates else 0,
        "max_doc_chars": MAX_DOC_CHARS,
        "frontend_built": FRONTEND_DIST.exists(),
        "output_dir": str(OUTPUT_DIR),
    }


@app.get("/api/rubrics")
def list_rubrics():
    return sorted(f.name for f in RUBRICS_DIR.glob("*.txt"))


@app.get("/api/jobs")
def list_jobs():
    with JOBS_LOCK:
        return list(JOBS.values())


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    payload = dict(job)
    if payload["result"]:
        # The reasoning trace can be huge; the UI fetches it on demand.
        payload["reasoning_length"] = len(payload["result"].get("reasoning", ""))
    return payload


@app.get("/api/models")
def list_models():
    from config import installed_models

    models = installed_models()
    return {
        "models": [m["name"] for m in models],
        "detail": [{"name": m["name"], "size_gb": round(m["size"] / 1e9, 1)} for m in models],
        "default": MODEL,
    }


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] in ("done", "error"):
        return {"job_id": job_id, "status": job["status"]}
    _set_job(job_id, cancelled=True, phase="Stopping...")
    return {"job_id": job_id, "status": "cancelling"}


@app.post("/api/evaluate")
async def evaluate(file: UploadFile = File(...), model: Optional[str] = Form(None)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files can be evaluated.")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename).name
    temp_path = OUTPUT_DIR / f"upload_{uuid.uuid4().hex[:8]}_{safe_name}"
    with temp_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    job = Job(id=uuid.uuid4().hex, filename=safe_name, started_at=time.monotonic(),
              model=model or MODEL)
    with JOBS_LOCK:
        JOBS[job.id] = asdict(job)

    thread = threading.Thread(
        target=_run_grading,
        args=(job.id, temp_path, Path(safe_name).stem, model),
        daemon=True,
    )
    thread.start()
    return {"job_id": job.id, "filename": safe_name, "model": model or MODEL}


@app.get("/api/jobs/{job_id}/download/{kind}")
def download(job_id: str, kind: str):
    job = JOBS.get(job_id)
    if not job or not job.get("result"):
        raise HTTPException(status_code=404, detail="No completed result for this job")
    files = job["result"]["files"]
    if kind not in files:
        raise HTTPException(status_code=400, detail=f"Unknown download '{kind}'")
    path = Path(files[kind])
    if not path.exists():
        raise HTTPException(status_code=404, detail="File no longer exists")
    media = {"scorecard": "application/json", "detail": "application/json",
             "feedback": "text/markdown", "audit_trail": "text/plain",
             "extracted_text": "text/plain"}[kind]
    return FileResponse(path, media_type=media, filename=path.name)


@app.post("/api/email")
def email_results(job_id: str = Form(...), recipient: str = Form(...)):
    """Send the feedback report by email if SMTP is configured in
    backend/email_config.json. Without config, reports why and returns the
    markdown so nothing is silently lost."""
    job = JOBS.get(job_id)
    if not job or not job.get("result"):
        raise HTTPException(status_code=404, detail="No completed result to send")

    config_path = Path(EMAIL_CONFIG_PATH)
    if not config_path.exists():
        return {
            "status": "not_configured",
            "message": "Email is not configured. Create backend/email_config.json "
                       "with smtp_host, smtp_port, smtp_user, smtp_password, sender "
                       "and use_tls, then try again.",
            "feedback": job["result"]["feedback"],
        }

    config = json.loads(config_path.read_text(encoding="utf-8"))
    result = job["result"]

    message = EmailMessage()
    message["Subject"] = f"Assessment results for {job['filename']}"
    message["From"] = config.get("sender", "")
    message["To"] = recipient
    message.set_content(result["feedback"])

    # Attach the machine-readable scorecard so the committee can archive it.
    scorecard_path = result["files"].get("scorecard")
    if scorecard_path and Path(scorecard_path).exists():
        message.add_attachment(
            Path(scorecard_path).read_text(encoding="utf-8").encode("utf-8"),
            maintype="application",
            subtype="json",
            filename=Path(scorecard_path).name,
        )

    try:
        if config.get("use_ssl", False):
            server = smtplib.SMTP_SSL(config["smtp_host"], config.get("smtp_port", 465), timeout=15)
        else:
            server = smtplib.SMTP(config["smtp_host"], config.get("smtp_port", 587), timeout=15)
        with server:
            if config.get("use_tls", True) and not config.get("use_ssl", False):
                server.starttls()
            if config.get("smtp_user"):
                server.login(config["smtp_user"], config.get("smtp_password", ""))
            server.send_message(message)
    except Exception as exc:
        return {"status": "failed", "message": f"SMTP send failed: {exc}"}

    return {"status": "sent", "message": f"Feedback emailed to {recipient} with the scorecard attached"}


@app.get("/api/results")
def list_saved_results():
    """Previously graded reports found in the Output directory."""
    results = []
    for scorecard in sorted(OUTPUT_DIR.glob("*_scorecard.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(scorecard.read_text(encoding="utf-8"))
        except Exception:
            continue
        results.append({
            "stem": scorecard.stem.removesuffix("_scorecard"),
            "total": data.get("total_calculated_score"),
            "max_points": data.get("max_points_possible", _max_points()),
            "unverified": data.get("unverified_evidence", 0),
            "verified": data.get("verified_score"),
            "modified": scorecard.stat().st_mtime,
        })
    return results


def _saved_result(stem: str) -> dict:
    """Reassemble a completed report from disk so history can be viewed in the UI."""
    scorecard_path = OUTPUT_DIR / f"{stem}_scorecard.json"
    if not scorecard_path.exists():
        raise HTTPException(status_code=404, detail="No saved report with that name")

    scorecard = json.loads(scorecard_path.read_text(encoding="utf-8"))
    detail_path = OUTPUT_DIR / f"{stem}_detail.json"
    detail = json.loads(detail_path.read_text(encoding="utf-8")) if detail_path.exists() else {}

    templates = load_scorecard_templates()
    texts = load_criterion_texts()
    # The scorecard is keyed by section name and already carries the verified
    # evidence, so it is the reliable source for re-rendering a saved report.
    source = scorecard if isinstance(scorecard, dict) else {}

    # Older reports written by the watcher have no counts in detail.json; fall
    # back to the extraction record so the history row still shows page counts.
    extraction_path = OUTPUT_DIR / f"{stem}_extraction.json"
    extraction = {}
    if extraction_path.exists():
        try:
            extraction = json.loads(extraction_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            extraction = {}
    sections = []
    for key, criterion_ids in templates.sections.items():
        raw_section = source.get(key) or {}
        raw_criteria = raw_section.get("criteria") if isinstance(raw_section.get("criteria"), dict) else raw_section
        if not isinstance(raw_criteria, dict):
            raw_criteria = {}
        sections.append({
            "key": key,
            "label": SECTION_LABELS.get(key, key.replace("_", " ").title()),
            "max": len(criterion_ids),
            "score": float(raw_section.get("section_score", 0) or 0),
            "criteria": [
                {
                    "id": cid,
                    "heading": texts.get(cid, cid),
                    "score": float((raw_criteria.get(cid) or {}).get("score", 0) or 0),
                    "evidence": str((raw_criteria.get(cid) or {}).get("evidence", "") or ""),
                    "note": str((raw_criteria.get(cid) or {}).get("note", "") or texts.get(cid, "")),
                    "evidence_verified": (raw_criteria.get(cid) or {}).get("evidence_verified"),
                    "evidence_source": (raw_criteria.get(cid) or {}).get("evidence_source", ""),
                    "review_hint": (raw_criteria.get(cid) or {}).get("review_hint", ""),
                    "possible_missed_point": bool((raw_criteria.get(cid) or {}).get("possible_missed_point", False)),
                }
                for cid in criterion_ids
            ],
        })

    return {
        "scorecard": scorecard,
        "detail": detail,
        "feedback": (OUTPUT_DIR / f"{stem}_feedback.md").read_text(encoding="utf-8")
                     if (OUTPUT_DIR / f"{stem}_feedback.md").exists() else "",
        "sections": sections,
        "summary": str(detail.get("summary", "")),
        "unverified_evidence": int(scorecard.get("unverified_evidence", 0) or 0),
        "missed_point_review": int(scorecard.get("missed_point_review", detail.get("missed_point_review", 0)) or 0),
        "recheck": detail.get("recheck") or {"attempted": False, "changed": 0, "flagged": 0},
        "max_points": scorecard.get("max_points_possible", _max_points()),
        "model": detail.get("model", MODEL),
        "extraction": {
            "pages": detail.get("page_count", 0) or len(extraction.get("pages", []) or []),
            "characters": detail.get("document_characters", 0) or sum(
                len(str(page.get("text", ""))) for page in extraction.get("pages", []) or []
            ),
            "ocr_pages": detail.get("ocr_pages", 0) or sum(
                1 for page in extraction.get("pages", []) or [] if page.get("method") == "ocr"
            ),
            "truncated": bool(detail.get("truncated", False)),
        },
        "files": {
            "scorecard": str(scorecard_path),
            "detail": str(detail_path),
            "feedback": str(OUTPUT_DIR / f"{stem}_feedback.md"),
            "audit_trail": str(OUTPUT_DIR / f"{stem}_audit_trail.txt"),
            "extracted_text": str(OUTPUT_DIR / f"{stem}_extracted.txt"),
        },
    }


@app.get("/api/compare")
def compare_two_runs(a: str, b: str):
    """Diff two saved runs of the same report graded by different models.

    The point is not to pick a winner. Agreement is evidence of stability;
    disagreement is a list of criteria a human must actually read.
    """
    for stem in (a, b):
        safe = Path(stem).name
        if safe != stem or safe.startswith("."):
            raise HTTPException(status_code=400, detail="Invalid report name")
    try:
        return compare_runs(a, b)
    except EvaluationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/results/{stem}")
def get_saved_result(stem: str):
    """Open a previously graded report in the web UI."""
    safe_stem = Path(stem).name
    if safe_stem != stem or safe_stem.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid report name")

    job_id = f"file:{stem}"
    if job_id in JOBS and JOBS[job_id].get("result"):
        return JOBS[job_id]

    result = _saved_result(stem)
    JOBS[job_id] = {
        "id": job_id,
        "filename": stem,
        "status": "done",
        "phase": "Loaded from Output/",
        "elapsed": result["detail"].get("elapsed_seconds", 0),
        "characters": result["extraction"]["characters"],
        "model": result["model"],
        "cancelled": False,
        "error": None,
        "result": result,
    }
    return JOBS[job_id]


@app.get("/api/results/{stem}/{kind}")
def download_saved(stem: str, kind: str):
    suffix = {
        "scorecard": "_scorecard.json",
        "detail": "_detail.json",
        "feedback": "_feedback.md",
        "audit_trail": "_audit_trail.txt",
        "extracted_text": "_extracted.txt",
    }
    if kind not in suffix:
        raise HTTPException(status_code=400, detail=f"Unknown download '{kind}'")
    safe_stem = Path(stem).name
    if safe_stem != stem or safe_stem.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid report name")
    path = OUTPUT_DIR / f"{safe_stem}{suffix[kind]}"
    if not path.exists():
        raise HTTPException(status_code=404, detail="That file does not exist")
    media = {"scorecard": "application/json", "detail": "application/json",
             "feedback": "text/markdown", "audit_trail": "text/plain",
             "extracted_text": "text/plain"}[kind]
    return FileResponse(path, media_type=media, filename=path.name)


def _fallback_page() -> HTMLResponse:
    return HTMLResponse(
        """
        <body style="font-family: system-ui; margin: 40px; line-height: 1.5">
          <h1>The web interface is not built yet</h1>
          <p>Run the launcher (<code>linux_start.sh</code> or <code>windows_start.ps1</code>) from the project
          folder. It installs dependencies, builds <code>frontend/dist</code> if it is
          missing, checks Ollama, and opens this app in your browser.</p>
          <p>The API is live: <a href="/api/health">/api/health</a></p>
        </body>
        """,
        status_code=200,
    )


if FRONTEND_DIST.exists() and (FRONTEND_DIST / "index.html").exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="interface")
else:
    @app.get("/")
    def index():
        return _fallback_page()


def _startup_banner() -> None:
    ensure_directories()
    print("=" * 60)
    print("Program Assessment Screener")
    print("=" * 60)
    if not ollama_is_running():
        print(f"[WARNING] Ollama is not reachable at {OLLAMA_URL}.")
        print("          Start it with:  ollama serve")
    elif not model_is_available():
        print(f"[WARNING] Model '{MODEL}' is not installed.")
        print(f"          Install it with:  ollama pull {MODEL}")
    else:
        print(f"[OK] Model '{MODEL}' is available.")

    if not FRONTEND_DIST.exists():
        print("[WARNING] frontend/dist is missing - run the launcher to build the UI.")
    print(f"Open http://{HOST}:{PORT}")
    print("=" * 60)


if __name__ == "__main__":
    import uvicorn

    _startup_banner()
    try:
        webbrowser.open(f"http://{HOST}:{PORT}")
    except Exception:
        pass  # headless environments simply print the URL
    uvicorn.run(app, host=HOST, port=PORT)
