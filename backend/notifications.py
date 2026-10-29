"""Optional completion email. Never changes evaluation output or scoring."""
import base64
import json
import re
import smtplib
import ssl
import urllib.error
import urllib.request
from email.message import EmailMessage

from config import EMAIL_CONFIG_PATH
from outlook_auth import OutlookSignInRequired, sender_access_token


def valid_recipient(value):
    return bool(re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", value))


def completion_message(result):
    criteria = [c for s in (result.get('sections') or result.get('scorecard', {}).get('sections_review', []))
                for c in s['criteria']]
    flagged = [c for c in criteria if c['score'] < 1 or not c.get('evidence_verified')]
    acceptable = bool(criteria) and not flagged
    status = 'Acceptable to proceed' if acceptable else 'Revisions recommended'
    lines = ['Dear Professor,', '',
             'Your submitted program assessment report has completed its preliminary AI review.',
             '', f'Assessment status: {status}', '']
    if flagged:
        lines += ['The system identified the following areas for improvement:', '']
        for c in flagged[:5]:
            note = c.get('note') or 'Review this criterion in the attached feedback.'
            if not c.get('evidence_verified'):
                note += ' Supporting evidence requires human verification.'
            lines.append(f"- Criterion {c['id']} ({c.get('heading') or c['id']}): {note}")
        if len(flagged) > 5:
            lines.append('- See the attached feedback for the remaining areas for improvement.')
        lines.append('')
    elif not acceptable:
        lines += ['Please review the attached feedback with a human reviewer to confirm readiness.', '']
    lines += [('Please review the attached feedback document and proceed to human review.' if acceptable else
               'Please review the attached feedback document, make any necessary revisions, and resubmit your report.'),
              '', 'These findings are AI-generated and are subject to human review.', '',
              'Thank you,', '', 'University Program Assessment System']
    return status, '\n'.join(lines)


def send_completion_email(result, filename, recipient):
    """Return delivery status, including for missing config or SMTP failure."""
    try:
        if not valid_recipient(recipient):
            return {'status': 'failed', 'message': 'Enter a valid delivery email address.'}
        if not EMAIL_CONFIG_PATH.exists():
            return {'status': 'not_configured', 'message':
                    'Email is not configured. Create backend/email_config.json using email_config.example.json.'}
        config = json.loads(EMAIL_CONFIG_PATH.read_text(encoding='utf-8'))
        status, body = completion_message(result)
        message = EmailMessage()
        message['Subject'] = f'Assessment completed: {status} — {filename}'
        message['From'] = config['sender']
        message['To'] = recipient
        message.set_content(body)
        message.add_attachment(result['feedback'].encode('utf-8'), maintype='text', subtype='markdown',
                               filename='assessment_feedback.md')
        message.add_attachment(json.dumps(result['scorecard'], indent=2).encode('utf-8'),
                               maintype='application', subtype='json', filename='assessment_scorecard.json')
        provider = config.get('provider', 'smtp')
        if provider == 'microsoft_graph':
            token = sender_access_token(config)
            # Graph accepts the same MIME message and attachments as SMTP.
            request = urllib.request.Request(
                'https://graph.microsoft.com/v1.0/me/sendMail',
                data=base64.b64encode(message.as_bytes()),
                headers={'Authorization': f'Bearer {token}', 'Content-Type': 'text/plain'},
                method='POST',
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                if response.status != 202:
                    return {'status': 'failed', 'message': 'Microsoft did not accept the email for sending.'}
            return {'status': 'sent', 'message': f'Microsoft accepted the completion email for {recipient}. Check Sent Items for delivery details.'}
        if provider != 'smtp':
            return {'status': 'failed', 'message': 'Unknown email provider. Use smtp or microsoft_graph.'}
        context = ssl.create_default_context()
        if config.get('use_ssl', False):
            server = smtplib.SMTP_SSL(config['smtp_host'], config.get('smtp_port', 465), timeout=15, context=context)
        else:
            server = smtplib.SMTP(config['smtp_host'], config.get('smtp_port', 587), timeout=15)
        with server:
            if config.get('use_tls', True) and not config.get('use_ssl', False):
                server.starttls(context=context)
            if config.get('smtp_user'):
                server.login(config['smtp_user'], config.get('smtp_password', ''))
            refused = server.send_message(message)
            if refused:
                return {'status': 'failed', 'message': 'The mail server refused the recipient.'}
        return {'status': 'sent', 'message': f'Completion email sent to {recipient}.'}
    except OutlookSignInRequired as exc:
        return {'status': 'sign_in_required', 'message': str(exc)}
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return {'status': 'failed', 'message': 'Microsoft denied email access. Reconnect the sender and ask university IT to verify delegated Mail.Send permission and account policy.'}
        return {'status': 'failed', 'message': f'Microsoft email request failed (HTTP {exc.code}). Retry manually later.'}
    except Exception:
        return {'status': 'failed', 'message': 'Email delivery failed. Check the email configuration and connection, then retry.'}
