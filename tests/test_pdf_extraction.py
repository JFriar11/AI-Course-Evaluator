import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from pdf_extraction import Extraction, PageText, extract_pdf, save_extraction
import watcher


def make_pdf(path, contents):
    writer = PdfWriter()
    for text in contents:
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
                                 NameObject('/Subtype'): NameObject('/Type1'),
                                 NameObject('/BaseFont'): NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({
            NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
        stream = DecodedStreamObject()
        stream.set_data(f'BT /F1 12 Tf 50 700 Td ({text}) Tj ET'.encode())
        page[NameObject('/Contents')] = writer._add_object(stream)
    writer.write(path)


class ExtractionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pdf = self.root / 'report.pdf'
        self.text = 'Students demonstrated the required learning outcomes in the final assessment.'

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

    def test_mixed_pdf_uses_ocr_for_scanned_page(self):
        make_pdf(self.pdf, [self.text, ''])
        with patch('pdf_extraction.ocr_page', return_value=self.text) as ocr:
            result = extract_pdf(self.pdf)
        ocr.assert_called_once_with(self.pdf, 1)
        self.assertTrue(result.ready)
        self.assertEqual([p.method for p in result.pages], ['embedded', 'ocr'])

    def test_failed_page_blocks_evaluation_and_is_saved(self):
        make_pdf(self.pdf, [self.text, ''])
        with patch('pdf_extraction.ocr_page', side_effect=RuntimeError('OCR missing')), \
             patch.object(watcher, 'OUTPUT_DIR', self.root), \
             patch.object(watcher, 'load_rubric', return_value='Rubric'), \
             patch.object(watcher, 'chat') as chat:
            watcher.grade_document(self.pdf)
        chat.assert_not_called()
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
        with patch.object(watcher, 'OUTPUT_DIR', self.root), \
             patch.object(watcher, 'load_rubric', return_value='Rubric'), \
             patch.object(watcher, 'chat') as chat:
            chat.return_value.message.content = '{}'
            chat.return_value.message.thinking = ''
            watcher.grade_document(self.pdf)
        chat.assert_called_once()
        saved = (self.root / 'report_extracted.txt').read_text()
        self.assertIn(saved, chat.call_args.kwargs['messages'][0]['content'])

    def test_long_document_is_not_silently_truncated(self):
        result = Extraction('report.pdf', [PageText(1, 'x' * 25001, 'embedded')])
        with patch.object(watcher, 'extract_pdf', return_value=result), \
             patch.object(watcher, 'OUTPUT_DIR', self.root), \
             patch.object(watcher, 'load_rubric', return_value='Rubric'), \
             patch.object(watcher, 'chat') as chat:
            watcher.grade_document(self.pdf)
        chat.assert_not_called()
        self.assertIn('x' * 25001, (self.root / 'report_extracted.txt').read_text())


if __name__ == '__main__':
    unittest.main()
