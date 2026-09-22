import time
import json
from pathlib import Path
from pypdf import PdfReader
from ollama import chat
from pydantic import BaseModel, Field
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# 1. Define the strict JSON structure for your Rubric
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

def grade_document(file_path):
    print(f"\n[AI] Reading new file: {file_path.name}")
    
    try:
        reader = PdfReader(file_path)
        text = "".join(page.extract_text() for page in reader.pages if page.extract_text())
    except Exception as e:
        print(f"[ERROR] Could not read PDF: {e}")
        return
        
    prompt = f"""
    Grade this document strictly against the following rubric:
    [INSERT YOUR RUBRIC TEXT HERE]
    
    Document Content:
    {text[:25000]}
    """
    
    print(f"[AI] Model is 'thinking' through the rubric (this may take a minute on CPU)...")
    
    try:
        response = chat(
            model="qwen3", 
            messages=[{"role": "user", "content": prompt}],
            format=Scorecard.model_json_schema(), 
            think=True, 
            options={
                "temperature": 0.1,
                "num_ctx": 8192 
            }
        )
        
        reasoning_trace = response.message.thinking
        final_json = response.message.content
        
        # Save the JSON Scorecard to /Output
        json_file = Path("Output") / f"{file_path.stem}_scorecard.json"
        with open(json_file, "w", encoding="utf-8") as f:
            f.write(final_json)
            
        # Save the internal thinking trace to /Output
        audit_file = Path("Output") / f"{file_path.stem}_audit_trail.txt"
        with open(audit_file, "w", encoding="utf-8") as f:
            f.write("MODEL REASONING TRACE:\n======================\n\n" + reasoning_trace)
            
        print(f"[AI] Success! Saved scorecard and audit trail to ./Output/")
        
    except Exception as e:
        print(f"[ERROR] AI processing failed: {e}")

class InboxWatcher(FileSystemEventHandler):
    def on_created(self, event):
        if event.src_path.lower().endswith('.pdf'):
            time.sleep(1.5) 
            grade_document(Path(event.src_path))

# Create the new folders if they don't exist
Path("Evaluate").mkdir(exist_ok=True)
Path("Output").mkdir(exist_ok=True)

# Tell the observer to watch the /Evaluate folder
observer = Observer()
observer.schedule(InboxWatcher(), path="Evaluate", recursive=False)
observer.start()

print("👀 Watching 'Evaluate' folder for new PDFs...")
print("🧠 Active Model: Qwen3 (8.2B) with Thinking enabled.")
print("Press Ctrl+C to stop.")

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    observer.stop()