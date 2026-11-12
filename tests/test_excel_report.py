import unittest
from io import BytesIO
from unittest.mock import patch

from openpyxl import load_workbook
import server
from excel_report import build_excel_report, EXCEL_MEDIA_TYPE


class ExcelReportTests(unittest.TestCase):
    def setUp(self):
        self.result = {
            'filename': 'report.pdf', 'scorecard': {'total_calculated_score': .5, 'verified_score': 0},
            'max_points': 1, 'detail': {'summary': '=Literal summary'},
            'unverified_evidence': 1,
            'sections': [{'label': 'Findings', 'score': .5, 'max': 1, 'criteria': [
                {'id': '1.1', 'score': .5, 'note': '=Literal note', 'evidence': 'Quoted text',
                 'evidence_verified': False, 'evidence_source': 'rubric',
                 'possible_missed_point': True, 'review_hint': 'Find this passage'}]}]}

    def test_workbook_preserves_panel_and_groups_without_formulas(self):
        sheet = load_workbook(BytesIO(build_excel_report(self.result))).active
        cells = {cell.value: cell for row in sheet for cell in row if cell.value is not None}
        for value in ['Findings', '1.1', '=Literal note', 'Quoted text',
                      'The rubric wording, not the report', 'Find this passage', '=Literal summary']:
            self.assertIn(value, cells)
        self.assertEqual(cells['=Literal note'].data_type, 's')
        self.assertEqual(cells['=Literal summary'].data_type, 's')
        self.assertEqual(sheet.row_dimensions[cells['1.1'].row].outlineLevel, 1)
        self.assertFalse(sheet.sheet_properties.outlinePr.summaryBelow)
        self.assertTrue(sheet.freeze_panes)

    def test_live_and_saved_downloads(self):
        with patch.dict(server.JOBS, {'excel-test': {'filename': 'report.pdf', 'result': self.result}}):
            response = server.download('excel-test', 'excel')
        self.assertEqual(response.media_type, EXCEL_MEDIA_TYPE)
        self.assertIn('report_evaluation.xlsx', response.headers['content-disposition'])
        load_workbook(BytesIO(response.body))
        with patch.object(server, '_saved_result', return_value=self.result):
            saved = server.download_saved('previous-report', 'excel')
        load_workbook(BytesIO(saved.body))
        with self.assertRaises(server.HTTPException):
            server.download_saved('../unsafe', 'excel')
