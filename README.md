# AI-Course-Evaluator

## Overview

### PDF conversion setup

Run from the project directory with Python 3.10 or newer:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
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

The current evaluator accepts at most 25,000 extracted characters. Longer PDFs
are fully converted and saved but not graded, avoiding the previous silent
truncation. Chunked evaluation is still future work. The watcher currently
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
