"""Run from the project root: .venv/bin/python backend/connect_outlook.py

Connects a sender through Microsoft sign-in; does not send any email.
"""
import json
import os
from pathlib import Path
import tempfile

from config import EMAIL_CONFIG_PATH
from outlook_auth import connect_sender, OutlookSignInRequired
from notifications import valid_recipient


def main():
    print('Connect the university Microsoft 365 sender. No email will be sent during setup.')
    sender = input('University sending email (use your Microsoft sign-in address): ').strip()
    tenant = input('Directory (tenant) ID from the university app registration: ').strip()
    client = input('Application (client) ID from the app registration: ').strip()
    if not valid_recipient(sender):
        raise SystemExit('Enter a valid university email address.')
    config = {'provider': 'microsoft_graph', 'sender': sender, 'tenant_id': tenant, 'client_id': client}
    print('Complete Microsoft sign-in in the browser window that opens.')
    try:
        connect_sender(config)
    except OutlookSignInRequired as exc:
        raise SystemExit(str(exc)) from None
    # Replace SMTP credentials only after sign-in succeeds.
    fd, filename = tempfile.mkstemp(dir=EMAIL_CONFIG_PATH.parent, prefix='.email-config-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as output:
            json.dump(config, output, indent=2)
            output.write('\n')
        os.replace(filename, EMAIL_CONFIG_PATH)
    finally:
        if Path(filename).exists():
            Path(filename).unlink()
    print('University sender connected. Restart the backend once to load the updated code.')
    print('Users can save any receiving email before uploading. Use an existing report to test delivery.')


if __name__ == '__main__':
    main()
