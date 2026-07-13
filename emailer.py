"""
emailer.py — sends email via plain SMTP.

Configure via a `.env` file (see .env.example) with your mail provider's
SMTP details (Gmail, Outlook/Office 365, or any transactional email service
like SendGrid/Resend/Postmark all work — they all speak SMTP).

If SMTP isn't configured yet, send_email() doesn't fail silently: it returns
sent=False and the fully composed message so the app can show you a preview
instead. That way the rest of the app is testable before you wire up real
email.
"""
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from dotenv import load_dotenv

load_dotenv()

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
FROM_EMAIL = os.getenv("FROM_EMAIL", SMTP_USER or "")
FROM_NAME = os.getenv("FROM_NAME", "Klareco Team Building")


def is_configured():
    return bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD)


def send_email(to_emails, subject, body_html, body_text=None):
    """
    to_emails: list of recipient email addresses.
    Returns (sent: bool, detail: str). If not configured, sent=False and
    detail contains the composed message for on-screen preview.
    """
    to_emails = [e for e in (to_emails or []) if e]
    preview = f"To: {', '.join(to_emails)}\nSubject: {subject}\n\n{body_text or body_html}"

    if not to_emails:
        return False, "No recipient email addresses — add emails on the Team Settings page."

    if not is_configured():
        return False, preview

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{FROM_NAME} <{FROM_EMAIL}>"
    msg["To"] = ", ".join(to_emails)
    if body_text:
        msg.attach(MIMEText(body_text, "plain"))
    msg.attach(MIMEText(body_html, "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(FROM_EMAIL, to_emails, msg.as_string())
        return True, f"Sent to {len(to_emails)} recipient(s)."
    except Exception as exc:
        return False, f"Send failed: {exc}\n\n--- message that would have been sent ---\n{preview}"
