"""Standalone web app for the AI report screener.

Runs the API and the built React front end from a single process, so a
non-technical user only needs Python and Ollama:

    python backend/server.py     ->  open http://127.0.0.1:8000

Grading is slow (a thinking model on a laptop), so uploads return a job id
immediately and the UI polls /api/jobs/<id> for progress.
"""
import json
import queue
import shutil
import threading
import time
import traceback
import uuid
import webbrowser
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from config import (
    EMAIL_CONFIG_PATH,
    EVALUATE_DIR,
    FRONTEND_DIST,
    HOST,
    MAX_DOC_CHARS,
    MODEL,
    OLLAMA_NUM_CTX,
    OLLAMA_NUM_THREAD,
    OLLAMA_URL,
    OUTPUT_DIR,
    PORT,
    RUBRICS_DIR,
    SECTION_LABELS,
    SINGLE_PASS_CHAR_LIMIT,
    ensure_directories,
    model_is_available,
    ollama_is_running,
)
from excel_report import build_excel_report, EXCEL_MEDIA_TYPE
from console import safe_print as print
from notifications import send_completion_email, valid_recipient
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

# ---------------------------------------------------------------------------
# One FIFO grading worker.
#
# CPU inference on this machine is not safe to run in parallel: two Ollama
# calls at once split the thread budget and make the same report score
# differently depending on how many others were in flight. A single daemon
# worker drains the queue, so every report gets 100% of the allocated threads
# and identical performance no matter how many uploads arrive at once.
# ---------------------------------------------------------------------------
JOB_QUEUE = queue.Queue()
WORKER_STARTED = threading.Event()


def source_pdf_path(stem: str) -> Path:
    """Where the copy of a graded report's original PDF lives."""
    return OUTPUT_DIR / f"{Path(stem).name}_source.pdf"


def enqueue_job(job_id: str, pdf_path: Path, output_stem: str,
                model: Optional[str] = None) -> None:
    """Put a report at the back of the FIFO queue."""
    JOB_QUEUE.put((job_id, Path(pdf_path), output_stem, model))


def _grading_worker_loop() -> None:
    while True:
        job_id, pdf_path, output_stem, model = JOB_QUEUE.get()
        try:
            with JOBS_LOCK:
                job = JOBS.get(job_id)
            if job is None:
                continue
            if job.get("cancelled") or job.get("status") == "cancelled":
                _set_job(job_id, status="cancelled", phase="Cancelled before it started")
                if pdf_path.exists() and pdf_path.resolve() != source_pdf_path(output_stem).resolve():
                    pdf_path.unlink()
                continue
            _run_grading(job_id, pdf_path, output_stem, model)
        except Exception as exc:  # pragma: no cover - the worker must never die
            _set_job(job_id, status="error", phase=f"Worker failure: {exc}", error=str(exc))
        finally:
            JOB_QUEUE.task_done()


def start_grading_worker() -> None:
    """Start the single grading worker exactly once (safe to call repeatedly)."""
    if WORKER_STARTED.is_set():
        return
    WORKER_STARTED.set()
    threading.Thread(target=_grading_worker_loop, daemon=True,
                     name="grading-worker").start()


def queue_status() -> Dict[str, int]:
    queued = running = 0
    with JOBS_LOCK:
        for job in JOBS.values():
            if job["status"] == "queued":
                queued += 1
            elif job["status"] in ("extracting", "grading"):
                running += 1
    return {"queued": queued, "running": running, "worker_started": int(WORKER_STARTED.is_set())}


start_grading_worker()


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
    error_traceback: Optional[str] = None
    error: Optional[str] = None
    delivery_email: Optional[str] = None
    notification: Optional[dict] = None


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
        _set_job(job_id, status="error", phase=f"Unexpected failure: {exc}", error=f"{type(exc).__name__}: {exc}", error_traceback=traceback.format_exc(),
                 elapsed=int(time.monotonic() - started))
    finally:
        # The upload's source PDF is kept in Output/ for auditing; only
        # throwaway temp copies are removed.
        if pdf_path.exists() and pdf_path.resolve() != source_pdf_path(output_stem).resolve():
            pdf_path.unlink()

    # The result is already saved and marked complete before optional delivery.
    job = JOBS[job_id]
    if job.get("result") and job.get("delivery_email"):
        _set_job(job_id, notification={"status": "sending", "message": "Sending completion email..."})
        notification = send_completion_email(job["result"], job["filename"], job["delivery_email"])
        _set_job(job_id, notification=notification)


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
        "single_pass_char_limit": SINGLE_PASS_CHAR_LIMIT,
        "num_ctx": OLLAMA_NUM_CTX,
        "num_thread": OLLAMA_NUM_THREAD,
        "queue": queue_status(),
        "frontend_built": FRONTEND_DIST.exists(),
        "output_dir": str(OUTPUT_DIR),
    }


@app.get("/api/queue")
def queue_endpoint():
    """How many reports are waiting and how many are being graded."""
    return queue_status()


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
    if job["status"] in ("done", "error", "cancelled"):
        return {"job_id": job_id, "status": job["status"]}
    if job["status"] == "queued":
        # Never reached the worker: drop it from the queue outright.
        _set_job(job_id, cancelled=True, status="cancelled",
                 phase="Cancelled before it started")
        return {"job_id": job_id, "status": "cancelled"}
    _set_job(job_id, cancelled=True, phase="Stopping...")
    return {"job_id": job_id, "status": "cancelling"}


