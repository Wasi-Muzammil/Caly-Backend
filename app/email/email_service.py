"""
Email Service
=============
Sends meeting confirmation emails to all participants using SMTP.
Configure via environment variables:
    EMAIL_HOST         — e.g. smtp.gmail.com
    EMAIL_PORT         — e.g. 587
    EMAIL_USERNAME     — sender email address
    EMAIL_PASSWORD     — sender email password / app password
    EMAIL_FROM_NAME    — display name (default: "Caly Scheduler")
"""

import os
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from typing import List

logger = logging.getLogger(__name__)


def _build_html(
    title:       str,
    start:       datetime,
    end:         datetime,
    organizer:   str,
    participants: List[str],
    location:    str = "",
    description: str = "",
    is_priority: bool = False,
) -> str:
    priority_badge = (
        '<span style="background:#e53e3e;color:white;padding:2px 8px;'
        'border-radius:4px;font-size:12px;margin-left:8px;">URGENT</span>'
        if is_priority else ""
    )
    participants_html = "".join(f"<li>{p}</li>" for p in participants)
    location_row  = f"<tr><td><b>Location</b></td><td>{location}</td></tr>"  if location    else ""
    desc_row      = f"<tr><td><b>Description</b></td><td>{description}</td></tr>" if description else ""

    return f"""
    <html><body style="font-family:Arial,sans-serif;color:#333;max-width:600px;margin:auto">
      <div style="background:#4A90E2;padding:20px;border-radius:8px 8px 0 0">
        <h2 style="color:white;margin:0">📅 Meeting Confirmed {priority_badge}</h2>
      </div>
      <div style="border:1px solid #ddd;border-top:none;padding:24px;border-radius:0 0 8px 8px">
        <h3 style="margin-top:0">{title}</h3>
        <table style="width:100%;border-collapse:collapse">
          <tr><td style="padding:6px 0;width:120px"><b>Start</b></td>
              <td>{start.strftime("%A, %d %B %Y at %H:%M")} UTC</td></tr>
          <tr><td style="padding:6px 0"><b>End</b></td>
              <td>{end.strftime("%A, %d %B %Y at %H:%M")} UTC</td></tr>
          <tr><td style="padding:6px 0"><b>Duration</b></td>
              <td>{int((end - start).total_seconds() // 60)} minutes</td></tr>
          <tr><td style="padding:6px 0"><b>Organizer</b></td>
              <td>{organizer}</td></tr>
          {location_row}
          {desc_row}
        </table>
        <hr style="margin:16px 0;border:none;border-top:1px solid #eee">
        <b>Participants:</b>
        <ul style="margin:8px 0">{participants_html}</ul>
        <p style="color:#888;font-size:12px;margin-top:24px">
          Sent by <b>Caly</b> — AI-Assisted Smart Meeting Scheduler
        </p>
      </div>
    </body></html>
    """


def send_confirmation_emails(
    participants: List[str],
    title:        str,
    start:        datetime,
    end:          datetime,
    organizer:    str,
    location:     str = "",
    description:  str = "",
    is_priority:  bool = False,
) -> dict:
    """
    Send a meeting confirmation email to every participant.

    Returns {"sent": [...], "failed": [...]} so the caller can surface warnings.
    Does NOT raise — email failure should never abort a meeting creation.
    """
    host      = os.getenv("EMAIL_HOST",      "smtp.gmail.com")
    port      = int(os.getenv("EMAIL_PORT",  "587"))
    username  = os.getenv("EMAIL_USERNAME",  "")
    password  = os.getenv("EMAIL_PASSWORD",  "")
    from_name = os.getenv("EMAIL_FROM_NAME", "Caly Scheduler")

    if not username or not password:
        logger.warning("Email credentials not configured — skipping confirmation emails.")
        return {"sent": [], "failed": participants, "reason": "Email not configured"}

    html_body = _build_html(title, start, end, organizer, participants, location, description, is_priority)
    subject   = f"{'[URGENT] ' if is_priority else ''}Meeting Confirmed: {title}"

    sent, failed = [], []

    try:
        with smtplib.SMTP(host, port, timeout=10) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(username, password)

            for recipient in participants:
                try:
                    msg = MIMEMultipart("alternative")
                    msg["Subject"] = subject
                    msg["From"]    = f"{from_name} <{username}>"
                    msg["To"]      = recipient
                    msg.attach(MIMEText(html_body, "html"))
                    smtp.sendmail(username, recipient, msg.as_string())
                    sent.append(recipient)
                    logger.info(f"Confirmation email sent to {recipient}")
                except Exception as e:
                    failed.append(recipient)
                    logger.error(f"Failed to send to {recipient}: {e}")

    except Exception as e:
        logger.error(f"SMTP connection failed: {e}")
        return {"sent": [], "failed": participants, "reason": str(e)}

    return {"sent": sent, "failed": failed}