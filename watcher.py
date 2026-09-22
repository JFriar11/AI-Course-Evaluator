import time
import json
from pathlib import Path
from pypdf import PdfReader
from ollama import chat
from pydantic import BaseModel, Field
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# -------------------------------------------------------------
# Directory Setup
# -------------------------------------------------------------
EVALUATE_DIR = Path("Evaluate")
OUTPUT_DIR = Path("Output")
RUBRICS_DIR = Path("rubrics")

EVALUATE_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)
RUBRICS_DIR.mkdir(exist_ok=True)

# Path to the primary rubric file
ACTIVE_RUBRIC_PATH = RUBRICS_DIR / "active_rubric.txt"

# -------------------------------------------------------------
# 1. JSON Schema Definition
# -------------------------------------------------------------
class Criterion(BaseModel):
    evidence_quotes: list[str] = Field(description="Verbatim quotes from the document")
    rationale: str = Field(description="Explanation of why the score was assigned")
    score: float = Field(description="Numeric score matching the rubric")

class Scorecard(BaseModel):
    administrative: Criterion
    tracking_information: Criterion
    methodology: Criterion
    results: Criterion
    continuous_improvement: Criterion
    total_calculated_score: float

# -------------------------------------------------------------
# 2. Evaluation Logic
# -------------------------------------------------------------
def load_rubric(rubric_path: Path) -> str:
    """Loads the rubric text from disk."""
    if not rubric_path.exists():
        raise FileNotFoundError(
            f"Rubric file not found at: {rubric_path.resolve()}\n"
            f"Please create '{rubric_path.name}' inside the '{RUBRICS_DIR}' folder."
        )
    text = rubric_path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"Rubric file '{rubric_path.name}' is empty.")
    return text

def grade_document(file_path: Path):
    print(f"\n[AI] Reading new file: {file_path.name}")
    
    # Check that rubric is available before doing work
    try:
        rubric_text = load_rubric(ACTIVE_RUBRIC_PATH)
    except Exception as e:
        print(f"[ERROR] Rubric check failed: {e}")
        return

    # Extract text from the PDF
    try:
        reader = PdfReader(file_path)
        raw_text = "".join(page.extract_text() for page in reader.pages if page.extract_text())
        
        # Security Sanitization: Strip invisible/control characters to prevent prompt injection
        text = "".join(c for c in raw_text if c.isprintable() or c in "\n\t\r")
        
        if not text.strip():
            print(f"[ERROR] Could not extract any readable text from {file_path.name}")
            return
    except Exception as e:
        print(f"[ERROR] Could not read PDF: {e}")
        return
    
    prompt = f"""
    Grade this document strictly against the following rubric:

    {rubric_text}
    
    Document Content:
    {text[:25000]}
    """
    
    print(f"[AI] Using rubric from: {ACTIVE_RUBRIC_PATH.name}")
    print(f"[AI] Model is thinking through the evaluation...")
    
    try:
        response = chat(
            model="deepseek-r1:8b", 
            messages=[{"role": "user", "content": prompt}],
            format=Scorecard.model_json_schema(), 
            think=True, 
            options={
                "temperature": 0.1,
                "num_ctx": 8192 
            }
        )
        
        reasoning_trace = response.message.thinking or "No thinking trace returned."
        final_json = response.message.content
        
        # Save output files
        json_file = OUTPUT_DIR / f"{file_path.stem}_scorecard.json"
        with open(json_file, "w", encoding="utf-8") as f:
            f.write(final_json)
            
        audit_file = OUTPUT_DIR / f"{file_path.stem}_audit_trail.txt"
        with open(audit_file, "w", encoding="utf-8") as f:
            f.write("MODEL REASONING TRACE:\n======================\n\n" + reasoning_trace)
            
        print(f"[AI] Success! Saved scorecard and audit trail to ./{OUTPUT_DIR}/")
        
    except Exception as e:
        print(f"[ERROR] AI processing failed: {e}")

# -------------------------------------------------------------
# 3. Watcher Loop
# -------------------------------------------------------------
class InboxWatcher(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        file_path = Path(event.src_path)
        if file_path.suffix.lower() == ".pdf":
            time.sleep(1.5)  # Wait for file write/transfer to finish
            grade_document(file_path)

if __name__ == "__main__":
    observer = Observer()
    observer.schedule(InboxWatcher(), path=str(EVALUATE_DIR), recursive=False)
    observer.start()

    print("=" * 60)
    print("Watcher Active:")
    print(f"   • Drop PDFs into:    ./{EVALUATE_DIR}/")
    print(f"   • Active Rubric:     ./{ACTIVE_RUBRIC_PATH}")
    print(f"   • Output stored in:  ./{OUTPUT_DIR}/")
    print("   • Press Ctrl+C to stop.")
    print("=" * 60)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()