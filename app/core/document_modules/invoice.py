import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.core.document_modules.common import NumberedCanvas, get_registration_details


def generate_invoice_pdf(registration, course=None, group_members: list | None = None, currency: str = "USD") -> io.BytesIO:
    """Dynamically generates a beautiful, 3-page professional invoice PDF using ReportLab."""
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
    
    # Custom Brand Colors
    primary_color = colors.HexColor("#0F2942")  # Brand Navy
    secondary_color = colors.HexColor("#E28743")  # Brand Orange/Gold Accent
    text_dark = colors.HexColor("#2D3748")
    bg_light = colors.HexColor("#F7FAFC")
    border_color = colors.HexColor("#E2E8F0")

    # Custom Paragraph Styles
    title_style = ParagraphStyle(
        'InvoiceTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=24,
        leading=28,
        textColor=primary_color,
        spaceAfter=15
    )
    
    h2_style = ParagraphStyle(
        'InvoiceHeading2',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        textColor=primary_color,
        spaceBefore=10,
        spaceAfter=5
    )

    body_style = ParagraphStyle(
        'InvoiceBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=text_dark
    )

    body_bold = ParagraphStyle(
        'InvoiceBodyBold',
        parent=body_style,
        fontName='Helvetica-Bold'
    )

    header_cell_style = ParagraphStyle(
        'HeaderCell',
        parent=body_style,
        fontName='Helvetica-Bold',
        textColor=colors.white
    )

    story = []

    # ------------------ PAGE 1 ------------------
    # Top branding bar
    brand_table_data = [
        [
            Paragraph("<b>LIVECODE TECHNOLOGIES LTD</b><br/><font size=8 color='#718096'>Outreach & Corporate Training Division</font>", body_style),
            Paragraph("<b>PIN:</b> P051713624B<br/><b>REG NO:</b> PVT|XYUPDZP", ParagraphStyle('TaxRight', parent=body_style, alignment=2))
        ]
    ]
    brand_table = Table(brand_table_data, colWidths=[300, 188])
    brand_table.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 10),
        ('LINEBELOW', (0,0), (-1,-1), 1, border_color),
    ]))
    story.append(brand_table)
    story.append(Spacer(1, 20))

    # Title & Invoice details
    is_paid = getattr(registration, "status", "") == "confirmed"
    
    if is_paid:
        title_para = Paragraph("INVOICE <font color='green'>(PAID)</font>", title_style)
    else:
        title_para = Paragraph("INVOICE", title_style)
    story.append(title_para)

    # Metadata Block (Attention to vs Invoice details)
    invoice_no = f"INV-{1000 + int(str(registration.id.int)[:6]) % 90000}"
    cust_id = f"CUST-{1000 + int(str(registration.id.int)[6:12]) % 9000}"
    date_today = datetime.now().strftime("%B %d, %Y")

    meta_left = [
        Paragraph(f"<b>Attention To:</b> {registration.title or 'Mr.'} {details['first_name']} {details['last_name']}", body_style),
        Paragraph(f"<b>Organization:</b> {details['org']}", body_style),
        Paragraph(f"<b>Country:</b> {details['country']}", body_style),
        Paragraph(f"<b>Email:</b> {details['email']}", body_style),
    ]
    
    payment_method_val = getattr(registration, "payment_method", "Bank Transfer / Offline")
    payment_method_normalized = str(payment_method_val or "").strip().lower()
    show_payment_instructions = (
        not is_paid
        and payment_method_normalized in {"bank transfer / offline", "offline", "bank transfer"}
    )
    meta_right = [
        Paragraph(f"<b>Invoice No:</b> {invoice_no}", body_style),
        Paragraph(f"<b>Date:</b> {date_today}", body_style),
        Paragraph(f"<b>Customer ID:</b> {cust_id}", body_style),
        Paragraph(f"<b>Payment Method:</b> {payment_method_val}", body_style),
    ]

    meta_table_data = [
        [meta_left, meta_right]
    ]
    meta_table = Table(meta_table_data, colWidths=[244, 244])
    meta_table.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BACKGROUND', (0,0), (-1,-1), bg_light),
        ('BOX', (0,0), (-1,-1), 1, border_color),
        ('TOPPADDING', (0,0), (-1,-1), 12),
        ('BOTTOMPADDING', (0,0), (-1,-1), 12),
        ('LEFTPADDING', (0,0), (-1,-1), 12),
        ('RIGHTPADDING', (0,0), (-1,-1), 12),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 25))

    # Line Items Table
    is_kes = currency.upper() == "KES"
    price_val = details['price_kes'] if is_kes else details['price_usd']
    sym = "KES" if is_kes else "USD"
    
    pax_val = details['pax']
    subtotal = price_val * pax_val
    tax = subtotal * 0.16
    total_amount = subtotal + tax

    pax_text = f"{pax_val} participant" if pax_val == 1 else f"{pax_val} participants"

    items_data = [
        [
            Paragraph("Project/Event Description", header_cell_style),
            Paragraph("No. of Pax", header_cell_style),
            Paragraph(f"Unit Price ({sym})", header_cell_style),
            Paragraph(f"Total Price ({sym})", header_cell_style)
        ],
        [
            Paragraph(f"<b>{details['course_title']}</b><br/><font size=8 color='#718096'>Location: {details['location']} | Dates: {details['date_str']}</font>", body_style),
            Paragraph(pax_text, body_style),
            Paragraph(f"{price_val:,.2f}", body_style),
            Paragraph(f"{subtotal:,.2f}", body_style)
        ],
        # Empty space or simple summaries
        ["", "", Paragraph("<b>SUBTOTAL:</b>", body_bold), Paragraph(f"{sym} {subtotal:,.2f}", body_bold)],
        ["", "", Paragraph("<b>TAX (16%):</b>", body_bold), Paragraph(f"{sym} {tax:,.2f}", body_bold)],
        ["", "", Paragraph("<b>TOTAL AMOUNT:</b>", ParagraphStyle('TotalBold', parent=body_bold, textColor=primary_color)), Paragraph(f"{sym} {total_amount:,.2f}", ParagraphStyle('TotalBold2', parent=body_bold, textColor=primary_color))]
    ]

    items_table = Table(items_data, colWidths=[240, 80, 84, 84])
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), primary_color),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('ALIGN', (1,1), (-1,-1), 'RIGHT'),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('GRID', (0,0), (-1,1), 0.5, border_color),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
        ('LINEABOVE', (2,2), (3,-1), 1, border_color),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 20))

    # --- Participants List (group registrations) ---
    if group_members:
        participants_header = Paragraph("<b>GROUP PARTICIPANTS</b>", ParagraphStyle(
            'ParticipantsHead', parent=body_style, fontName='Helvetica-Bold',
            textColor=primary_color, fontSize=10
        ))
        story.append(participants_header)
        story.append(Spacer(1, 6))

        # Build lead row + member rows
        all_participants = [{
            "title": registration.title or "",
            "first_name": details["first_name"],
            "last_name": details["last_name"],
            "email": details["email"],
            "role": "Lead Registrant"
        }]
        for m in group_members:
            m_email = (m.get("email") or "").strip().lower()
            lead_email = (details["email"] or "").strip().lower()
            if m_email == lead_email:
                continue
            all_participants.append({
                "title": m.get("title", ""),
                "first_name": m.get("first_name", ""),
                "last_name": m.get("last_name", ""),
                "email": m.get("email", ""),
                "role": "Participant"
            })

        p_table_data = [
            [
                Paragraph("#", header_cell_style),
                Paragraph("Name", header_cell_style),
                Paragraph("Email", header_cell_style),
                Paragraph("Role", header_cell_style),
            ]
        ]
        for idx, p in enumerate(all_participants, start=1):
            full_name = f"{p['title']} {p['first_name']} {p['last_name']}".strip()
            p_table_data.append([
                Paragraph(str(idx), body_style),
                Paragraph(full_name, body_style),
                Paragraph(p["email"], body_style),
                Paragraph(p["role"], body_style),
            ])

        p_table = Table(p_table_data, colWidths=[24, 190, 190, 84])
        p_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), primary_color),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.4, border_color),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, bg_light]),
        ]))
        story.append(p_table)
        story.append(Spacer(1, 20))
    else:
        story.append(Spacer(1, 10))

    if show_payment_instructions:
        # Banking Details Cards
        bank_data_kes = [
            [Paragraph("<b>KES BANK DETAILS (EFT/WIRE)</b>", ParagraphStyle('BankHeadKes', parent=body_style, fontName='Helvetica-Bold', textColor=primary_color)), ""],
            [Paragraph("<b>Account Name:</b>", body_style), Paragraph("Livecode Technologies Limited", body_style)],
            [Paragraph("<b>Bank:</b>", body_style), Paragraph("Kenya Commercial Bank (KCB)", body_style)],
            [Paragraph("<b>Branch:</b>", body_style), Paragraph("Mortgage Centre Sarit", body_style)],
            [Paragraph("<b>Swift Code:</b>", body_style), Paragraph("KCBLKENX", body_style)],
            [Paragraph("<b>Account Number (KES):</b>", body_style), Paragraph("1253187703", body_style)],
        ]
        bank_table_kes = Table(bank_data_kes, colWidths=[100, 150])
        bank_table_kes.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), bg_light),
            ('SPAN', (0,0), (1,0)),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('BOX', (0,0), (-1,-1), 1, border_color),
            ('LEFTPADDING', (0,0), (-1,-1), 10),
            ('RIGHTPADDING', (0,0), (-1,-1), 10),
            ('TOPPADDING', (0,0), (-1,0), 8),
            ('BOTTOMPADDING', (0,-1), (-1,-1), 8),
        ]))

        bank_data_usd = [
            [Paragraph("<b>USD BANK DETAILS (EFT/WIRE)</b>", ParagraphStyle('BankHeadUsd', parent=body_style, fontName='Helvetica-Bold', textColor=primary_color)), ""],
            [Paragraph("<b>Account Name:</b>", body_style), Paragraph("LIVECODE TECHNOLOGIES LIMITED", body_style)],
            [Paragraph("<b>Bank:</b>", body_style), Paragraph("Co-operative Bank of Kenya Ltd", body_style)],
            [Paragraph("<b>Branch:</b>", body_style), Paragraph("Co-op House", body_style)],
            [Paragraph("<b>Swift Code:</b>", body_style), Paragraph("KCOOKENA", body_style)],
            [Paragraph("<b>Account Number (USD):</b>", body_style), Paragraph("02100825826300", body_style)],
        ]
        bank_table_usd = Table(bank_data_usd, colWidths=[100, 150])
        bank_table_usd.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), bg_light),
            ('SPAN', (0,0), (1,0)),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('BOX', (0,0), (-1,-1), 1, border_color),
            ('LEFTPADDING', (0,0), (-1,-1), 10),
            ('RIGHTPADDING', (0,0), (-1,-1), 10),
            ('TOPPADDING', (0,0), (-1,0), 8),
            ('BOTTOMPADDING', (0,-1), (-1,-1), 8),
        ]))

        if is_kes:
            bank_parent_table = Table([[bank_table_kes]], colWidths=[250])
        else:
            bank_parent_table = Table([[bank_table_usd]], colWidths=[250])

        bank_parent_table.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('LEFTPADDING', (0,0), (-1,-1), 0),
            ('RIGHTPADDING', (0,0), (-1,-1), 0),
            ('BOTTOMPADDING', (0,0), (-1,-1), 0),
            ('TOPPADDING', (0,0), (-1,-1), 0),
        ]))
        story.append(bank_parent_table)
        story.append(Spacer(1, 20))
        story.append(Paragraph("<b>Note:</b> All checks should be payable to: <i>Livecode Technologies Limited.</i><br/>Please send proof of payment to: <b>info@livecodetechnologies.com</b>", ParagraphStyle('NoteStyle', parent=body_style, fontSize=8.5)))

    story.append(PageBreak())

    # ------------------ PAGE 2 ------------------
    story.append(Paragraph("TERMS AND CONDITIONS", title_style))
    story.append(Spacer(1, 10))

    terms_of_payment = (
        "The client will make the full payment to either of the following account details: "
        "Livecode Technologies Limited (KES) Account No: 1253187703, Kenya Commercial Bank (KCB), "
        "Mortgage Centre Sarit, Swift Code: KCBLKENX; or LIVECODE TECHNOLOGIES LIMITED (USD) "
        "Account No: 02100825826300, Co-operative Bank of Kenya Ltd, Co-op House, Swift Code: KCOOKENA. "
        "16% VAT is payable until proof of exemption is provided."
    )
    if not show_payment_instructions:
        terms_of_payment = (
            "Payment has been received through the selected online payment channel. "
            "No additional bank transfer or wire payment is required for this invoice. "
            "16% VAT is payable until proof of exemption is provided."
        )

    tc_data = [
        ("1. DEFINITIONS AND APPLICATION", "In these Terms and Conditions \"Livecode Technologies\" means Livecode Technologies Ltd. \"Client\" any person at whose request or on whose behalf Livecode Technologies undertakes any business or provides advice, information or services. If any legislation is compulsorily applicable to any business undertaken, these Terms and Conditions shall, as regards such business, be read as subject to such legislation and nothing in these Terms and Conditions shall be construed as a surrender by Livecode Technologies of any of its rights or immunities or as an increase of any of its responsibilities or liabilities under such legislation."),
        ("2. Validity of Offer", "Ninety days (90) from date of issue."),
        ("3. Pricing", "Training Fee shall be charged at individual or group rates which includes facilitation and cost of workshop materials. Prices are subject to change at any time prior to Livecode Technologies acceptance of Client’s order."),
        ("4. Order Acceptance", "Livecode Technologies shall accept the client order once the training fees have been paid in full."),
        ("5. Terms of Payment", terms_of_payment),
        ("6. Delivery Time", "Client-site workshop will have a minimum duration of 5 working days and is subject to availability of an instructor."),
        ("7. Quorum", "All scheduled courses will be conducted as long as there's a participant that has confirmed."),
        ("8. Force Majeure", "Neither party will be liable for performance delays, nor for non-performance due to causes beyond its reasonable control; however, will this provision not apply to Client's payment obligation.")
    ]

    for item_title, item_desc in tc_data:
        story.append(Paragraph(f"<b>{item_title}</b>", h2_style))
        story.append(Paragraph(item_desc, body_style))
        story.append(Spacer(1, 8))

    story.append(PageBreak())

    # ------------------ PAGE 3 ------------------
    story.append(Paragraph("TERMS AND CONDITIONS (CONTINUED)", title_style))
    story.append(Spacer(1, 10))

    tc_data_p3 = [
        ("9. Confidentiality", "Confidential information includes without limitation, pricing, software and hardware products, product plans, marketing and sales information, business plans, customer and supplier data, financial and technical information, \"know-how,\" trade secrets, and other information, whether such information is in written, oral, electronic, web-based, or other form. These may not be divulged to any third party without prior written consent from Livecode Technologies. The Client shall exercise the same degree of care as that used to protect their own confidential information but no less than reasonable care."),
        ("10. Jurisdiction and Law", "These Terms and Conditions and any act or contract to which they apply shall be governed by the Laws of Kenya and any dispute arising out of any act or contract to which these Terms and Conditions apply shall be subject to the exclusive jurisdiction of the Courts of Kenya."),
        ("11. Further Information", "Please contact us in case you need clarification or further information. Email: <b>info@livecodetechnologies.com</b>")
    ]

    for item_title, item_desc in tc_data_p3:
        story.append(Paragraph(f"<b>{item_title}</b>", h2_style))
        story.append(Paragraph(item_desc, body_style))
        story.append(Spacer(1, 8))

    story.append(Spacer(1, 30))
    story.append(Paragraph("<b>Acceptance Form</b>", ParagraphStyle('AccTitle', parent=styles['Heading2'], textColor=primary_color)))
    story.append(Spacer(1, 5))
    story.append(Paragraph("I hereby accept the terms and conditions of the above-mentioned invoice and place an order with Livecode Technologies Ltd for the services indicated on the invoice.", body_style))
    story.append(Spacer(1, 15))

    sig_data = [
        [Paragraph("<b>Company Name:</b> ___________________________", body_style), Paragraph("<b>Quote/Invoice No:</b> " + invoice_no, body_style)],
        [Paragraph("<b>Authorized Officer:</b> ________________________", body_style), Paragraph("<b>Date:</b> ___________________________", body_style)],
        [Paragraph("<b>Signature:</b> _________________________", body_style), Paragraph("<b>Official Stamp/Seal:</b> [ Seal Below ]", body_style)]
    ]
    sig_table = Table(sig_data, colWidths=[244, 244])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('TOPPADDING', (0,0), (-1,-1), 10),
        ('BOTTOMPADDING', (0,0), (-1,-1), 10),
    ]))
    story.append(sig_table)

    # Build the document using the NumberedCanvas
    doc.build(story, canvasmaker=NumberedCanvas)
    buffer.seek(0)
    return buffer
