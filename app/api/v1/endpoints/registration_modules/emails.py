import asyncio
import html
import json as _json
import logging as _logging
from typing import Any

from app.core.config import settings as _settings
from app.core.document_generators import (
    generate_invoice_pdf,
    generate_invitation_letter_pdf,
    generate_pre_training_form_docx,
)
from app.core.email import send_email_async

_logger = _logging.getLogger(__name__)


def _escape(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def _safe_subject(value: Any) -> str:
    return str(value or "").replace("\r", " ").replace("\n", " ").strip()


def _build_reg_obj(data: dict):
    """Build a simple attribute object from a dict for use with document generators."""
    class _Obj:
        pass
    obj = _Obj()
    for k, v in data.items():
        setattr(obj, k, v)
    return obj


def _build_course_obj(course_dict: dict | None):
    """Build a course-like object (with optional logistics) from a dict."""
    if not course_dict:
        return None

    class _Obj:
        pass

    course_obj = _Obj()
    for k, v in course_dict.items():
        setattr(course_obj, k, v)

    if course_dict.get('logistics'):
        logistics_obj = _Obj()
        for k, v in course_dict['logistics'].items():
            setattr(logistics_obj, k, v)
        course_obj.logistics = logistics_obj
    else:
        course_obj.logistics = None

    return course_obj


def _member_email_html(member_name: str, course_title: str, salutation: str = "") -> str:
    greeting = _escape(f"{salutation} {member_name}".strip())
    safe_course_title = _escape(course_title)
    return f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Welcome to Livecode Technologies!</h2>
            <p>Hello {greeting},</p>
            <p>You have been registered to attend the <strong>{safe_course_title}</strong> training course.</p>
            <p>Attached are your personal training documents. Kindly review them before the session:</p>
            <ul>
                <li>An Invitation Letter</li>
                <li>A Pre-Training Evaluation Form (please fill and return before the course date)</li>
            </ul>
            <p>For queries, feel free to contact us:</p>
            <p><strong>Email:</strong> info@livecodetechnologies.com<br>
            <strong>Tel:</strong> +254 796 190 682</p>
        </div>
    </body>
    </html>
    """


def _lead_email_html(reg_obj, member_count: int = 0) -> str:
    group_note = ""
    if member_count > 0:
        group_note = f"<p>Individual confirmation emails with personal documents have also been sent to each of the <strong>{member_count}</strong> group member(s) you registered.</p>"
    return f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Thank You For Choosing Livecode Technologies!</h2>
            <p>Hello {_escape(reg_obj.title)} {_escape(reg_obj.first_name)} {_escape(reg_obj.last_name)},</p>
            <p>Thank you for registering for the <strong>{_escape(reg_obj.course_title)}</strong> course. This is to confirm that we have received your registration.</p>
            {group_note}
            <p>Kindly check your attachments for:</p>
            <ul>
                <li>A Payment Invoice</li>
                <li>An Invitation Letter</li>
                <li>A Pre-Training Evaluation Form</li>
            </ul>
            <p>One of our agents will be in touch with you shortly. For queries or requests for assistance, feel free to contact us via:</p>
            <p><strong>Email:</strong> info@livecodetechnologies.com<br>
            <strong>Tel:</strong> +254 796 190 682</p>
        </div>
    </body>
    </html>
    """


async def process_registration_email(registration_dict: dict, course_dict: dict = None):
    """
    Background task that:
    1. Parses group members (if any).
    2. Generates ONE shared invoice (with all participant names) and personal docs for lead.
    3. Sends the lead registrant all 3 documents.
    4. For each group member, generates personal Invitation Letter + Evaluation Form
       and sends them all 3 documents (reusing the shared invoice PDF).
    5. Sends a company notification email with a registration summary.
    """
    from app.core.config import settings as _settings

    reg_obj = _build_reg_obj(registration_dict)
    course_obj = _build_course_obj(course_dict)

    # --- Parse group members ---
    group_members: list[dict] = []
    raw_members = registration_dict.get("group_members_json")
    if raw_members:
        try:
            group_members = _json.loads(raw_members)
        except (_json.JSONDecodeError, TypeError):
            _logger.warning(
                "Could not parse group_members_json for registration %s",
                registration_dict.get("id"),
            )

    # Filter out the lead registrant (billing contact) from group_members if they were included
    # (matching case-insensitively by email) to prevent duplication in invoices and emails.
    lead_email = (reg_obj.email or "").strip().lower()
    group_members = [
        m for m in group_members
        if (m.get("email") or "").strip().lower() != lead_email
    ]

    # --- Generate shared invoice (includes all participant names for group regs) ---
    invoice_buffer = await asyncio.to_thread(
        generate_invoice_pdf, reg_obj, course_obj, group_members or None, reg_obj.currency
    )
    invoice_bytes = invoice_buffer.getvalue()
    invoice_filename = f"Invoice_INV-{str(reg_obj.id)[:8].upper()}.pdf"

    shared_invoice_attachment = {
        "filename": invoice_filename,
        "content": invoice_bytes,
        "maintype": "application",
        "subtype": "pdf",
    }

    def _build_doc_attachments(invitation_buf, form_buf) -> list[dict]:
        """Return the 3 standard attachment dicts, sharing the one invoice."""
        return [
            shared_invoice_attachment,
            {
                "filename": "Invitation_Letter.pdf",
                "content": invitation_buf.getvalue(),
                "maintype": "application",
                "subtype": "pdf",
            },
            {
                "filename": "Pre-Training_Evaluation_Form.docx",
                "content": form_buf.getvalue(),
                "maintype": "application",
                "subtype": "vnd.openxmlformats-officedocument.wordprocessingml.document",
            },
        ]

    # --- Generate & send lead registrant email ---
    lead_invitation = await asyncio.to_thread(generate_invitation_letter_pdf, reg_obj, course_obj)
    lead_form = await asyncio.to_thread(generate_pre_training_form_docx, reg_obj, course_obj)

    subject = _safe_subject(f"Registration Confirmation - {reg_obj.course_title}")
    await send_email_async(
        reg_obj.email,
        subject,
        _lead_email_html(reg_obj, member_count=len(group_members)),
        _build_doc_attachments(lead_invitation, lead_form),
    )
    _logger.info("Sent lead email to %s", reg_obj.email)

    # --- Send all 3 docs individually to each group member ---
    for member in group_members:
        member_email = member.get("email")
        if not member_email:
            continue

        member_reg_dict = {**registration_dict}
        member_reg_dict["first_name"] = member.get("first_name", "")
        member_reg_dict["last_name"] = member.get("last_name", "")
        member_reg_dict["title"] = member.get("title", "")
        member_reg_dict["phone"] = member.get("phone", "")
        member_reg_dict["email"] = member_email
        member_reg_dict["registration_type"] = "individual"
        member_reg_dict["group_size"] = None
        member_reg_dict["group_members_json"] = None

        member_obj = _build_reg_obj(member_reg_dict)
        member_invitation = await asyncio.to_thread(generate_invitation_letter_pdf, member_obj, course_obj)
        member_form = await asyncio.to_thread(generate_pre_training_form_docx, member_obj, course_obj)

        member_name = f"{member.get('first_name', '')} {member.get('last_name', '')}".strip()
        member_subject = _safe_subject(f"Training Registration - {reg_obj.course_title}")
        await send_email_async(
            member_email,
            member_subject,
            _member_email_html(member_name, reg_obj.course_title, salutation=member.get("title", "")),
            _build_doc_attachments(member_invitation, member_form),
        )
        _logger.info("Sent member email to %s", member_email)

    # --- Company notification email ---
    company_email = _settings.COMPANY_NOTIFICATION_EMAIL
    if company_email:
        total_participants = 1 + len(group_members)
        reg_type = registration_dict.get("registration_type", "individual")
        member_rows = "".join(
            f"<tr><td style='padding:4px 8px'>{_escape(m.get('first_name',''))} {_escape(m.get('last_name',''))}</td>"
            f"<td style='padding:4px 8px'>{_escape(m.get('email',''))}</td></tr>"
            for m in group_members
        )
        group_section = (
            f"<h4 style='margin-top:16px'>Group Members</h4>"
            f"<table border='1' cellpadding='0' cellspacing='0' style='border-collapse:collapse;font-size:13px'>"
            f"<tr style='background:#0F2942;color:white'><th style='padding:5px 10px'>Name</th><th style='padding:5px 10px'>Email</th></tr>"
            f"{member_rows}</table>"
        ) if group_members else ""

        company_html = f"""
        <html><body style="font-family:Arial,sans-serif;color:#333;padding:20px">
          <h2 style="color:#0F2942">📋 New Course Registration</h2>
          <table style="font-size:14px;border-collapse:collapse;width:100%;max-width:600px">
            <tr><td style="padding:5px 10px"><b>Course:</b></td><td style="padding:5px 10px">{_escape(reg_obj.course_title)}</td></tr>
            <tr style="background:#F7FAFC"><td style="padding:5px 10px"><b>Type:</b></td><td style="padding:5px 10px">{_escape(reg_type.title())} ({total_participants} participant(s))</td></tr>
            <tr><td style="padding:5px 10px"><b>Lead Registrant:</b></td><td style="padding:5px 10px">{_escape((reg_obj.title or '').strip())} {_escape(reg_obj.first_name)} {_escape(reg_obj.last_name)}</td></tr>
            <tr style="background:#F7FAFC"><td style="padding:5px 10px"><b>Organisation:</b></td><td style="padding:5px 10px">{_escape(registration_dict.get('organization') or 'N/A')}</td></tr>
            <tr><td style="padding:5px 10px"><b>Country:</b></td><td style="padding:5px 10px">{_escape(registration_dict.get('country') or 'N/A')}</td></tr>
            <tr style="background:#F7FAFC"><td style="padding:5px 10px"><b>Email:</b></td><td style="padding:5px 10px">{_escape(reg_obj.email)}</td></tr>
            <tr><td style="padding:5px 10px"><b>Phone:</b></td><td style="padding:5px 10px">{_escape(registration_dict.get('phone') or 'N/A')}</td></tr>
            <tr style="background:#F7FAFC"><td style="padding:5px 10px"><b>Schedule:</b></td><td style="padding:5px 10px">{_escape(registration_dict.get('schedule_date') or 'N/A')} - {_escape(registration_dict.get('schedule_location') or 'N/A')}</td></tr>
          </table>
          {group_section}
          <p style="color:#999;font-size:12px;margin-top:24px">Automated notification · Livecode Technologies registration system</p>
        </body></html>
        """
        notify_subject = _safe_subject(f"[New Registration] {reg_obj.course_title} - {reg_obj.first_name} {reg_obj.last_name}")
        await send_email_async(company_email, notify_subject, company_html, [shared_invoice_attachment])
        _logger.info("Sent company notification to %s", company_email)
