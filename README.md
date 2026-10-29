# AI-Course-Evaluator

## Overview

### Running the web app

The interface is a built React page served by the backend AI harness

```sh
./linux_start.sh      # Linux / macOS
.\windows_start.ps1  # Windows PowerShell
```

The launcher creates `.venv` if it is missing, installs the dependencies in
`backend/requirements.txt`, builds `frontend/dist` if it has not been built,
checks that Ollama is running, and opens `http://127.0.0.1:8000`. Drop a report
PDF onto the page: the local model scores all 23 rubric criteria, the page shows
the evidence and notes behind each score, and the totals are recomputed from the
criterion scores. Each finished report can be downloaded as
`<name>_scorecard.json`, `<name>_feedback.md`, `<name>_detail.json`,
`<name>_audit_trail.txt`, or the extracted text, and can be emailed if SMTP
details are placed in `backend/email_config.json`.

### Automatic completion emails

Save a delivery address using **Save email** before uploading a report. Each new
upload carries that saved address to the backend. After the evaluation output is
saved, the backend automatically sends a completion email, even if the browser is
closed. Existing grading, scoring, and output files are unchanged. Reports
uploaded without a saved address continue to work without email.

Copy `backend/email_config.example.json` to `backend/email_config.json` and fill
in your mail provider's SMTP host, port, username, password (or app password), and
sender address. Port 587 uses STARTTLS by default. For port 465, add
`"use_ssl": true` and `"use_tls": false`. The local configuration is ignored by Git.

#### University Outlook / Microsoft 365 sender

The evaluator supports Microsoft Graph with delegated `Mail.Send`. Users still
enter their own receiving address; only the system's sending account signs in.
No university password or app secret is stored in the email configuration.

One-time setup (university IT may need to complete steps 1–3):

