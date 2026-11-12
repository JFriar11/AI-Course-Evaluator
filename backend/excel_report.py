"""Excel copy of the result panel, using the same sections and criteria."""
from io import BytesIO

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

EXCEL_MEDIA_TYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


def build_excel_report(result, filename=None):
    """Return an XLSX with readable, collapsible sections and literal text cells."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Evaluation'
    sheet.sheet_properties.outlinePr.summaryBelow = False

    def row(values, heading=False):
        sheet.append(values)
        for cell in sheet[sheet.max_row]:
            if isinstance(cell.value, str):
                cell.value = ILLEGAL_CHARACTERS_RE.sub('', cell.value)
                # Report/model text must never become an Excel formula.
                cell.data_type = 's'
            cell.alignment = Alignment(vertical='top', wrap_text=True)
            if heading:
                cell.font = Font(bold=True, color='FFFFFF')
                cell.fill = PatternFill('solid', fgColor='24546A')

    scorecard = result.get('scorecard', {})
    row(['Report', filename or result.get('filename') or result.get('stem', '')], True)
    row(['Total score', scorecard.get('total_calculated_score', 0), 'Maximum', result.get('max_points', 25)])
    row(['Evidenced score', scorecard.get('verified_score', scorecard.get('total_calculated_score', 0))])
    extraction = result.get('extraction', {})
    row(['Pages', extraction.get('pages', 0), 'OCR pages', extraction.get('ocr_pages', 0),
         'Characters', extraction.get('characters', 0)])
    row(['Extraction', '; '.join(filter(None, [
        f"{extraction.get('figure_captions', 0)} figure caption(s)",
        'Read in overlapping parts' if extraction.get('chunked') else '',
        'Some pages left out of the prompt' if extraction.get('truncated') else '',
    ]))])
    if result.get('stopped'):
        row(['Evaluation stopped before grading', result.get('stopped_reason', ''),
             'A human must review this report; 0 is a placeholder.'])
    if result.get('unverified_evidence'):
        row(['Evidence warning', f"{result['unverified_evidence']} quote(s) could not be matched to the document text; check before submitting."])
    if result.get('missed_point_review'):
        row(['Review needed', f"{result['missed_point_review']} criterion(s) scored 0 but may be addressed in the report."])
    recheck = result.get('recheck') or {}
    if recheck.get('attempted'):
        row(['Second pass', f"Re-asked about {recheck.get('flagged', 0)} unsupported criteria; revised {recheck.get('changed', 0)}."])
    row([])
    row(['Criterion', 'Score', 'Comments / heading', 'Evidence quote', 'Evidence status', 'Review flag', 'Search the report for'], True)
    sheet.freeze_panes = f'C{sheet.max_row + 1}'
    for section in result.get('sections') or scorecard.get('sections_review', []):
        criteria = section.get('criteria', [])
        row([section.get('label', section.get('key', 'Section')), section.get('score', 0),
             f"Out of {section.get('max', len(criteria))}"], True)
        start = sheet.max_row + 1
        for criterion in criteria:
            verified = criterion.get('evidence_verified')
            status = 'Verified' if verified is True else 'Not checked'
            if verified is False:
                status = {'rubric': 'The rubric wording, not the report',
                          'script_fact': 'The automated pre-check, not the report'}.get(
                              criterion.get('evidence_source'), 'Not found in the report')
            row([criterion.get('id', ''), criterion.get('score', 0),
                 criterion.get('note') or criterion.get('heading', ''),
                 criterion.get('evidence', ''), status,
                 'Scored 0, but the report appears to address this; check for a missed point.'
                 if criterion.get('possible_missed_point') else '', criterion.get('review_hint', '')])
            sheet.row_dimensions[sheet.max_row].height = 90
        if criteria:
            sheet.row_dimensions.group(start, sheet.max_row, outline_level=1, hidden=False)
    row([])
    row(['Summary'], True)
    row([(result.get('detail') or {}).get('summary', '')])
    sheet.merge_cells(start_row=sheet.max_row, start_column=1, end_row=sheet.max_row, end_column=7)
    sheet.row_dimensions[sheet.max_row].height = 100
    for index, width in enumerate([28, 14, 65, 75, 32, 45, 65], 1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_setup.orientation = 'landscape'
    sheet.page_setup.paperSize = sheet.PAPERSIZE_A3
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()