@app.post("/api/evaluate")
async def evaluate(file: UploadFile = File(...), model: Optional[str] = Form(None),
                   recipient: Optional[str] = Form(None)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files can be evaluated.")

    recipient = recipient.strip() if recipient else None
    if recipient and not valid_recipient(recipient):
        raise HTTPException(status_code=400, detail="Enter a valid delivery email address.")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename).name
    stem = Path(safe_name).stem
    # The uploaded PDF is persisted as the source of truth for this report,
    # so the graded result can always be traced back to the exact file.
    saved_source = source_pdf_path(stem)
    with saved_source.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    job = Job(id=uuid.uuid4().hex, filename=safe_name, started_at=time.monotonic(),
              model=model or MODEL, delivery_email=recipient)
    with JOBS_LOCK:
        JOBS[job.id] = asdict(job)

    start_grading_worker()
    enqueue_job(job.id, saved_source, stem, model)
    return {"job_id": job.id, "filename": safe_name, "model": model or MODEL,
           "source_pdf": str(saved_source), "queue": queue_status()}


def _excel_response(result: dict, filename: str):
    name = Path(filename).stem
    from urllib.parse import quote
    return Response(build_excel_report(result, filename), media_type=EXCEL_MEDIA_TYPE,
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name + '_evaluation.xlsx', safe='')}"})


@app.get("/api/jobs/{job_id}/download/{kind}")
def download(job_id: str, kind: str):
    job = JOBS.get(job_id)
    if not job or not job.get("result"):
        raise HTTPException(status_code=404, detail="No completed result for this job")
    if kind == "excel":
        return _excel_response(job["result"], job["filename"])
    files = job["result"]["files"]
    if kind not in files:
        raise HTTPException(status_code=400, detail=f"Unknown download '{kind}'")
    path = Path(files[kind])
    if not path.exists():
        raise HTTPException(status_code=404, detail="File no longer exists")
    media = {"scorecard": "application/json", "detail": "application/json",
             "feedback": "text/markdown", "audit_trail": "text/plain",
             "extracted_text": "text/plain", "source_pdf": "application/pdf"}[kind]
    return FileResponse(path, media_type=media, filename=path.name)


@app.post("/api/email")
def email_results(job_id: str = Form(...), recipient: str = Form(...)):
    """Manually send or retry a completion email for an existing result."""
    job = JOBS.get(job_id)
    if not job or not job.get("result"):
        raise HTTPException(status_code=404, detail="No completed result to send")

    notification = send_completion_email(job["result"], job["filename"], recipient.strip())
    _set_job(job_id, notification=notification)
    return notification


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
            "figure_captions": int(detail.get("figure_captions",
                                             extraction.get("figure_captions", 0)) or 0),
            "chunked": bool(detail.get("chunked", False)),
            "single_pass_char_limit": detail.get("single_pass_char_limit", SINGLE_PASS_CHAR_LIMIT),
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
    if Path(stem).name != stem or stem.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid report name")
    if kind == "excel":
        return _excel_response(_saved_result(stem), stem)
    suffix = {
        "scorecard": "_scorecard.json",
        "detail": "_detail.json",
        "feedback": "_feedback.md",
        "audit_trail": "_audit_trail.txt",
        "extracted_text": "_extracted.txt",
        "pdf": "_source.pdf",
        "source": "_source.pdf",
        "source_pdf": "_source.pdf",
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
             "extracted_text": "text/plain", "pdf": "application/pdf",
             "source": "application/pdf", "source_pdf": "application/pdf"}[kind]
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


def start_inbox_watcher():
    """Watch Evaluate/ and push every dropped PDF onto the same FIFO queue.

    Folder drops and web uploads are graded by the same single worker, so an
    upload arriving while a folder drop is in flight never causes two Ollama
    calls to run at once.
    """
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    class _QueueInboxHandler(FileSystemEventHandler):
        def on_created(self, event):
            if event.is_directory:
                return
            path = Path(event.src_path)
            if path.suffix.lower() != ".pdf":
                return
            time.sleep(1.5)  # let the file finish writing/transferring
            job = Job(id=uuid.uuid4().hex, filename=path.name,
                      started_at=time.monotonic(), model=MODEL)
            with JOBS_LOCK:
                JOBS[job.id] = asdict(job)
            start_grading_worker()
            enqueue_job(job.id, path, path.stem, MODEL)
            print(f"[QUEUE] Queued {path.name} from {EVALUATE_DIR}/", flush=True)

    ensure_directories()
    observer = Observer()
    observer.schedule(_QueueInboxHandler(), path=str(EVALUATE_DIR), recursive=False)
    observer.start()
    return observer


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
    print(f"Grading: one report at a time (num_thread={OLLAMA_NUM_THREAD}, "
          f"num_ctx starts at {OLLAMA_NUM_CTX})")
    print("=" * 60)


if __name__ == "__main__":
    import os
    import uvicorn

    _startup_banner()
    if os.environ.get("WATCH_INBOX", "true").lower() not in ("0", "false", "no"):
        start_inbox_watcher()
        print(f"Watching {EVALUATE_DIR}/ for PDFs you drop in.")
    try:
        webbrowser.open(f"http://{HOST}:{PORT}")
    except Exception:
        pass  # headless environments simply print the URL
    uvicorn.run(app, host=HOST, port=PORT)
