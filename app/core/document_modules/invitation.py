import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.core.document_modules.common import NumberedCanvas, get_registration_details


def generate_invitation_letter_pdf(registration, course=None) -> io.BytesIO:
    """Generates a professional 6-page training invitation letter containing full curriculum blocks."""
    details = get_registration_details(registration, course)
    
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
    secondary_color = colors.HexColor("#E28743")
    text_dark = colors.HexColor("#2D3748")
    bg_light = colors.HexColor("#F7FAFC")
    border_color = colors.HexColor("#E2E8F0")

    title_style = ParagraphStyle(
        'LetterTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=primary_color,
        spaceAfter=15
    )

    h2_style = ParagraphStyle(
        'LetterH2',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        textColor=primary_color,
        spaceBefore=12,
        spaceAfter=6,
        keepWithNext=True
    )

    body_style = ParagraphStyle(
        'LetterBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=14,
        textColor=text_dark,
        spaceAfter=8
    )

    story = []

    # ------------------ PAGE 1: COVER/BRAND PAGE ------------------
    story.append(Spacer(1, 150))
    story.append(Paragraph("<font size=28 color='#0F2942'><b>OFFICIAL INVITATION LETTER</b></font>", ParagraphStyle('CoverTitle', parent=body_style, alignment=1)))
    story.append(Spacer(1, 15))
    story.append(Paragraph(f"<font size=14 color='#E28743'><b>{details['course_title']}</b></font>", ParagraphStyle('CoverSub', parent=body_style, alignment=1)))
    story.append(Spacer(1, 10))
    story.append(Paragraph(f"<font size=11 color='#718096'>Dates: {details['date_str']} | Location: {details['location']}</font>", ParagraphStyle('CoverMeta', parent=body_style, alignment=1)))
    story.append(Spacer(1, 200))
    
    org_info = """
    <b>LIVECODE TECHNOLOGIES LTD</b><br/>
    Town Office: Equity Plaza, Nairobi, Kenya<br/>
    Tel: +254 796 190 682 | Email: info@livecodetechnologies.com<br/>
    Web: www.livecodetechnologies.com
    """
    story.append(Paragraph(org_info, ParagraphStyle('CoverOrg', parent=body_style, alignment=1, fontSize=9, leading=14)))
    story.append(PageBreak())

    # ------------------ PAGE 2: FORMAL LETTER ------------------
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
    story.append(Spacer(1, 15))

    # Recipient info
    recipient_text = f"""
    To:<br/>
    <b>{details['org']}</b>,<br/>
    {details['country']}.<br/><br/>
    <b>Attn:</b> {registration.title or 'Mr.'} {details['first_name']} {details['last_name']}
    """
    story.append(Paragraph(recipient_text, body_style))
    story.append(Spacer(1, 10))

    # Subject line
    subj_text = f"<b>SUBJECT: INVITATION TO ATTEND A {details['duration'].upper()} TRAINING WORKSHOP ON {details['course_title'].upper()}</b>"
    story.append(Paragraph(subj_text, ParagraphStyle('Subj', parent=body_style, fontName='Helvetica-Bold', textColor=primary_color, fontSize=10, leading=14)))
    story.append(Spacer(1, 12))

    # Body paragraphs
    intro = f"""We are delighted to invite you to participate in a {details['duration']} training workshop <b>"{details['course_title']}"</b> to be held from <b>{details['date_str']}</b> in <b>{details['location']}</b>."""
    story.append(Paragraph(intro, body_style))

    overview = """
    <b>Course Overview</b><br/>
    Take your analysis and reporting skills to an advanced professional level. This course combines standard analytical best practices with the power of modern business intelligence tools. Learn pivots, imports, data formatting, Dax expressions, dashboards, and automated custom reporting.
    """
    story.append(Paragraph(overview, body_style))

    audience = """
    <b>Target Audience</b><br/>
    This program is designed for business analysts, operations supervisors, IT coordinators, operations assistants, finance assistants, marketing professionals, small business owners, and administrators who want to master dynamic data reports.
    """
    story.append(Paragraph(audience, body_style))

    story.append(Spacer(1, 20))
    story.append(Paragraph("Yours Sincerely,", body_style))
    story.append(Spacer(1, 10))
    story.append(Paragraph("<b>Managing Director</b><br/>Livecode Technologies Ltd", ParagraphStyle('CEOStyle', parent=body_style, leading=13)))

    story.append(PageBreak())

    # ------------------ PAGES 3 - 5: COURSE OUTLINE / SYLLABUS ------------------
    story.append(Paragraph("COURSE OUTLINE & SYLLABUS", title_style))
    story.append(Spacer(1, 10))

    outline_data = [
        ("Course Objectives", [
            "Gain enhanced spreadsheets data skills: creating templates, charts, graphics, and formulas for business and operational work.",
            "How to calculate with advanced functions & formulas, create interactive charts using Excel.",
            "How to analyze data using Pivot Charts, insert graphic objects and quickly transform business data into informative reports.",
            "How to use business dashboards to compare multiple elements in one screen.",
            "How to generate management and weekly reports quickly and accurately."
        ]),
        ("Module 1: Introduction to Business Data Analysis with Excel", [
            "Functions and Formulae (Entering and Copying Formulae)",
            "Creating Formulas using Names (Managing Names using Name Manager)",
            "Naming Ranges (Creating Named Ranges, Inserting Names in Formulae)",
            "Formatting (Number Formatting, Cell Styles, Clearing Formatting)",
            "Case Study/Practical Component: Analyzing a real-world business dataset."
        ]),
        ("Module 2: Calculating with Formulas and Functions", [
            "Use Date and Time Functions",
            "Use Statistical Functions (Database Functions)",
            "Use Lookup Functions (Logical Functions)",
            "Case Study/Practical Component: Calculating key business metrics."
        ]),
        ("Module 3: Visualizing Data with Charts", [
            "Use Recommended Charts Tool (Create Chart with Quick Analysis)",
            "Align Chart Axis Labels (Display Value Axis in Millions)",
            "Create Combo Chart (Create Chart Template for Sharing)",
            "Build Dynamic Chart with Table",
            "Case Study/Practical Component: Creating a comprehensive data visualization report."
        ]),
        ("Module 4: Analyzing Data with Tables", [
            "Create Table with Quick Analysis (Remove Duplicate Records)",
            "Add Total Row to Table (Insert Calculated Columns)",
            "Filter Table Data with Custom Filter (Use Slicer to Filter Data)",
            "Apply Conditional Formatting (Sort and Filter Data by Color)",
            "Case Study/Practical Component: Managing and analyzing a large dataset."
        ]),
        ("Module 5: Analyzing Data with PivotTables", [
            "Overview of PivotTable & PivotChart",
            "Create PivotTable from Table (Change Report Layouts)",
            "Show and Hide Report Totals (Create Custom Calculations)",
            "Filter Pivot Data with Slicer and Timeline",
            "Case Study/Practical Component: Developing a sales report using PivotTables."
        ]),
        ("Module 6: Importing External Data Sources", [
            "Import Data from Text Files",
            "Create PivotTable & PivotChart from Microsoft Access",
            "Manage Data Connections",
            "Case Study/Practical Component: Integrating and analyzing data from multiple external sources."
        ]),
        ("Module 7: Data Manipulation in Excel", [
            "How Excel Handles Different Data Types",
            "Data Consistency (Building Datasheets)",
            "Sorting and Filtering",
            "Data Cleaning and Formatting",
            "Case Study/Practical Component: Cleaning a messy dataset for business analysis."
        ]),
        ("Module 8: Creating Dashboard Reports", [
            "Overview of Dashboard Architecture",
            "Create PivotTable and PivotChart",
            "Hide Field Buttons from PivotChart",
            "Use Slicer to Connect PivotTables (Build Slicer Dashboard Report)",
            "Case Study/Practical Component: Building an interactive KPI Excel dashboard."
        ]),
        ("Module 9: Power BI Essentials", [
            "Power BI Overview & Setting Up",
            "Installing Power BI Desktop",
            "Connecting to Multiple Data Sources (Data Modelling)",
            "Introduction to DAX (Crossjoin, CALCULATE, VALUES, CALENDAR)",
            "Case Study/Practical Component: Creating a data model in Power BI."
        ]),
        ("Module 10: Business Data Analytics with Power BI", [
            "Connecting to and Cleaning Data",
            "Creating Calculated Fields & Measures",
            "Building Charts (Line, Bar, Geo Maps)",
            "Creating a Dashboard & Slicers",
            "Case Study/Practical Component: Developing a full interactive Power BI dashboard."
        ])
    ]

    # Render syllabus pages
    for idx, (section_title, bullet_items) in enumerate(outline_data):
        # We can put page breaks between modules if it gets too crowded
        if idx in [4, 8]:
            story.append(PageBreak())
            story.append(Paragraph("COURSE OUTLINE (CONTINUED)", title_style))
            story.append(Spacer(1, 10))

        story.append(Paragraph(section_title, h2_style))
        for bullet in bullet_items:
            story.append(Paragraph(f"• {bullet}", ParagraphStyle('BulletStyle', parent=body_style, leftIndent=12, firstLineIndent=-8)))
        story.append(Spacer(1, 6))

    story.append(PageBreak())

    # ------------------ PAGE 6: METHODOLOGY & LOGISTICS ------------------
    story.append(Paragraph("METHODOLOGY & ACCREDITATION", title_style))
    story.append(Spacer(1, 10))

    methodology = """
    <b>Training Methodology</b><br/>
    The instructor-led training is delivered using a blended learning approach and comprises of presentations, guided sessions of practical exercises, web-based templates and intensive group case studies. Facilitators are industry experts with years of practical experience. All facilitation and materials are offered in English.
    """
    story.append(Paragraph(methodology, body_style))
    story.append(Spacer(1, 10))

    accreditation = """
    <b>Accreditation & Certification</b><br/>
    Upon successful completion of this training, participants will be issued with a Livecode Technologies official training certificate.
    """
    story.append(Paragraph(accreditation, body_style))
    story.append(Spacer(1, 10))

    venue = f"""
    <b>Training Venue</b><br/>
    The training will be conducted in <b>{details['location']}</b>. The course registration fee covers the course tuition, extensive training materials, certificates, break refreshments, and daily lunches. Travel, insurance, hotel accommodation and personal expenses are separately catered for by the participant.
    """
    story.append(Paragraph(venue, body_style))
    story.append(Spacer(1, 10))

    inquiries = """
    <b>Inquiries & Custom Options</b><br/>
    This course can also be fully customized/tailored for your organization. For custom deliveries or inquiries, contact us on Tel: <b>+254 796 190 682</b> or email <b>info@livecodetechnologies.com</b>.
    """
    story.append(Paragraph(inquiries, body_style))

    doc.build(story, canvasmaker=NumberedCanvas)
    buffer.seek(0)
    return buffer
