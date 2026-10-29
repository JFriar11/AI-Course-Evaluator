import json
import re
import tempfile
import time
import unittest
from threading import Thread
from pathlib import Path
from unittest.mock import patch
from ollama import ChatResponse

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from pdf_extraction import Extraction, PageText, extract_pdf, save_extraction
import pdf_extraction
import watcher
from config import MAX_DOC_CHARS


def make_pdf(path, contents, rotated_text=None):
    writer = PdfWriter()
    for text in contents:
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
                                 NameObject('/Subtype'): NameObject('/Type1'),
                                 NameObject('/BaseFont'): NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({
            NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
        stream = DecodedStreamObject()
        commands = f'BT /F1 12 Tf 50 700 Td ({text}) Tj ET'
        if rotated_text:
            commands += f' BT /F1 12 Tf 0 1 -1 0 100 100 Tm ({rotated_text}) Tj ET'
        stream.set_data(commands.encode())
        page[NameObject('/Contents')] = writer._add_object(stream)
    writer.write(path)


def model_output_json(templates, score=1.0):
    """A realistic model response: every criterion with evidence and a note."""
    payload = {}
    for section, criteria in templates.sections.items():
        payload[section] = {
            "criteria": {
                criterion: {"score": score, "evidence": "stated in the report", "note": "meets the criterion"}
                for criterion in criteria
            },
            "section_score": score * len(criteria),
        }
    payload["summary"] = "The report addresses every section of the rubric."
    payload["total_calculated_score"] = score * templates.max_points
    return json.dumps(payload)


class ExtractionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pdf = self.root / 'report.pdf'
        self.text = 'Students demonstrated the required learning outcomes in the final assessment.'

    def grade_with_mock(self, chat, print_output=None):
        """Run grade_document with the model and Ollama probes mocked out."""
        patches = [
            patch.object(watcher, 'OUTPUT_DIR', self.root),
            patch.object(watcher, 'load_full_rubric', return_value='Rubric text'),
            patch.object(watcher, 'ollama_is_running', return_value=True),
            patch.object(watcher, 'model_is_available', return_value=True),
            patch.object(watcher, 'chat', return_value=chat),
        ]
        if print_output is not None:
            patches.append(patch('builtins.print', new=print_output))
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            if print_output is not None:
                with patch('builtins.print', new=print_output):
                    watcher.grade_document(self.pdf)
            else:
                watcher.grade_document(self.pdf)

    def test_digital_pdf_preserves_pages_and_saved_text(self):
        make_pdf(self.pdf, [self.text, self.text])
        with patch('pdf_extraction.ocr_page') as ocr:
            result = extract_pdf(self.pdf)
        ocr.assert_not_called()
        self.assertTrue(result.ready)
        self.assertIn('--- Page 2 ---', result.text)
        self.assertEqual(result.pages[0].text, self.text)
        path = save_extraction(result, self.root, 'report')
        self.assertEqual(path.read_text(), result.text)

    def test_rotated_text_is_retained_alongside_upright_text(self):
        rotated = 'Assessment evidence printed sideways'
        make_pdf(self.pdf, [self.text], rotated_text=rotated)
        with patch('pdf_extraction.ocr_page') as ocr:
            result = extract_pdf(self.pdf)
        ocr.assert_not_called()
        self.assertTrue(result.ready)
        self.assertIn(self.text, result.text)
        self.assertIn(rotated, result.text)

    def test_mixed_pdf_uses_ocr_for_scanned_page(self):
        make_pdf(self.pdf, [self.text, ''])
        with patch('pdf_extraction.ocr_page', return_value=self.text) as ocr:
            result = extract_pdf(self.pdf)
        ocr.assert_called_once_with(self.pdf, 1)
        self.assertTrue(result.ready)
        self.assertEqual([p.method for p in result.pages], ['embedded', 'ocr'])

    def test_failed_page_blocks_evaluation_and_is_saved(self):
        make_pdf(self.pdf, [self.text, ''])
        printed = []
        with patch('pdf_extraction.ocr_page', side_effect=RuntimeError('OCR missing')), \
             patch.object(watcher, 'OUTPUT_DIR', self.root), \
             patch.object(watcher, 'load_full_rubric', return_value='Rubric text'), \
             patch.object(watcher, 'ollama_is_running', return_value=True), \
             patch.object(watcher, 'model_is_available', return_value=True), \
             patch('builtins.print', new=lambda *a, **k: printed.append(' '.join(str(x) for x in a))), \
             patch.object(watcher, 'chat') as chat:
            watcher.grade_document(self.pdf)
        chat.assert_not_called()
        self.assertTrue(any('could not be read' in line for line in printed))
        self.assertTrue((self.root / 'report_extraction.json').exists())
        self.assertIn('OCR missing', (self.root / 'report_extraction.json').read_text())

    def test_empty_ocr_requires_review(self):
        make_pdf(self.pdf, [''])
        with patch('pdf_extraction.ocr_page', return_value=''):
            self.assertFalse(extract_pdf(self.pdf).ready)

    def test_corrupt_pdf_is_rejected(self):
        self.pdf.write_bytes(b'not a pdf')
        with self.assertRaises(Exception):
            extract_pdf(self.pdf)

    def test_password_protected_pdf_is_rejected(self):
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        writer.encrypt('secret')
        writer.write(self.pdf)
        with self.assertRaisesRegex(ValueError, 'Password-protected'):
            extract_pdf(self.pdf)

    def test_agent_receives_saved_page_marked_text(self):
        make_pdf(self.pdf, [self.text])
        templates = watcher.load_scorecard_templates()
        payload = model_output_json(templates)
        chat = iter([
            ChatResponse(message={'role': 'assistant', 'thinking': 'Reviewing'}),
            ChatResponse(message={'role': 'assistant', 'content': payload[:40]}),
            ChatResponse(message={'role': 'assistant', 'content': payload[40:]}, done=True),
        ])
        with patch.object(watcher, 'OUTPUT_DIR', self.root), \
             patch.object(watcher, 'load_full_rubric', return_value='Rubric text'), \
             patch.object(watcher, 'ollama_is_running', return_value=True), \
             patch.object(watcher, 'model_is_available', return_value=True), \
             patch.object(watcher, 'RECHECK_UNVERIFIED', False), \
             patch.object(watcher, 'chat') as mock_chat:
            mock_chat.return_value = chat
            watcher.grade_document(self.pdf)
        mock_chat.assert_called_once()
        self.assertTrue(mock_chat.call_args.kwargs['stream'])
        self.assertEqual(
            mock_chat.call_args.kwargs['options']['num_ctx'],
            watcher.MODEL_CONTEXT_TOKENS,
        )
        self.assertEqual(mock_chat.call_args.kwargs['format'], templates.schema)

        scorecard = json.loads((self.root / 'report_scorecard.json').read_text())
        self.assertEqual(scorecard['total_calculated_score'], templates.max_points)
        entry = scorecard['administrative']['criteria']['1.1']
        self.assertEqual(entry['score'], 1.0)
        self.assertEqual(entry['evidence'], 'stated in the report')
        self.assertIn('evidence_verified', entry)
        self.assertEqual(scorecard['administrative']['section_score'], 1.0)

        detail = json.loads((self.root / 'report_detail.json').read_text())
        self.assertEqual(
            detail['raw_model_output']['administrative']['criteria']['1.1']['evidence'],
            'stated in the report',
        )
        # The reviewer-facing view is written alongside the raw model output.
        self.assertEqual(detail['sections'][0]['label'], 'Section 1 - Administrative')
        self.assertIn('unverified_evidence', detail)

        feedback = (self.root / 'report_feedback.md').read_text()
        self.assertIn('Criterion 1.1', feedback)
        self.assertIn('Section 1 - Administrative', feedback)

        self.assertIn('Reviewing', (self.root / 'report_audit_trail.txt').read_text())

        prompt = mock_chat.call_args.kwargs['messages'][0]['content']
        saved = (self.root / 'report_extracted.txt').read_text()
        self.assertIn(saved, prompt)
        self.assertIn(templates.instructions, prompt)
        self.assertIn(templates.model_template, prompt)
        self.assertIn('"5.5"', templates.json_template)

    def test_scorecard_schema_comes_from_output_template(self):
        templates = watcher.load_scorecard_templates()
        self.assertEqual(templates.schema['type'], 'object')
        self.assertEqual(
            templates.schema['properties']['administrative']['properties']['criteria']
            ['properties']['1.1'],
            {'type': 'object',
             'properties': {'evidence': {'type': 'string'},
                            'note': {'type': 'string'},
                            'score': {'type': 'number'}},
             'required': ['evidence', 'note', 'score'],
             'additionalProperties': False},
        )
        self.assertEqual(templates.max_points, 23.0)
        # Evidence precedes score on purpose: the model must cite before it
        # credits, which curbs invented justification for an inflated score.
        first_field = list(json.loads(templates.model_template)['administrative']['criteria']['1.1'])[0]
        self.assertEqual(first_field, 'evidence')

    def test_full_rubric_contains_every_section(self):
        rubric = watcher.load_full_rubric()
        for criterion in ['1.1', '2.8', '3.4', '4.5', '5.5']:
            self.assertIn(criterion, rubric)

    def test_long_documents_keep_rubric_relevant_pages(self):
        pages = [
            PageText(1, "Program Assessment Report BS-CHE AY2025-26 CIM code BS-CHE", "embedded"),
            PageText(2, "A long unrelated narrative about campus landscaping " * 60, "embedded"),
            PageText(3, "Rubric Table 1 Learning goal 1 average percentage of students meeting goal 1", "embedded"),
            PageText(4, "Another unrelated narrative about parking " * 60, "embedded"),
            PageText(5, "Program authority meeting minutes attached discussion of goals", "embedded"),
        ]
        criteria = {
            "1.1": "Uniform Template Used",
            "3.1": "Rubric Table 1 included with a minimum of 1 goal",
            "5.1": "Program authority discussion of results",
        }
        selected = watcher.select_relevant_pages(pages, criteria, 1200)
        kept = [int(n) for n in re.findall(r"--- Page (\d+) ---", selected)]
        self.assertIn(1, kept)
        self.assertIn(3, kept)
        self.assertIn(5, kept)
        self.assertNotIn(2, kept)
        self.assertLessEqual(len(selected), 1200 + 400)

    def test_long_documents_are_marked_as_partial(self):
        pages = [PageText(i, "report page " * 400, "embedded") for i in range(1, 60)]
        full = watcher.select_relevant_pages(pages, {"1.1": "Uniform Template Used"}, 1000)
        annotated = full + watcher.relevance_note("\n\n".join(p.text for p in pages), full)
        self.assertIn("[NOTE: this report is", annotated)
        self.assertLessEqual(len(full), 1400)

    def test_facts_block_cannot_be_misused_as_evidence(self):
        # A fact the script actually confirmed for this criterion grounds the
        # score (source "script_check"). An echo of the facts block for a
        # criterion the script never checked does not.
        facts = {"4.5": "No A-Number-style or 7-8 digit student identifiers detected."}
        sections = [{
            "key": "results",
            "criteria": [
                {"id": "4.5", "score": 1.0,
                 "evidence": "No A-Number-style or 7-8 digit student identifiers detected"},
                {"id": "3.1", "score": 1.0,
                 "evidence": "No A-Number-style or 7-8 digit student identifiers detected"},
            ],
        }]
        unverified = watcher.verify_evidence(sections, "A report with no numbers.", "Rubric text here.", facts)
        self.assertEqual(unverified, 1)
        self.assertEqual(sections[0]["criteria"][0]["evidence_source"], "script_check")
        self.assertTrue(sections[0]["criteria"][0]["evidence_verified"])
        self.assertEqual(sections[0]["criteria"][1]["evidence_source"], "script_fact")
        self.assertFalse(sections[0]["criteria"][1]["evidence_verified"])

    def test_genuine_quote_is_confirmed_and_not_mislabelled(self):
        sections = [{
            "key": "results",
            "criteria": [{"id": "3.1", "score": 1.0,
                         "evidence": "the committee collected nine artifacts"}],
        }]
        watcher.verify_evidence(
            sections,
            "In 2025 the committee collected nine artifacts from four courses.",
            "Criterion 3.1: Rubric Table included with a minimum of one goal",
            {"3.1": "Artifacts found: nine artifacts"},
        )
        self.assertTrue(sections[0]["criteria"][0]["evidence_verified"])
        self.assertEqual(sections[0]["criteria"][0]["evidence_source"], "document")

    def test_script_confirmed_fact_counts_as_grounding(self):
        sections = [{
            "key": "tracking_information",
            "criteria": [{"id": "2.1", "score": 1.0, "evidence": "", "note": "code present"}],
        }]
        unverified = watcher.verify_evidence(
            sections, "BS-ARCE program", "Criterion 2.1: CIM Code", {"2.1": "Program code present: BS-ARCE"}
        )
        self.assertEqual(unverified, 0)
        self.assertTrue(sections[0]["criteria"][0]["evidence_verified"])
        self.assertEqual(sections[0]["criteria"][0]["evidence_source"], "script_check")

    def test_review_hints_point_the_reviewer_at_the_text(self):
        document = (
            "The capstone rubric contains four levels of achievement. "
            "Faculty discussed the results at the November meeting. "
            "Student work samples were collected in ART 402."
        )
        criteria = {"3.3": "Criterion 3.3: levels of achievement defined for each rubric row",
                    "5.1": "Criterion 5.1: faculty meeting discussed results"}
        scorecard = {"methodology": {"criteria": {"3.3": {"score": 1.0, "evidence_verified": False}}},
                     "continuous_improvement": {"criteria": {"5.1": {"score": 1.0, "evidence_verified": False}}}}
        hints = watcher.review_hints(document, criteria, scorecard)
        self.assertIn("3.3", hints)
        self.assertIn("5.1", hints)
        self.assertTrue("levels of achievement" in hints["3.3"].lower())

    def test_review_hints_are_only_generated_for_unverified_criteria(self):
        document = (
            "The capstone rubric contains four levels of achievement. "
            "Faculty discussed the results at the November meeting."
        )
        criteria = {"3.3": "Criterion 3.3: levels of achievement defined for each rubric row",
                    "3.4": "Criterion 3.4: rubric rows describe levels of achievement"}
        scorecard = {"methodology": {"criteria": {
            "3.3": {"score": 1.0, "evidence_verified": False},
            "3.4": {"score": 1.0, "evidence_verified": True},
        }}}
        hints = watcher.review_hints(document, criteria, scorecard)
        self.assertIn("3.3", hints)
        self.assertNotIn("3.4", hints)

    def test_deterministic_checks_report_verifiable_facts(self):


        facts = watcher.deterministic_checks(
            "Assessment of BS in Chemistry (BS-CHE), AY2025-26. "
            "Minutes of the program authority meeting attached. "
            "Student A-1234567 scored above the threshold."
        )
        self.assertIn("BS-CHE", facts["2.1"])
        self.assertIn("AY2025", facts["2.3"])
        self.assertIn("meeting", facts["2.8"])
        self.assertIn("A-1234567", facts["4.5"])

    def test_deterministic_checks_report_absence_honestly(self):
        facts = watcher.deterministic_checks("A narrative about teaching methods.")
        self.assertIn("No CIM code", facts["2.1"])
        self.assertIn("No academic year", facts["2.3"])

    def test_rubric_restatement_is_flagged(self):

        rubric = "Criterion 5.5: Administrative Implementation Process Described"
        sections = [{'key': 'results', 'label': 'S5', 'max': 1,
                     'criteria': [{'id': '5.5', 'score': 1.0,
                                   'evidence': 'Administrative Implementation Process Described',
                                   'note': ''}]}]
        watcher.verify_evidence(sections, "the program added a new course in spring.", rubric)
        self.assertEqual(sections[0]['criteria'][0]['evidence_source'], 'rubric')
        self.assertFalse(sections[0]['criteria'][0]['evidence_verified'])

    def test_scattered_word_matches_do_not_count_as_evidence(self):

        sections = [{'key': 'administrative', 'label': 'S1', 'max': 1,
                     'criteria': [{'id': '1.1', 'score': 1.0,
                                   'evidence': 'minutes of the meeting attached appendix',
                                   'note': ''}]}]
        document = 'the meeting attached some minutes and an appendix was mailed separately'
        watcher.verify_evidence(sections, document)
        self.assertFalse(sections[0]['criteria'][0]['evidence_verified'])

    def test_evidence_verification_flags_quotes_not_in_the_document(self):
        doc = "The CIM code listed on the form is BAC-ARCT. Minutes were not attached."
        sections = [
            {
                "key": "tracking_information",
                "label": "Tracking information",
                "max": 2,
                "score": 2,
                "criteria": [
                    {"id": "2.1", "score": 1.0, "evidence": "The CIM code listed on the form is BAC-ARCT"},
                    {"id": "2.8", "score": 1.0, "evidence": "Minutes of the meeting are attached hereto"},
                ],
            }
        ]
        unverified = watcher.verify_evidence(sections, doc)
        self.assertEqual(unverified, 1)
        self.assertTrue(sections[0]["criteria"][0]["evidence_verified"])
        self.assertFalse(sections[0]["criteria"][1]["evidence_verified"])

    def test_totals_are_recomputed_and_scores_clamped(self):
        templates = watcher.load_scorecard_templates()
        sloppy = {
            "administrative": {"criteria": {"1.1": {"score": 0.4}}, "section_score": 5},
            "tracking_information": {"criteria": {c: {"score": 1} for c in templates.sections["tracking_information"]},
                                     "section_score": 8},
            "methodology": {"criteria": {c: {"score": 1.3} for c in templates.sections["methodology"]},
                            "section_score": 4},
            "results": {"criteria": {c: {"score": 0.5} for c in templates.sections["results"]},
                        "section_score": 2.5},
            "continuous_improvement": {"criteria": {c: {"score": 0.5} for c in templates.sections["continuous_improvement"]},
                                       "section_score": 2.5},
            "summary": "Summary",
            "total_calculated_score": 99,
        }
        scorecard = watcher.build_scorecard(sloppy, templates)
        self.assertEqual(scorecard['administrative']['criteria']['1.1']['score'], 0.5)
        self.assertEqual(scorecard['methodology']['criteria']['3.1']['score'], 1.0)
        self.assertEqual(scorecard['administrative']['section_score'], 0.5)
        self.assertEqual(
            scorecard['total_calculated_score'],
            sum(section['section_score'] for section in scorecard.values() if isinstance(section, dict)),
        )
        self.assertLessEqual(scorecard['total_calculated_score'], templates.max_points)

    def test_incomplete_model_stream_does_not_save_scorecard(self):
        make_pdf(self.pdf, [self.text])
        printed = []
        chat = patch.object(watcher, 'chat', return_value=iter([
            ChatResponse(message={'role': 'assistant', 'content': '{'})
        ]))
        with patch.object(watcher, 'OUTPUT_DIR', self.root), \
             patch.object(watcher, 'load_full_rubric', return_value='Rubric text'), \
             patch.object(watcher, 'ollama_is_running', return_value=True), \
             patch.object(watcher, 'model_is_available', return_value=True), \
             patch('builtins.print', new=lambda *a, **k: printed.append(' '.join(str(x) for x in a))), \
             chat:
            watcher.grade_document(self.pdf)
        self.assertFalse((self.root / 'report_scorecard.json').exists())
        self.assertTrue(any('incomplete or empty' in line for line in printed))

    def test_long_document_is_truncated_openly_not_silently(self):
        make_pdf(self.pdf, ['x' * 100, 'M' * 30000, 'y' * 100])
        printed = []
        with patch.object(watcher, 'OUTPUT_DIR', self.root), \
             patch.object(watcher, 'load_full_rubric', return_value='Rubric text'), \
             patch.object(watcher, 'ollama_is_running', return_value=True), \
             patch.object(watcher, 'model_is_available', return_value=True), \
             patch('builtins.print', new=lambda *a, **k: printed.append(' '.join(str(x) for x in a))), \
             patch.object(watcher, 'chat') as chat:
            watcher.grade_document(self.pdf)

        # The whole document is still saved for the human reviewer.
        saved = (self.root / 'report_extracted.txt').read_text()
        self.assertIn('M' * 24000, saved)

        # The document section handed to the model is capped, says so, and keeps both ends.
        prompt = chat.call_args.kwargs['messages'][0]['content']
        document = prompt.split('Document Content:', 1)[1].rsplit('Treat the document content', 1)[0]
        self.assertLess(len(document), MAX_DOC_CHARS + 500)
        self.assertIn('Only the pages most relevant', document)
        self.assertTrue('omitted' in ' '.join(printed))
        self.assertNotIn('M' * 24000, document)
        self.assertIn('x' * 100, document)
        self.assertIn('y' * 100, document)

    def test_readable_pages_never_invoke_ocr(self):
        make_pdf(self.pdf, [self.text])
        with patch.object(pdf_extraction, 'ocr_page', side_effect=RuntimeError('tesseract missing')) as ocr:
            result = pdf_extraction.extract_pdf(self.pdf)
        ocr.assert_not_called()
        self.assertTrue(result.ready)
        self.assertEqual(result.pages[0].method, 'embedded')

    def test_thin_page_surfaces_an_install_hint_when_ocr_is_unavailable(self):
        make_pdf(self.pdf, ['scanned figure caption'])
        with patch.object(pdf_extraction, 'ocr_page', side_effect=RuntimeError('Tesseract is not installed')):
            result = pdf_extraction.extract_pdf(self.pdf)
        self.assertFalse(result.ready)
        self.assertIn('Tesseract is not installed', result.pages[0].error or '')
        self.assertTrue(result.pages[0].needs_manual_review)

    def test_progress_callback_reports_phase_elapsed_and_characters(self):
        chunks = [
            ChatResponse(message={'role': 'assistant', 'thinking': 'reviewing the rubric'}),
            ChatResponse(message={'role': 'assistant', 'content': '{"summary": "ok"}'}),
            ChatResponse(message={'role': 'assistant', 'content': ''}, done=True),
        ]

        def slow_stream():
            for chunk in chunks:
                time.sleep(0.12)
                yield chunk

        reports = []
        with patch.object(watcher, 'chat', return_value=slow_stream()), \
             patch('builtins.print', new=lambda *a, **k: None):
            raw, reasoning = watcher.stream_evaluation(
                progress=lambda phase, elapsed, characters: reports.append((phase, elapsed, characters)),
                progress_interval=0.05,
                model='test-model',
            )

        self.assertEqual(raw, '{"summary": "ok"}')
        self.assertEqual(reasoning, 'reviewing the rubric')
        self.assertTrue(reports, 'progress callback never fired')
        self.assertTrue(all(len(report) == 3 for report in reports))
        self.assertGreater(reports[-1][2], 0)
        self.assertEqual(reports[-1][0], 'Receiving scorecard')

    def test_job_progress_reaches_the_web_job_record(self):
        """The web server forwards watcher progress into the job record."""
        import server

        job_id = 'test-job'
        server.JOBS[job_id] = {'id': job_id, 'filename': 'x.pdf', 'status': 'queued',
                               'phase': 'Waiting to start', 'elapsed': 0, 'characters': 0,
                               'started_at': time.monotonic(), 'cancelled': False}
        with patch.object(server, 'grade_pdf',
                          side_effect=watcher.EvaluationError('boom')), \
             patch.object(server.time, 'monotonic', return_value=1000.0):
            server._run_grading(job_id, Path(self.root / 'missing.pdf'), 'missing')

        job = server.JOBS[job_id]
        self.assertEqual(job['status'], 'error')
        self.assertIn('boom', job['error'])
        del server.JOBS[job_id]

    def test_cancel_flag_stops_the_stream_mid_response(self):
        stop_after = {'n': 3}

        def fake_stream():
            for _ in range(50):
                yield ChatResponse(message={'role': 'assistant', 'content': 'x' * 20})
                time.sleep(0.05)

        with patch.object(watcher, 'chat', return_value=fake_stream()), \
             patch('builtins.print', new=lambda *a, **k: None):
            def should_stop():
                return stop_after['n'] <= 0

            def countdown():
                time.sleep(0.18)
                stop_after['n'] = 0

            thread = Thread(target=countdown)
            thread.start()
            try:
                watcher.stream_evaluation(should_stop=should_stop, progress_interval=1, model='test-model')
                self.fail('the stream should have been stopped')
            except watcher.EvaluationError as exc:
                self.assertIn('stopped', str(exc))
            thread.join()

    def test_cancel_endpoint_marks_the_job_cancelled(self):
        import server

        job_id = 'cancel-endpoint'
        server.JOBS[job_id] = {'id': job_id, 'filename': 'x.pdf', 'status': 'grading',
                              'phase': 'Receiving scorecard', 'elapsed': 30, 'characters': 10,
                              'started_at': time.monotonic(), 'cancelled': False}
        response = server.cancel_job(job_id)
        self.assertEqual(response['status'], 'cancelling')
        self.assertTrue(server.JOBS[job_id]['cancelled'])
        del server.JOBS[job_id]

    def test_email_endpoint_reports_missing_config_instead_of_failing(self):
        import server

        job_id = 'email-endpoint'
        server.JOBS[job_id] = {'id': job_id, 'filename': 'x.pdf', 'status': 'done',
                              'result': {'feedback': '## Criterion 1.1', 'files': {}}}
        with patch('notifications.EMAIL_CONFIG_PATH', self.root / 'no-such-config.json'):
            response = server.email_results(job_id=job_id, recipient='committee@example.edu')
        self.assertEqual(response['status'], 'not_configured')
        self.assertIn('email_config.json', response['message'])
        del server.JOBS[job_id]

    def test_email_endpoint_sends_when_smtp_is_configured(self):
        import server

        job_id = 'email-send-test'
        scorecard = self.root / 'send_scorecard.json'
        scorecard.write_text('{"total_calculated_score": 12.5}')
        server.JOBS[job_id] = {'id': job_id, 'filename': 'x.pdf', 'status': 'done',
                              'result': {'feedback': '## Criterion 1.1', 'scorecard': {},
                                         'files': {'scorecard': str(scorecard)}}}
        config = self.root / 'email_config.json'
        config.write_text(json.dumps({'smtp_host': '127.0.0.1', 'smtp_port': 1025,
                                     'sender': 'screener@local.test', 'use_tls': False}))

        captured = []

        class FakeSMTP:
            def __init__(self, host, port, timeout=None):
                captured.append((host, port))
            def __enter__(self):
                return self
            def __exit__(self, *exc):
                return False
            def send_message(self, message):
                captured.append(message)

        with patch('notifications.EMAIL_CONFIG_PATH', config), \
             patch('notifications.smtplib') as smtplib_module:
            smtplib_module.SMTP = FakeSMTP
            response = server.email_results(job_id=job_id, recipient='committee@example.edu')

        self.assertEqual(response['status'], 'sent')
        self.assertEqual(list(captured[1].iter_attachments())[0].get_payload(decode=True).decode(), '## Criterion 1.1')
        self.assertEqual(list(captured[1].iter_attachments())[1].get_filename(), 'assessment_scorecard.json')
        del server.JOBS[job_id]

    def test_grading_aborts_when_the_model_runs_past_the_timeout(self):
        def fake_stream():
            while True:
                yield ChatResponse(message={'role': 'assistant', 'content': 'x' * 40})
                time.sleep(0.05)

        with patch.object(watcher, 'chat', return_value=fake_stream()), \
             patch('builtins.print', new=lambda *a, **k: None):
            try:
                watcher.stream_evaluation(timeout=0.2, progress_interval=0.1)
                self.fail('the stream should have timed out')
            except watcher.EvaluationError as exc:
                self.assertIn('grading limit', str(exc))

    def test_recheck_prompt_shows_found_passages_not_the_model_guess(self):
        flagged = [{"id": "4.5", "heading": "PII Redacted", "evidence": "made up quote", "score": 1.0}]
        prompt = watcher.build_recheck_prompt(flagged, [], {"4.5": "no names appear here | page 3"}, "RUBRIC TEXT")
        self.assertIn("made up quote", prompt)
        self.assertIn("no names appear here", prompt)
        self.assertIn("do not invent wording", prompt.lower())

    def test_recheck_criteria_replaces_a_fabricated_quote_with_a_real_one(self):
        sections = [{
            "key": "results",
            "criteria": [
                {"id": "4.5", "heading": "PII Redacted", "score": 1.0,
                 "evidence": "fabricated quote", "note": "", "evidence_verified": False},
            ],
        }]

        def fake_eval(**kwargs):
            payload = json.dumps({"criteria": {
                "4.5": {"evidence": "no student names appear in this report",
                        "note": "found", "score": 0.5}
            }})
            return payload, "trace"

        with patch.object(watcher, "stream_evaluation", fake_eval):
            changed = watcher.recheck_criteria(
                sections,
                {"4.5": "no student names appear in this report"},
                "rubric",
                "model",
            )

        self.assertEqual(changed["changed"], 1)
        criterion = sections[0]["criteria"][0]
        self.assertEqual(criterion["score"], 0.5)
        self.assertIn("no student names", criterion["evidence"])

        unverified = watcher.verify_evidence(
            sections, "The report says: no student names appear in this report.", "rubric text", {}
        )
        self.assertEqual(unverified, 0)
        self.assertTrue(sections[0]["criteria"][0]["evidence_verified"])

    def test_zero_sweep_raises_a_point_the_model_missed(self):
        sections = [{
            "key": "results",
            "criteria": [
                {"id": "3.3", "heading": "Levels of Achievement", "score": 0.0,
                 "evidence": "", "note": "no rubric levels mentioned",
                 "evidence_verified": True, "evidence_source": "none"},
            ],
        }]
        missed = watcher.flag_missed_points(
            "The capstone rubric has four levels: exceeds, meets, approaches, below.",
            {"3.3": "Levels of Achievement Included in the Rubric. Submission of "
                    "representative student work samples across performance levels."},
            sections, {},
        )
        self.assertEqual(len(missed), 1)

        def fake_eval(**kwargs):
            return json.dumps({"criteria": {
                "3.3": {"evidence": "The capstone rubric has four levels: exceeds, meets, approaches, below.",
                        "note": "found in the rubric table", "score": 1.0}
            }}), "trace"

        with patch.object(watcher, "stream_evaluation", fake_eval):
            result = watcher.recheck_criteria(sections, {}, "rubric", "model", missed=missed)

        self.assertEqual(result["under_credited"], 1)
        self.assertEqual(result["changed"], 1)
        self.assertEqual(sections[0]["criteria"][0]["score"], 1.0)

    def test_recheck_prompt_names_both_groups_of_criteria(self):
        prompt = watcher.build_recheck_prompt(
            [{"id": "4.5", "heading": "PII Redacted", "score": 1.0, "evidence": "invented"}],
            [{"id": "3.3", "heading": "Levels of Achievement", "score": 0.0, "evidence": "",
              "candidate_passages": ["four levels of achievement in the rubric"]}],
            {},
            "rubric",
        )
        self.assertIn("GROUP A", prompt)
        self.assertIn("GROUP B", prompt)
        self.assertIn("four levels of achievement in the rubric", prompt)

    def test_recheck_is_skipped_when_every_quote_is_verified(self):
        sections = [{"key": "results", "criteria": [
            {"id": "3.1", "heading": "Rubric Table", "score": 1.0, "evidence": "x",
             "note": "", "evidence_verified": True},
        ]}]
        self.assertEqual(watcher.recheck_criteria(sections, {}, "rubric", "model")["changed"], 0)

    def test_second_pass_runs_once_when_quotes_are_untraceable(self):
        make_pdf(self.pdf, [self.text])
        templates = watcher.load_scorecard_templates()
        payload = model_output_json(templates)

        first = iter([
            ChatResponse(message={'role': 'assistant', 'content': payload}, done=True),
        ])
        second_payload = json.dumps({"criteria": {
            criterion_id: {"evidence": "", "note": "not in the report", "score": 0.0}
            for section in templates.sections.values() for criterion_id in section
        }})
        calls = []

        def fake_chat(**kwargs):
            calls.append(kwargs)
            return first if len(calls) == 1 else iter(
                [ChatResponse(message={'role': 'assistant', 'content': second_payload}, done=True)]
            )

        with patch.object(watcher, 'OUTPUT_DIR', self.root), \
             patch.object(watcher, 'load_full_rubric', return_value='Rubric text'), \
             patch.object(watcher, 'ollama_is_running', return_value=True), \
             patch.object(watcher, 'model_is_available', return_value=True), \
             patch.object(watcher, 'chat', side_effect=fake_chat):
            watcher.grade_document(self.pdf)

        self.assertEqual(len(calls), 2)
        scorecard = json.loads((self.root / 'report_scorecard.json').read_text())
        self.assertEqual(scorecard['total_calculated_score'], 0.0)
        self.assertEqual(scorecard['verified_score'], 0.0)
        detail = json.loads((self.root / 'report_detail.json').read_text())
        self.assertTrue(detail['recheck']['attempted'])
        self.assertGreater(detail['recheck']['changed'], 0)

    def test_isolated_word_matches_are_not_offered_as_hints(self):
        # "Personally" appearing in an unrelated citation must not be served up
        # as a pointer for the PII-redaction criterion.
        document = (
            "The programme reviewed outcomes each term. "
            "Smith, J. (2019). Personally, the data looked reasonable. Journal of Nothing 3(1), 1-9. "
            "No student names or identifier numbers appear anywhere in this report."
        )
        hints = watcher.review_hints(
            document,
            {"4.5": "Personally Identifiable Information (PII) Redacted"},
            {"results": {"criteria": {"4.5": {"id": "4.5", "score": 1.0, "evidence_verified": False}}}},
        )
        self.assertIn("may not address this criterion", hints["4.5"])
        self.assertNotIn("Smith", hints["4.5"])

    def test_hints_point_at_windows_where_terms_co_occur(self):
        document = (
            "Intro paragraph about the review cycle. "
            "The report lists every learning outcome and the levels of achievement "
            "expected for each outcome on a four-level scale. "
            "Closing paragraph about budgeting."
        )
        hints = watcher.review_hints(
            document,
            {"3.3": "Levels of Achievement Included in the Rubric"},
            {"results": {"criteria": {"3.3": {"id": "3.3", "score": 1.0, "evidence_verified": False}}}},
        )
        self.assertIn("levels of achievement", hints["3.3"].lower())
        self.assertIn("four-level", hints["3.3"].lower())

    def test_zero_score_with_relevant_passage_is_flagged_for_review(self):
        # A 0 with no quote looks honest to quote-checking, but here the report
        # plainly discusses the criterion, so the zero needs a human eye.
        document = (
            "The assessment plan describes a rubric used for every artifact. "
            "The rubric used for the capstone has four levels of achievement: "
            "exceeds, meets, approaches, and does not meet expectations. "
            "Scores were reported for each outcome."
        )
        sections = [{
            "key": "results",
            "criteria": [{"id": "3.3", "score": 0.0, "evidence": "", "note": "none found",
                         "evidence_verified": True, "evidence_source": "none"}],
        }]
        flagged = watcher.flag_missed_points(
            document, {"3.3": "Levels of Achievement Included in the Rubric"}, sections, {}
        )
        self.assertEqual(len(flagged), 1)
        self.assertTrue(sections[0]["criteria"][0]["possible_missed_point"])
        self.assertIn("four levels of achievement", sections[0]["criteria"][0]["review_hint"])

    def test_deterministically_checked_criteria_are_not_flagged_as_missed(self):
        # The script already proved the fact, so a 0 here is not the model
        # missing something.
        document = "meeting minutes meeting date meeting minutes meeting date meeting minutes"
        sections = [{
            "key": "tracking",
            "criteria": [{"id": "2.8", "score": 0.0, "evidence": "", "note": "no minutes",
                         "evidence_verified": True, "evidence_source": "none"}],
        }]
        flagged = watcher.flag_missed_points(
            document, {"2.8": "Meeting minutes attached"}, sections,
            {"2.8": "Minutes referenced: none found"},
        )
        self.assertEqual(len(flagged), 0)

    def test_hints_skip_windows_that_are_only_the_rubric_heading(self):
        # Reports often paste the rubric into an appendix; the hint should point
        # at report prose, not at the restated criterion.
        document = (
            "Criterion 3.3: Levels of Achievement Included in the Rubric. "
            "Levels of achievement are included in the rubric as required by the criterion. "
            "The committee measured levels of achievement across four outcome levels "
            "and published the levels of achievement table."
        )
        hints = watcher.review_hints(
            document,
            {"3.3": "Levels of Achievement Included in the Rubric"},
            {"results": {"criteria": {"3.3": {"id": "3.3", "score": 1.0, "evidence_verified": False}}}},
        )
        self.assertIn("committee measured", hints["3.3"].lower())


class CompareRunsTests(unittest.TestCase):
    """Two models on the same report: agreement is a signal, disagreement is a
    reviewer's to-do list."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def _write(self, stem, scores, evidence):
        detail = {
            "model": stem,
            "sections": [{
                "key": "results",
                "criteria": [
                    {
                        "id": cid,
                        "heading": "Student Learning Outcomes",
                        "score": scores[cid],
                        "note": "",
                        "evidence": evidence.get(cid, ""),
                        "evidence_verified": bool(evidence.get(cid)),
                    }
                    for cid in ("2.1", "2.2")
                ],
            }],
        }
        (self.root / f"{stem}_detail.json").write_text(json.dumps(detail), encoding="utf-8")

    def test_disagreements_are_listed_with_both_quotes(self):
        with patch.object(watcher, 'OUTPUT_DIR', self.root):
            self._write("run_llama", {"2.1": 1.0, "2.2": 0.0},
                        {"2.1": "The program publishes its learning outcomes online."})
            self._write("run_qwen", {"2.1": 0.0, "2.2": 1.0},
                        {"2.2": "Student work samples appear in the appendix."})

            comparison = watcher.compare_runs("run_llama", "run_qwen")

        self.assertEqual(comparison["criteria_compared"], 2)
        self.assertEqual(comparison["agreements"], 0)
        self.assertEqual(len(comparison["disagreements"]), 2)
        # The headline totals are identical (1.0 vs 1.0) yet the two runs award
        # the points to different criteria. A total alone would hide that, which
        # is exactly why the comparison is per-criterion.
        self.assertEqual(comparison["total_difference"], 0.0)
        # Each disagreement is decided by which side actually quoted the report:
        # run_llama has a traceable quote for 2.1, run_qwen for 2.2.
        by_id = {entry["id"]: entry for entry in comparison["disagreements"]}
        self.assertEqual(by_id["2.1"]["supported_by"], "run_llama")
        self.assertEqual(by_id["2.2"]["supported_by"], "run_qwen")

    def test_agreement_is_reported_when_scores_match(self):
        with patch.object(watcher, 'OUTPUT_DIR', self.root):
            self._write("run_llama", {"2.1": 1.0, "2.2": 1.0}, {})
            self._write("run_qwen", {"2.1": 1.0, "2.2": 1.0}, {})
            comparison = watcher.compare_runs("run_llama", "run_qwen")

        self.assertEqual(comparison["agreements"], 2)
        self.assertEqual(comparison["disagreements"], [])
        self.assertEqual(comparison["agreement_rate"], 100.0)

    def test_the_run_with_traceable_evidence_is_named(self):
        with patch.object(watcher, 'OUTPUT_DIR', self.root):
            # run_llama scores 2.1 high but quotes nothing; run_qwen quotes real text.
            self._write("run_llama", {"2.1": 1.0, "2.2": 0.0}, {})
            self._write("run_qwen", {"2.1": 0.0, "2.2": 1.0},
                        {"2.1": "Learning outcomes are posted on the program page."})
            comparison = watcher.compare_runs("run_llama", "run_qwen")

        entry = next(item for item in comparison["disagreements"] if item["id"] == "2.1")
        self.assertEqual(entry["supported_by"], "run_qwen")

    def test_consensus_prefers_the_run_with_a_traceable_quote(self):
        with patch.object(watcher, 'OUTPUT_DIR', self.root):
            # run_llama claims 1.0 but quotes nothing findable; run_qwen finds
            # real text. Evidence, not confidence, decides.
            # run_llama claims 2.1 and 2.2 but quotes nothing that the script can
            # find; run_qwen scores 2.2 lower but with real, traceable text.
            self._write("run_llama", {"2.1": 1.0, "2.2": 1.0},
                        {"2.1": "a quote that is not really in the report"})
            detail = json.loads((self.root / "run_llama_detail.json").read_text())
            for criterion in detail["sections"][0]["criteria"]:
                criterion["evidence_verified"] = False   # the script could not trace it
            (self.root / "run_llama_detail.json").write_text(json.dumps(detail))

            self._write("run_qwen", {"2.1": 0.0, "2.2": 0.5},
                        {"2.2": "Student work samples appear in the appendix."})

            comparison = watcher.compare_runs("run_llama", "run_qwen")

        consensus = comparison["consensus"]
        by_id = {c["id"]: c for c in consensus["criteria"]}
        # run_llama's 1.0 is discarded because its quote cannot be traced; the
        # 0.5 with a real quote survives.
        self.assertEqual(by_id["2.2"]["score"], 0.5)
        self.assertIn("run_qwen quoted report text", by_id["2.2"]["basis"])
        # 2.1: neither side could cite anything, so nothing is credited.
        self.assertEqual(by_id["2.1"]["score"], 0.0)
        self.assertIn("needs a human", by_id["2.1"]["basis"])
        # 2.2 was settled by evidence, so only 2.1 is escalated.
        self.assertEqual(consensus["needs_human_review"], 1)
        self.assertEqual(consensus["score"], 0.5)

    def test_consensus_hedges_when_both_quotes_are_real(self):
        # Two real quotes, different readings: the lower score is taken as the
        # conservative default, and the criterion is flagged for the committee.
        result = watcher.arbitrate(
            agreements=[],
            disagreements=[{"id": "3.3", "heading": "x", "score_a": 1.0, "score_b": 0.5,
                            "evidence_a": "a", "evidence_b": "b",
                            "verified_a": True, "verified_b": True}],
            run_a="A", run_b="B",
        )
        self.assertEqual(result["score"], 0.5)
        self.assertEqual(result["needs_human_review"], 1)

    def test_consensus_keeps_agreements_unflagged(self):
        result = watcher.arbitrate(
            agreements=[{"id": "2.1", "heading": "x", "score_a": 1.0, "score_b": 1.0,
                         "evidence_a": "a", "evidence_b": "a",
                         "verified_a": True, "verified_b": True}],
            disagreements=[],
        )
        self.assertEqual(result["score"], 1.0)
        self.assertEqual(result["needs_human_review"], 0)

    def test_missing_run_raises_a_clear_error(self):
        with patch.object(watcher, 'OUTPUT_DIR', self.root):
            with self.assertRaises(watcher.EvaluationError):
                watcher.compare_runs("never-graded", "also-never-graded")


if __name__ == '__main__':
    unittest.main()