1. In [Microsoft Entra](https://entra.microsoft.com), register a single-tenant app
   named **Program Assessment System** for your university directory. Record its
   **Application (client) ID** and **Directory (tenant) ID**.
2. Under **Authentication**, add the **Mobile and desktop applications** platform
   with redirect URI `http://localhost` for browser sign-in.
3. Under **API permissions**, add **Microsoft Graph > Delegated permissions >
   Mail.Send**. Obtain consent according to university policy. This integration
   does not require application permissions, a client secret, or enabling SMTP.
4. From the project folder, install the updated dependencies:
   `.venv/bin/python -m pip install -r backend/requirements.txt`.
5. Run `.venv/bin/python backend/connect_outlook.py`. Enter the sending account's
   Microsoft sign-in email, tenant ID, and client ID. Complete sign-in and MFA in
   the browser. If consent or sign-in is blocked, ask university IT to approve the
   registration and delegated permission. Setup does not send a test email.
6. After successful sign-in, the script replaces `backend/email_config.json`
   with the Outlook configuration. Restart the existing backend once to load the
   updated code; stop the existing process first to avoid a port-8000 conflict.
7. Save a receiving address in the app, then use a completed report's email button
   to test. Check the sender's **Sent Items** and the recipient's inbox/spam folder.
   New uploads use the receiving address saved before submission.

On Windows, substitute `.venv\Scripts\python.exe` for `.venv/bin/python`.
The local token cache `backend/.outlook_token_cache.json` and email configuration
are excluded from Git. The cache contains sensitive refresh credentials and is
stored with owner-only permissions on macOS/Linux. Tokens refresh silently while
university policy permits; if sign-in expires or is revoked, delivery status asks
you to rerun the connection script. Evaluations remain completed.
Microsoft accepting a message does not guarantee inbox delivery; inspect Sent
Items and any non-delivery notice. SMTP remains available for other providers.

References: [Microsoft Graph sendMail](https://learn.microsoft.com/en-us/graph/api/user-sendmail?view=graph-rest-1.0),
[Microsoft interactive and silent sign-in](https://learn.microsoft.com/en-us/entra/msal/python/getting-started/acquiring-tokens).

The email includes the preliminary assessment status, up to five flagged criteria,
the feedback document as a Markdown attachment, and the JSON scorecard. “Acceptable
to proceed” requires every criterion to earn full credit with verified evidence;
otherwise the email says “Revisions recommended.” This notification rule does not
change evaluation scores, and all findings remain subject to human review.

Email delivery status appears beside the completed job. Missing SMTP configuration
or delivery failures do not fail the evaluation. Use the existing email button to
retry manually; there are no automatic retries.

The model used is chosen automatically from the models installed in Ollama
(deepseek-r1, qwen2.5, qwq, llama3.1, mistral — first match wins). Override it
with `EVAL_MODEL=<model> ./linux_start.sh`.
### PDF conversion setup

Run from the project directory with Python 3.10 or newer:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

On Windows, activate with `.venv\Scripts\activate` instead. Scanned PDFs also
require the Tesseract executable on your PATH (English language data included).
On macOS with Homebrew, install it with `brew install tesseract`; on Ubuntu/Debian,
use `sudo apt install tesseract-ocr`. Windows installation guidance is available
in the [Tesseract documentation](https://tesseract-ocr.github.io/tessdoc/Installation.html).

Convert a PDF without running the model:

```sh
python pdf_extraction.py "path/to/report.pdf"
```

Or run `python watcher.py`, then drop a PDF into `Evaluate/`. The watcher converts
it before sending text to Ollama. Conversion runs locally and writes
`Output/<name>_extracted.txt` with page markers and `<name>_extraction.json` with
per-page text, extraction methods, errors, and readiness status.

Digital pages use [pypdf layout extraction](https://pypdf.readthedocs.io/en/stable/user/extract-text.html)
to retain spacing and approximate table columns. Pages with images or fewer than
40 alphanumeric characters use local OCR. This conservative rule also OCRs pages
with decorative images. Blank pages, failed OCR, and unreadable pages require
review and block grading; inspect the original and supply a corrected PDF before
retrying. OCR and layout extraction do not guarantee correct reading order,
table structure, handwriting, or interpretation of charts. The extracted text
should be checked for important evidence.

Rotated embedded text is included in layout extraction. pypdf may still warn
that rotated text degrades the layout; this warning alone does not block grading.
Check the saved extracted text against the PDF, especially for sideways labels
and tables. Extraction failures print the affected page numbers and errors in
the watcher console as well as saving them in the extraction JSON report.

The current evaluator accepts at most 25,000 extracted characters. Longer PDFs
are fully converted and saved but not graded, avoiding the previous silent
truncation. Both evaluation modes request a 16,384-token Ollama context to
accommodate larger rubrics and reports; this uses more memory than the model's
default context. Chunked evaluation is still future work. The watcher currently
processes newly created files only; add files after starting it.

Run the extraction and grading-gate regression checks:

```sh
python -m unittest discover -s tests -v
```

This project explores the development of an **AI-assisted evaluation system** designed to review institutional reports against a predefined set of requirements or evaluation criteria.

Currently, these reports require significant manual review from faculty and staff. In previous evaluation cycles, reviewers from multiple departments have had to manually read, assess, and score large numbers of reports. This project aims to determine whether AI can assist with that process by providing **consistent, structured, and explainable evaluations** while reducing the amount of manual work required.

The goal is not simply to have an AI assign a grade. Instead, the system should evaluate a report against specific criteria and explain:

* Which requirements were satisfied
* How well each requirement was addressed
* Areas where the report performed well
* Areas that could be improved
* Evidence from the report supporting the evaluation

Human reviewers remain an important part of the process, particularly for validating the system and handling evaluations where additional judgment or context is required.

---

## Problem

Evaluating institutional reports can require significant faculty and staff time.

A typical workflow involves:

1. A report being submitted.
2. Reviewers reading the report.
3. Reviewers comparing the report against established requirements or a rubric.
4. Reviewers assigning scores or evaluations.
5. Feedback being compiled and communicated.

When many reports must be reviewed, this process can require bringing together reviewers from multiple departments and asking them to perform substantial additional grading work.

This project investigates whether AI can assist with this process while maintaining reliable and meaningful evaluations.

---

## Proposed Solution

The system will take two primary inputs:

**1. A submitted report**

The document that needs to be evaluated.

**2. Evaluation criteria**

The rubric, requirements, or rules describing what constitutes a strong report.

The AI will analyze the report against those criteria and generate a structured evaluation.

A potential output could include:

* Overall assessment
* Criterion-by-criterion evaluation
* Supporting evidence from the report
* Strengths
* Areas for improvement
* Missing requirements
* Confidence or uncertainty indicators

The exact evaluation format will be refined as the project develops.

---

## How the AI is kept honest

Local models fill gaps in a document by restating the rubric back to us as if it
were a quotation. The pipeline therefore does not trust the model's output; every
claim is checked afterwards by the script.

**Evidence is required before a score.** The output template orders the fields as
`evidence → note → score`, and the prompt states that if no quote can be copied,
the quote stays empty and the score is `0.0`. Generation order constrains what the
model can commit to.

**Every quote is checked against the text.** `verify_evidence()` normalises the
document and the quoted evidence, then requires five consecutive matching words.
A shorter quote must match in full. Scattered word overlap does not count.

**Rubric restatement is detected.** If the "quote" appears verbatim in the rubric,
it is tagged `evidence_source: "rubric"` and flagged.

**Facts supplied by the script cannot be passed off as quotations.** Deterministic
pre-checks extract verifiable facts (CIM code, academic year, meeting minutes,
PII/A-Number presence) before the model ever reads the document. If the model
copies one of those lines as its evidence, it is tagged `script_fact` and flagged
as not coming from the report.

**Two totals are reported.** `total_calculated_score` sums the model's criterion
scores, recomputed by the script rather than trusted from the model.
`verified_score` counts only criteria whose evidence could be traced to the
document. The interface shows both, e.g. `8.5 / 23 (7.5 evidenced)`.

**Reviewers are pointed at the text.** For every criterion the script could not
verify, `review_hints()` searches the full document for the criterion's own
wording and returns the three most likely passages, shown as
*"Search the report for: …"*. Only unverified criteria get hints.

**Long reports are selected by relevance, not truncated.** 13 of the 110 AY25
reports exceed the 25,000-character budget (the worst is 498,000). Cutting off the
tail silently discards data and teaches the model to invent it. Instead pages are
scored against the rubric headings, irrelevant pages are dropped, and the model is
told which pages were omitted and instructed to score anything it cannot ground
as `0.0`.

**Unverified criteria get one more chance, with the receipts shown.** A score is
not abandoned just because the model's quote was bad. `recheck_criteria()` runs a
second, narrower pass: for each criterion that kept points but lost its quote, the
model is shown the exact passages the script found for that criterion's wording and
asked to either quote one of them or set the score to `0.0`. It is explicitly told
not to invent wording, and the revised answer is run through `verify_evidence()`
again. Recheck is capped (`RECHECK_MAX_CRITERIA`, `RECHECK_TIMEOUT_SECONDS`) so a
report never costs two full grading runs; `detail.json` records
`recheck: {attempted, changed, flagged}` and the UI reports it.

Measured on `thum.pdf`: the earlier pipeline reported `23 / 23` with 10 quotes
that could not be found anywhere in the document. The current pipeline reports
`8.5 / 23`, with 1 unverified quote and a hint pointing the reviewer at the
passage behind each doubtful score. Same model, same PDF.

---

## Validating the AI

A major focus of this project is answering the question:

> **How do we know the AI is doing a good job?**

AI-generated evaluations cannot simply be assumed to be correct.

Historical reports that have already been evaluated by human reviewers will be used to help validate the system.

The initial validation process will follow a workflow similar to:

**Historical Report → AI Evaluation → Human Evaluation → Comparison**

The team can then measure how closely the AI's assessment aligns with previous human evaluations.

When disagreements occur, they can be reviewed to determine whether:

* The AI misunderstood the rubric.
* The AI missed information in the report.
* The prompt or evaluation process needs improvement.
* Human reviewers interpreted the criteria differently.
* The historical evaluation itself may be inconsistent.

This process will allow the system to be improved iteratively rather than relying solely on AI-generated results.

---

## Data Quality and Bias

The quality of the AI evaluation depends heavily on the quality of the information provided to it.

Historical evaluations may contain:

* Differences in reviewer interpretation
* Inconsistent scoring
* Subjective judgments
* Incomplete feedback

Because of this, historical human evaluations should not automatically be treated as perfect ground truth.

Part of the project will involve determining how reliable previous evaluations are and how disagreements between AI and human reviewers should be handled.

The system should ultimately support **consistent, explainable, and evidence-based evaluations** rather than simply reproducing historical scoring patterns.

---

## Privacy and FERPA

Student privacy is an important requirement for this project.

Any reports used during development and testing must comply with **FERPA (Family Educational Rights and Privacy Act)** requirements.

Development data should not contain personally identifiable student information or protected educational records unless appropriate authorization and safeguards are in place.

Whenever possible, development and testing should use:

* Anonymized reports
* De-identified historical data
* Synthetic test documents
* Data specifically approved for project use

Privacy considerations should remain part of the system design throughout development.

---

## Initial Development Plan

### Phase 1 — Understand the Evaluation Process

* Collect sample reports.
* Understand the existing evaluation rubric.
* Identify how reports are currently scored.
* Determine what information reviewers use when making decisions.

### Phase 2 — Build the Initial Prototype

* Create an AI evaluation prompt.
* Provide the AI with the report and evaluation criteria.
* Generate structured evaluations.
* Standardize the AI's output format.

### Phase 3 — Historical Testing

* Run previously evaluated reports through the system.
* Compare AI evaluations against human evaluations.
* Identify areas of agreement and disagreement.

### Phase 4 — Evaluation and Improvement

* Develop metrics for measuring AI performance.
* Review disagreements with subject-matter experts.
* Improve prompts and evaluation logic.
* Test consistency across multiple reports.

### Phase 5 — Human-in-the-Loop Workflow

Explore how the AI system could support the existing evaluation process.

A potential future workflow could be:

`Report Submission → AI Evaluation → Human Review → Final Evaluation`

Rather than completely replacing reviewers, the AI could provide an initial evaluation that allows reviewers to focus their attention on ambiguous or difficult cases.

---

## Current Status

**Project Stage:** Early Research / Prototype Development

The current focus is on:

* Analyzing sample reports
* Created first draft of UI
* Built an initial model
* Implementing RAG
* Determining how AI performance will be measured

---

## Project Goals

The project will investigate whether an AI-assisted evaluation system can:

* Reduce manual evaluation workload
* Produce consistent evaluations
* Provide useful and actionable feedback
* Explain the reasoning behind evaluations
* Identify missing or weak report requirements
* Align reasonably with expert human judgment
* Protect student privacy and comply with FERPA requirements
* Support human reviewers rather than requiring them to evaluate every report entirely from scratch

---

## Key Research Question

> **Can an AI system evaluate institutional reports accurately, consistently, and fairly enough to meaningfully assist human reviewers while reducing the amount of manual evaluation required?**
