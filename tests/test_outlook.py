import base64
from email import policy
from email.parser import BytesParser
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import urllib.error

import connect_outlook
import notifications
import outlook_auth
from test_notifications import result


CONFIG = {'provider': 'microsoft_graph', 'sender': 'prof@university.edu',
          'tenant_id': '11111111-1111-1111-1111-111111111111',
          'client_id': '22222222-2222-2222-2222-222222222222'}


class OutlookTests(unittest.TestCase):
    def test_graph_sends_same_mime_feedback_and_recipient(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'config.json'
            config.write_text(json.dumps(CONFIG))
            with patch.object(notifications, 'EMAIL_CONFIG_PATH', config), \
                 patch.object(notifications, 'sender_access_token', return_value='token'), \
                 patch.object(notifications.urllib.request, 'urlopen') as send, \
                 patch.object(notifications.smtplib, 'SMTP') as smtp:
                send.return_value.__enter__.return_value.status = 202
                outcome = notifications.send_completion_email(result(.5), 'report.pdf', 'recipient@example.org')
                self.assertEqual(outcome['status'], 'sent')
                request = send.call_args.args[0]
                self.assertEqual(request.full_url, 'https://graph.microsoft.com/v1.0/me/sendMail')
                self.assertEqual(request.get_header('Authorization'), 'Bearer token')
                message = BytesParser(policy=policy.default).parsebytes(base64.b64decode(request.data))
                self.assertEqual(message['From'], CONFIG['sender'])
                self.assertEqual(message['To'], 'recipient@example.org')
                self.assertIn('Revisions recommended', message.get_body().get_content())
                attachments = list(message.iter_attachments())
                self.assertEqual(len(attachments), 2)
                self.assertEqual(attachments[0].get_payload(decode=True).decode(), result()['feedback'])
                smtp.assert_not_called()

    def test_signin_and_access_failures_do_not_send_via_smtp(self):
        errors = [outlook_auth.OutlookSignInRequired('Sign in again'),
                  urllib.error.HTTPError('https://graph.microsoft.com', 403, 'Denied', {}, None),
                  urllib.error.HTTPError('https://graph.microsoft.com', 429, 'Throttled', {}, None)]
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'config.json'
            config.write_text(json.dumps(CONFIG))
            for error in errors:
                with patch.object(notifications, 'EMAIL_CONFIG_PATH', config), \
                     patch.object(notifications, 'sender_access_token', side_effect=error), \
                     patch.object(notifications.smtplib, 'SMTP') as smtp:
                    outcome = notifications.send_completion_email(result(), 'report.pdf', 'recipient@example.org')
                    self.assertIn(outcome['status'], ['failed', 'sign_in_required'])
                    smtp.assert_not_called()

    def test_refresh_uses_configured_sender_without_interactive_signin(self):
        app, cache = MagicMock(), MagicMock()
        account = {'username': CONFIG['sender']}
        app.get_accounts.return_value = [account]
        app.acquire_token_silent.return_value = {'access_token': 'refreshed-token'}
        with patch.object(outlook_auth, '_application', return_value=(app, cache)), \
             patch.object(outlook_auth, '_save_cache') as save:
            self.assertEqual(outlook_auth.sender_access_token(CONFIG), 'refreshed-token')
            app.get_accounts.assert_called_once_with(username=CONFIG['sender'])
            app.acquire_token_silent.assert_called_once_with(outlook_auth.SCOPES, account=account)
            app.acquire_token_interactive.assert_not_called()
            save.assert_called_once_with(cache)

    def test_expired_or_missing_account_requires_explicit_signin(self):
        for accounts in ([], [{'username': CONFIG['sender']}]):
            app, cache = MagicMock(), MagicMock()
            app.get_accounts.return_value = accounts
            app.acquire_token_silent.return_value = None
            with patch.object(outlook_auth, '_application', return_value=(app, cache)), \
                 patch.object(outlook_auth, '_save_cache'):
                with self.assertRaises(outlook_auth.OutlookSignInRequired):
                    outlook_auth.sender_access_token(CONFIG)
                app.acquire_token_interactive.assert_not_called()

    def test_wrong_account_does_not_replace_cache(self):
        app, cache = MagicMock(), MagicMock()
        app.acquire_token_interactive.return_value = {'access_token': 'token',
            'id_token_claims': {'preferred_username': 'other@university.edu'}}
        with patch.object(outlook_auth, '_application', return_value=(app, cache)), \
             patch.object(outlook_auth, '_save_cache') as save:
            with self.assertRaises(outlook_auth.OutlookSignInRequired):
                outlook_auth.connect_sender(CONFIG)
            save.assert_not_called()

    def test_cache_is_atomically_saved_with_private_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'cache.json'
            cache = MagicMock()
            cache.serialize.return_value = '{"private":"token"}'
            with patch.object(outlook_auth, 'CACHE_PATH', path):
                outlook_auth._save_cache(cache)
            self.assertEqual(path.read_text(), '{"private":"token"}')
            if os.name != 'nt':
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(len(list(Path(directory).iterdir())), 1)

    def test_setup_preserves_existing_config_on_failed_signin(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.json'
            path.write_text('{"provider":"smtp"}')
            with patch.object(connect_outlook, 'EMAIL_CONFIG_PATH', path), \
                 patch('builtins.input', side_effect=[CONFIG['sender'], CONFIG['tenant_id'], CONFIG['client_id']]), \
                 patch('builtins.print'), \
                 patch.object(connect_outlook, 'connect_sender', side_effect=outlook_auth.OutlookSignInRequired('Consent required')):
                with self.assertRaises(SystemExit):
                    connect_outlook.main()
            self.assertEqual(path.read_text(), '{"provider":"smtp"}')

    def test_setup_switches_provider_only_after_signin(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.json'
            path.write_text('{"smtp_password":"old-secret"}')
            with patch.object(connect_outlook, 'EMAIL_CONFIG_PATH', path), \
                 patch('builtins.input', side_effect=[CONFIG['sender'], CONFIG['tenant_id'], CONFIG['client_id']]), \
                 patch('builtins.print'), patch.object(connect_outlook, 'connect_sender') as connect:
                connect_outlook.main()
            connect.assert_called_once_with(CONFIG)
            self.assertEqual(json.loads(path.read_text()), CONFIG)
