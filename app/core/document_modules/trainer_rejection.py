import io
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from app.core.document_modules.common import NumberedCanvas

def generate_trainer_rejection_letter_pdf(application) -> io.BytesIO:
    """Generates a professional trainer application rejection letter."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=54,
        leftMargin=54,
        topMargin=54,
        bottomMargin=72
    )

    styles = getSampleStyleSheet()
    primary_color = colors.HexColor("#0F2942")  # Brand Navy
    text_dark = colors.HexColor("#2D3748")
    border_color = colors.HexColor("#E2E8F0")

    body_style = ParagraphStyle(
        'LetterBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=16,
        textColor=text_dark,
        spaceAfter=10
    )

    story = []

    # Header block
    brand_hdr = [
        [
            Paragraph("<b>LIVECODE TECHNOLOGIES LTD</b>", body_style),
            Paragraph("<b>Date:</b> " + datetime.now().strftime("%d %B %Y"), ParagraphStyle('DateAl', parent=body_style, alignment=2))
        ]
    ]
    brand_tbl = Table(brand_hdr, colWidths=[244, 244])
    brand_tbl.setStyle(TableStyle([
        ('LINEBELOW', (0,0), (-1,-1), 0.5, border_color),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(brand_tbl)
    story.append(Spacer(1, 25))

    # Recipient info
    recipient_text = f"""
    To:<br/>
    <b>{application.full_name}</b>,<br/>
    {application.city}, {application.country}.<br/><br/>
    """
    story.append(Paragraph(recipient_text, body_style))
    story.append(Spacer(1, 15))

    # Subject line
    subj_text = "<b>SUBJECT: UPDATE ON YOUR TRAINER APPLICATION</b>"
    story.append(Paragraph(subj_text, ParagraphStyle('Subj', parent=body_style, fontName='Helvetica-Bold', textColor=primary_color, fontSize=11, leading=16)))
    story.append(Spacer(1, 15))

    # Body paragraphs
    intro = f"""Dear {application.full_name},<br/><br/>
    Thank you for taking the time to apply for a trainer position at Livecode Technologies Ltd. We appreciate your interest in joining our faculty and carefully reviewed your CV and cover letter regarding your expertise in {application.specialization}.
    """
    story.append(Paragraph(intro, body_style))

    body_text = """
    We receive many applications from highly qualified professionals like yourself. After careful consideration of your application and qualifications against our current operational requirements and upcoming training schedules, we regret to inform you that we will not be moving forward with your application at this time.
    <br/><br/>
    Please note that this decision is largely based on our current capacity and specific specialization needs for the upcoming quarter, and does not necessarily reflect on your professional capabilities or qualifications.
    """
    story.append(Paragraph(body_text, body_style))

    future_text = """
    With your permission, we will keep your resume on file. Should a training opportunity open up that aligns closely with your skill set and geographical preferences, we will reach out to you.
    <br/><br/>
    We thank you again for your interest in Livecode Technologies and wish you every success in your future professional endeavors.
    """
    story.append(Paragraph(future_text, body_style))

    story.append(Spacer(1, 30))
    story.append(Paragraph("Yours Sincerely,", body_style))
    story.append(Spacer(1, 10))
    story.append(Paragraph("<b>Management Team</b><br/>Livecode Technologies Ltd", ParagraphStyle('MgmtStyle', parent=body_style, leading=14)))

    doc.build(story, canvasmaker=NumberedCanvas)
    buffer.seek(0)
    return buffer
