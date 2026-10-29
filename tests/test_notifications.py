import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

import notifications
import server


def result(score=1, verified=True):
    return {'sections': [{'criteria': [{'id': '2.1', 'heading': 'Learning outcome evidence',
            'score': score, 'evidence_verified': verified, 'note': 'Additional evidence needed.'}]}],
            'scorecard': {}, 'feedback': '# Feedback\nDetailed findings.'}


class NotificationTests(unittest.TestCase):
    def test_status_and_actual_findings(self):
        self.assertEqual(notifications.completion_message(result())[0], 'Acceptable to proceed')
        status, body = notifications.completion_message(result(.5))
        self.assertEqual(status, 'Revisions recommended')
        self.assertIn('Additional evidence needed.', body)
        self.assertIn('subject to human review', body)
        self.assertEqual(notifications.completion_message(result(1, False))[0], 'Revisions recommended')

    def test_smtp_and_attachments(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'email.json'
            config.write_text('{"smtp_host":"smtp.example.com","sender":"sender@example.com"}')
            with patch.object(notifications, 'EMAIL_CONFIG_PATH', config), patch.object(notifications.smtplib, 'SMTP') as smtp:
                smtp.return_value.send_message.return_value = {}
                outcome = notifications.send_completion_email(result(), 'report.pdf', 'prof@example.com')
                self.assertEqual(outcome['status'], 'sent')
                client = smtp.return_value
                client.starttls.assert_called_once()
                message = client.send_message.call_args.args[0]
                self.assertEqual(message['To'], 'prof@example.com')
                self.assertEqual(len(list(message.iter_attachments())), 2)
                self.assertIn('Acceptable to proceed', message.get_body().get_content())
            with patch.object(notifications, 'EMAIL_CONFIG_PATH', config), patch.object(notifications.smtplib, 'SMTP', side_effect=OSError('offline')):
                self.assertEqual(notifications.send_completion_email(result(), 'report.pdf', 'prof@example.com')['status'], 'failed')

    def test_missing_config_and_invalid_address(self):
        with patch.object(notifications, 'EMAIL_CONFIG_PATH', Path('/nonexistent/email.json')):
            self.assertEqual(notifications.send_completion_email(result(), 'r.pdf', 'prof@example.com')['status'], 'not_configured')
            self.assertEqual(notifications.send_completion_email(result(), 'r.pdf', 'bad\naddress')['status'], 'failed')

    def test_delivery_after_completion_and_failure_isolated(self):
        with tempfile.TemporaryDirectory() as directory:
            pdf = Path(directory) / 'report.pdf'
            pdf.touch()
            server.JOBS['email-test'] = {'delivery_email': 'prof@example.com', 'filename': 'report.pdf'}
            def send(*args):
                self.assertEqual(server.JOBS['email-test']['status'], 'done')
                self.assertFalse(pdf.exists())
                return {'status': 'failed', 'message': 'Offline'}
            with patch.object(server, 'grade_pdf', return_value=result()), patch.object(server, 'send_completion_email', side_effect=send) as delivery:
                server._run_grading('email-test', pdf, 'report')
                delivery.assert_called_once()
                self.assertEqual(server.JOBS['email-test']['status'], 'done')
                self.assertEqual(server.JOBS['email-test']['notification']['status'], 'failed')
            del server.JOBS['email-test']

    def test_no_delivery_for_failed_grading_or_missing_email(self):
        for recipient, failure in [('prof@example.com', True), (None, False)]:
            with tempfile.TemporaryDirectory() as directory:
                pdf = Path(directory) / 'report.pdf'
                pdf.touch()
                server.JOBS['email-test'] = {'delivery_email': recipient, 'filename': 'report.pdf'}
                with patch.object(server, 'grade_pdf', side_effect=server.EvaluationError('Failed') if failure else None, return_value=result()), patch.object(server, 'send_completion_email') as send:
                    server._run_grading('email-test', pdf, 'report')
                    send.assert_not_called()
                del server.JOBS['email-test']
