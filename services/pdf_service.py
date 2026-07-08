"""
PDF Generation Service for HMIS Platform
Generates real, production-grade branded PDFs for:
- Invoices & Payment Receipts
- Prescriptions with QR code verification
- Lab Reports with normal range highlighting
- Discharge Summaries
"""
import io
import os
import qrcode
from datetime import datetime
from typing import List, Dict, Any, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, HRFlowable, PageBreak
)
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics import renderPDF

# ─── Constants ───────────────────────────────────────────────────────────────

PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 15 * mm
BRAND_PRIMARY = colors.HexColor("#0d9488")   # Teal
BRAND_DARK = colors.HexColor("#1e293b")      # Dark Slate
BRAND_LIGHT = colors.HexColor("#f0fdfa")     # Teal 50
BRAND_ACCENT = colors.HexColor("#f59e0b")    # Amber
BRAND_RED = colors.HexColor("#ef4444")       # Red for abnormal
BRAND_GREEN = colors.HexColor("#22c55e")     # Green for normal

# ─── Style Helpers ───────────────────────────────────────────────────────────

def get_styles():
    """Returns a curated set of paragraph styles for PDF documents."""
    styles = getSampleStyleSheet()
    
    styles.add(ParagraphStyle(
        name='HospitalName',
        fontName='Helvetica-Bold',
        fontSize=16,
        textColor=BRAND_DARK,
        alignment=TA_LEFT,
        spaceAfter=2
    ))
    styles.add(ParagraphStyle(
        name='HospitalAddress',
        fontName='Helvetica',
        fontSize=8,
        textColor=colors.HexColor("#64748b"),
        alignment=TA_LEFT,
        spaceAfter=1
    ))
    styles.add(ParagraphStyle(
        name='DocTitle',
        fontName='Helvetica-Bold',
        fontSize=13,
        textColor=BRAND_PRIMARY,
        alignment=TA_CENTER,
        spaceBefore=8,
        spaceAfter=8
    ))
    styles.add(ParagraphStyle(
        name='SectionTitle',
        fontName='Helvetica-Bold',
        fontSize=10,
        textColor=BRAND_DARK,
        spaceBefore=10,
        spaceAfter=4,
        borderPadding=(0, 0, 2, 0)
    ))
    styles.add(ParagraphStyle(
        name='FieldLabel',
        fontName='Helvetica-Bold',
        fontSize=8,
        textColor=colors.HexColor("#64748b"),
    ))
    styles.add(ParagraphStyle(
        name='FieldValue',
        fontName='Helvetica',
        fontSize=9,
        textColor=BRAND_DARK,
    ))
    styles.add(ParagraphStyle(
        name='SmallText',
        fontName='Helvetica',
        fontSize=7,
        textColor=colors.HexColor("#94a3b8"),
    ))
    styles.add(ParagraphStyle(
        name='FooterText',
        fontName='Helvetica-Oblique',
        fontSize=7,
        textColor=colors.HexColor("#94a3b8"),
        alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        name='AbnormalValue',
        fontName='Helvetica-Bold',
        fontSize=9,
        textColor=BRAND_RED,
    ))
    styles.add(ParagraphStyle(
        name='NormalValue',
        fontName='Helvetica',
        fontSize=9,
        textColor=BRAND_DARK,
    ))
    
    return styles


def generate_qr_image(data: str, size: int = 80) -> Image:
    """Generate a QR code image from string data."""
    qr = qrcode.QRCode(version=1, box_size=4, border=1)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    buf = io.BytesIO()
    if type(img).__name__ == "PilImage":
        # Use getattr to prevent static type-checking warnings (e.g. Pyright/Pylance)
        # since the base class BaseImage.save() signature does not declare 'format'.
        save_fn = getattr(img, "save")
        save_fn(buf, format="PNG")
    else:
        img.save(buf)
    buf.seek(0)
    return Image(buf, width=size, height=size)


def build_header_table(hospital: Dict, doc_type: str, doc_number: str, doc_date: str, styles) -> Table:
    """Build a standardized header with hospital info, document type, and date."""
    
    hospital_name = hospital.get("name", "Hospital Name")
    hospital_address = hospital.get("address", "")
    hospital_phone = hospital.get("phone", "")
    hospital_email = hospital.get("email", "")
    gstin = hospital.get("gstin", "")
    
    # Left: Hospital Details
    left_content = [
        Paragraph(hospital_name, styles['HospitalName']),
        Paragraph(hospital_address, styles['HospitalAddress']),
    ]
    if hospital_phone:
        left_content.append(Paragraph(f"📞 {hospital_phone}  |  ✉ {hospital_email}", styles['HospitalAddress']))
    if gstin:
        left_content.append(Paragraph(f"GSTIN: {gstin}", styles['HospitalAddress']))
    
    # Right: Document type, number, date
    right_content = [
        Paragraph(doc_type, ParagraphStyle('DocType', fontName='Helvetica-Bold', fontSize=10, textColor=BRAND_PRIMARY, alignment=TA_RIGHT)),
        Paragraph(f"<b>{doc_number}</b>", ParagraphStyle('DocNum', fontName='Helvetica', fontSize=9, textColor=BRAND_DARK, alignment=TA_RIGHT)),
        Paragraph(doc_date, ParagraphStyle('DocDate', fontName='Helvetica', fontSize=8, textColor=colors.HexColor("#64748b"), alignment=TA_RIGHT)),
    ]
    
    header_data = [[left_content, right_content]]
    header_table = Table(header_data, colWidths=[PAGE_WIDTH * 0.6, PAGE_WIDTH * 0.28])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    return header_table


def build_patient_info_table(patient: Dict, styles, extra_fields: Optional[Dict] = None) -> Table:
    """Build a standardized patient information block."""
    fields = [
        ("Patient Name", f"{patient.get('first_name', '')} {patient.get('last_name', '')}"),
        ("MRN", patient.get("mrn", "N/A")),
        ("Age / Gender", f"{patient.get('age', 'N/A')} / {patient.get('gender', 'N/A')}"),
        ("Phone", patient.get("phone", "N/A")),
    ]
    if patient.get("abha_number"):
        fields.append(("ABHA No.", patient.get("abha_number")))
    
    if extra_fields:
        for k, v in extra_fields.items():
            fields.append((k, v))
    
    # Build 2-column layout
    rows = []
    for i in range(0, len(fields), 2):
        left_label = Paragraph(f"<b>{fields[i][0]}:</b>", styles['FieldLabel'])
        left_value = Paragraph(str(fields[i][1]), styles['FieldValue'])
        
        if i + 1 < len(fields):
            right_label = Paragraph(f"<b>{fields[i+1][0]}:</b>", styles['FieldLabel'])
            right_value = Paragraph(str(fields[i+1][1]), styles['FieldValue'])
        else:
            right_label = Paragraph("", styles['FieldLabel'])
            right_value = Paragraph("", styles['FieldValue'])
        
        rows.append([left_label, left_value, right_label, right_value])
    
    col_widths = [PAGE_WIDTH * 0.14, PAGE_WIDTH * 0.34, PAGE_WIDTH * 0.14, PAGE_WIDTH * 0.26]
    table = Table(rows, colWidths=col_widths)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), BRAND_LIGHT),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
    ]))
    return table


def build_footer(canvas, doc, hospital_name: str):
    """Draw standardized footer on every page."""
    canvas.saveState()
    # Line separator
    canvas.setStrokeColor(colors.HexColor("#e2e8f0"))
    canvas.setLineWidth(0.5)
    canvas.line(MARGIN, 25 * mm, PAGE_WIDTH - MARGIN, 25 * mm)
    # Footer text
    canvas.setFont("Helvetica-Oblique", 7)
    canvas.setFillColor(colors.HexColor("#94a3b8"))
    canvas.drawCentredString(PAGE_WIDTH / 2, 20 * mm, f"This is a computer-generated document from {hospital_name} HMIS Platform.")
    canvas.drawCentredString(PAGE_WIDTH / 2, 16 * mm, "No signature is required. Verify authenticity by scanning the QR code.")
    # Page number
    canvas.setFont("Helvetica", 7)
    canvas.drawRightString(PAGE_WIDTH - MARGIN, 12 * mm, f"Page {doc.page}")
    canvas.restoreState()


# ═══════════════════════════════════════════════════════════════════════════════
# INVOICE PDF GENERATOR
# ═══════════════════════════════════════════════════════════════════════════════

def generate_invoice_pdf(
    invoice: Dict,
    patient: Dict,
    hospital: Dict,
    items: List[Dict],
    payments: Optional[List[Dict]] = None,
    base_url: str = ""
) -> bytes:
    """Generate a professional, GST-compliant invoice PDF."""
    buffer = io.BytesIO()
    styles = get_styles()
    
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=30 * mm
    )
    
    story = []
    hospital_name = hospital.get("name", "Hospital")
    invoice_number = invoice.get("invoice_number", "N/A")
    invoice_date = invoice.get("created_at", datetime.utcnow())
    if isinstance(invoice_date, str):
        try:
            invoice_date = datetime.fromisoformat(invoice_date)
        except:
            invoice_date = datetime.utcnow()
    
    date_str = invoice_date.strftime("%d %b %Y, %I:%M %p")
    
    # Header
    story.append(build_header_table(hospital, "TAX INVOICE", invoice_number, date_str, styles))
    story.append(Spacer(1, 6 * mm))
    
    # Teal accent line
    story.append(HRFlowable(width="100%", thickness=2, color=BRAND_PRIMARY, spaceBefore=0, spaceAfter=4))
    
    # Patient Info
    extra = {}
    if invoice.get("doctor_name"):
        extra["Consulting Doctor"] = invoice.get("doctor_name")
    story.append(build_patient_info_table(patient, styles, extra))
    story.append(Spacer(1, 6 * mm))
    
    # Items Table
    story.append(Paragraph("INVOICE ITEMS", styles['SectionTitle']))
    
    header_row = [
        Paragraph("<b>#</b>", styles['FieldLabel']),
        Paragraph("<b>Description</b>", styles['FieldLabel']),
        Paragraph("<b>HSN/SAC</b>", styles['FieldLabel']),
        Paragraph("<b>Qty</b>", styles['FieldLabel']),
        Paragraph("<b>Rate (₹)</b>", styles['FieldLabel']),
        Paragraph("<b>Amount (₹)</b>", styles['FieldLabel']),
    ]
    
    table_data = [header_row]
    subtotal = 0.0
    for idx, item in enumerate(items, 1):
        qty = item.get("quantity", 1)
        rate = item.get("rate", item.get("unit_price", 0))
        amount = qty * rate
        subtotal += amount
        
        table_data.append([
            Paragraph(str(idx), styles['FieldValue']),
            Paragraph(item.get("description", item.get("name", "Service")), styles['FieldValue']),
            Paragraph(item.get("hsn_sac", "9993"), styles['SmallText']),
            Paragraph(str(qty), styles['FieldValue']),
            Paragraph(f"{rate:,.2f}", styles['FieldValue']),
            Paragraph(f"{amount:,.2f}", styles['FieldValue']),
        ])
    
    col_widths = [PAGE_WIDTH * 0.05, PAGE_WIDTH * 0.35, PAGE_WIDTH * 0.1, PAGE_WIDTH * 0.07, PAGE_WIDTH * 0.15, PAGE_WIDTH * 0.16]
    items_table = Table(table_data, colWidths=col_widths)
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), BRAND_PRIMARY),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (3, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ('INNERGRID', (0, 1), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 4 * mm))
    
    # Totals
    discount = float(invoice.get("discount", 0))
    tax_pct = float(invoice.get("tax_percentage", 0))
    tax_amt = (subtotal - discount) * (tax_pct / 100) if tax_pct else float(invoice.get("tax_amount", 0))
    grand_total = float(invoice.get("grand_total", subtotal - discount + tax_amt))
    amount_paid = float(invoice.get("amount_paid", 0))
    balance = grand_total - amount_paid
    
    totals_data = [
        ["", "", "Subtotal:", f"₹ {subtotal:,.2f}"],
    ]
    if discount > 0:
        totals_data.append(["", "", "Discount:", f"- ₹ {discount:,.2f}"])
    if tax_amt > 0:
        tax_label = f"GST ({tax_pct:.0f}%):" if tax_pct else "Tax:"
        totals_data.append(["", "", tax_label, f"₹ {tax_amt:,.2f}"])
    totals_data.append(["", "", "Grand Total:", f"₹ {grand_total:,.2f}"])
    if amount_paid > 0:
        totals_data.append(["", "", "Amount Paid:", f"₹ {amount_paid:,.2f}"])
    totals_data.append(["", "", "Balance Due:", f"₹ {balance:,.2f}"])
    
    # Format totals
    formatted_totals = []
    for row in totals_data:
        formatted_totals.append([
            "", "",
            Paragraph(f"<b>{row[2]}</b>", ParagraphStyle('TotalLabel', fontName='Helvetica-Bold', fontSize=9, textColor=BRAND_DARK, alignment=TA_RIGHT)),
            Paragraph(f"<b>{row[3]}</b>", ParagraphStyle('TotalValue', fontName='Helvetica-Bold', fontSize=9, textColor=BRAND_DARK, alignment=TA_RIGHT)),
        ])
    
    totals_table = Table(formatted_totals, colWidths=[PAGE_WIDTH * 0.3, PAGE_WIDTH * 0.2, PAGE_WIDTH * 0.2, PAGE_WIDTH * 0.18])
    totals_table.setStyle(TableStyle([
        ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LINEABOVE', (2, -1), (-1, -1), 1, BRAND_PRIMARY),
        ('BACKGROUND', (2, -1), (-1, -1), BRAND_LIGHT),
    ]))
    story.append(totals_table)
    story.append(Spacer(1, 6 * mm))
    
    # Payment History
    if payments:
        story.append(Paragraph("PAYMENT HISTORY", styles['SectionTitle']))
        pay_header = [
            Paragraph("<b>Date</b>", styles['FieldLabel']),
            Paragraph("<b>Method</b>", styles['FieldLabel']),
            Paragraph("<b>Transaction ID</b>", styles['FieldLabel']),
            Paragraph("<b>Amount (₹)</b>", styles['FieldLabel']),
        ]
        pay_data = [pay_header]
        for p in payments:
            p_date = p.get("created_at", datetime.utcnow())
            if isinstance(p_date, datetime):
                p_date = p_date.strftime("%d %b %Y")
            pay_data.append([
                Paragraph(str(p_date), styles['FieldValue']),
                Paragraph(p.get("payment_method", "Cash").upper(), styles['FieldValue']),
                Paragraph(p.get("transaction_id", "—"), styles['SmallText']),
                Paragraph(f"{float(p.get('amount', 0)):,.2f}", styles['FieldValue']),
            ])
        pay_table = Table(pay_data, colWidths=[PAGE_WIDTH * 0.2, PAGE_WIDTH * 0.18, PAGE_WIDTH * 0.3, PAGE_WIDTH * 0.2])
        pay_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ('ALIGN', (3, 0), (3, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
        ]))
        story.append(pay_table)
        story.append(Spacer(1, 4 * mm))
    
    # QR Code + Verification
    qr_data = f"{base_url}/api/billing/invoices/{invoice.get('id', '')}/verify" if base_url else f"INV:{invoice_number}"
    qr_img = generate_qr_image(qr_data, size=60)
    
    qr_table = Table(
        [[qr_img, Paragraph("Scan QR code to verify this invoice online.<br/>This is a computer-generated tax invoice.", styles['SmallText'])]],
        colWidths=[70, PAGE_WIDTH * 0.6]
    )
    qr_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (1, 0), (1, 0), 10),
    ]))
    story.append(qr_table)
    
    doc.build(story, onFirstPage=lambda c, d: build_footer(c, d, hospital_name),
              onLaterPages=lambda c, d: build_footer(c, d, hospital_name))
    
    return buffer.getvalue()


# ═══════════════════════════════════════════════════════════════════════════════
# PRESCRIPTION PDF GENERATOR
# ═══════════════════════════════════════════════════════════════════════════════

def generate_prescription_pdf(
    prescription: Dict,
    patient: Dict,
    doctor: Dict,
    hospital: Dict,
    base_url: str = ""
) -> bytes:
    """Generate a professional prescription PDF with medication details and QR verification."""
    buffer = io.BytesIO()
    styles = get_styles()
    
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=30 * mm
    )
    
    story = []
    hospital_name = hospital.get("name", "Hospital")
    
    rx_date = prescription.get("created_at", datetime.utcnow())
    if isinstance(rx_date, str):
        try:
            rx_date = datetime.fromisoformat(rx_date)
        except:
            rx_date = datetime.utcnow()
    date_str = rx_date.strftime("%d %b %Y")
    
    rx_id = prescription.get("id", str(prescription.get("_id", "N/A")))
    
    # Header
    story.append(build_header_table(hospital, "℞ PRESCRIPTION", f"RX-{rx_id[-8:].upper()}", date_str, styles))
    story.append(Spacer(1, 4 * mm))
    story.append(HRFlowable(width="100%", thickness=2, color=BRAND_PRIMARY, spaceBefore=0, spaceAfter=4))
    
    # Doctor Info
    doctor_name = doctor.get("name", "Doctor")
    doctor_reg = doctor.get("registration_number", "")
    doctor_dept = doctor.get("department_name", doctor.get("department", ""))
    
    doc_info = f"<b>Dr. {doctor_name}</b>"
    if doctor_reg:
        doc_info += f"  |  Reg. No: {doctor_reg}"
    if doctor_dept:
        doc_info += f"  |  {doctor_dept}"
    story.append(Paragraph(doc_info, styles['FieldValue']))
    story.append(Spacer(1, 4 * mm))
    
    # Patient Info
    story.append(build_patient_info_table(patient, styles))
    story.append(Spacer(1, 6 * mm))
    
    # Diagnosis
    diagnoses = prescription.get("diagnosis", [])
    if diagnoses:
        story.append(Paragraph("DIAGNOSIS", styles['SectionTitle']))
        diag_text = ", ".join(diagnoses) if isinstance(diagnoses, list) else str(diagnoses)
        story.append(Paragraph(diag_text, styles['FieldValue']))
        story.append(Spacer(1, 4 * mm))
    
    # Medications Table
    story.append(Paragraph("℞ MEDICATIONS", styles['SectionTitle']))
    
    medications = prescription.get("medications", [])
    if medications:
        med_header = [
            Paragraph("<b>#</b>", styles['FieldLabel']),
            Paragraph("<b>Medicine</b>", styles['FieldLabel']),
            Paragraph("<b>Dosage</b>", styles['FieldLabel']),
            Paragraph("<b>Frequency</b>", styles['FieldLabel']),
            Paragraph("<b>Duration</b>", styles['FieldLabel']),
            Paragraph("<b>Instructions</b>", styles['FieldLabel']),
        ]
        
        med_data = [med_header]
        for idx, med in enumerate(medications, 1):
            med_data.append([
                Paragraph(str(idx), styles['FieldValue']),
                Paragraph(f"<b>{med.get('name', med.get('drug_name', 'N/A'))}</b>", styles['FieldValue']),
                Paragraph(med.get("dosage", "N/A"), styles['FieldValue']),
                Paragraph(med.get("frequency", "N/A"), styles['FieldValue']),
                Paragraph(med.get("duration", "N/A"), styles['FieldValue']),
                Paragraph(med.get("instructions", med.get("notes", "—")), styles['SmallText']),
            ])
        
        col_widths = [PAGE_WIDTH * 0.04, PAGE_WIDTH * 0.22, PAGE_WIDTH * 0.12, PAGE_WIDTH * 0.16, PAGE_WIDTH * 0.12, PAGE_WIDTH * 0.22]
        med_table = Table(med_data, colWidths=col_widths)
        med_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), BRAND_PRIMARY),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ('INNERGRID', (0, 1), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ]))
        story.append(med_table)
    else:
        story.append(Paragraph("No medications prescribed.", styles['FieldValue']))
    
    story.append(Spacer(1, 6 * mm))
    
    # Clinical Notes
    notes = prescription.get("notes", prescription.get("clinical_notes", ""))
    if notes:
        story.append(Paragraph("CLINICAL NOTES", styles['SectionTitle']))
        story.append(Paragraph(notes, styles['FieldValue']))
        story.append(Spacer(1, 4 * mm))
    
    # Follow-up
    follow_up = prescription.get("follow_up", prescription.get("follow_up_date", ""))
    if follow_up:
        story.append(Paragraph("FOLLOW-UP", styles['SectionTitle']))
        story.append(Paragraph(str(follow_up), styles['FieldValue']))
        story.append(Spacer(1, 4 * mm))
    
    # QR Code
    qr_data = f"{base_url}/api/prescription/{rx_id}/verify" if base_url else f"RX:{rx_id}"
    qr_img = generate_qr_image(qr_data, size=55)
    
    qr_row = Table(
        [[qr_img, Paragraph(f"Prescription ID: {rx_id}<br/>Scan to verify at pharmacy.", styles['SmallText'])]],
        colWidths=[65, PAGE_WIDTH * 0.5]
    )
    qr_row.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('LEFTPADDING', (1, 0), (1, 0), 10)]))
    story.append(qr_row)
    
    doc.build(story, onFirstPage=lambda c, d: build_footer(c, d, hospital_name),
              onLaterPages=lambda c, d: build_footer(c, d, hospital_name))
    
    return buffer.getvalue()


# ═══════════════════════════════════════════════════════════════════════════════
# LAB REPORT PDF GENERATOR
# ═══════════════════════════════════════════════════════════════════════════════

def generate_lab_report_pdf(
    lab_order: Dict,
    results: List[Dict],
    patient: Dict,
    hospital: Dict,
    doctor_name: str = "",
    base_url: str = ""
) -> bytes:
    """Generate a lab report PDF with abnormal value highlighting."""
    buffer = io.BytesIO()
    styles = get_styles()
    
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=30 * mm
    )
    
    story = []
    hospital_name = hospital.get("name", "Hospital")
    
    order_date = lab_order.get("created_at", datetime.utcnow())
    if isinstance(order_date, str):
        try:
            order_date = datetime.fromisoformat(order_date)
        except:
            order_date = datetime.utcnow()
    date_str = order_date.strftime("%d %b %Y")
    
    order_id = str(lab_order.get("id", lab_order.get("_id", "N/A")))
    
    # Header
    story.append(build_header_table(hospital, "LABORATORY REPORT", f"LAB-{order_id[-8:].upper()}", date_str, styles))
    story.append(Spacer(1, 4 * mm))
    story.append(HRFlowable(width="100%", thickness=2, color=BRAND_PRIMARY, spaceBefore=0, spaceAfter=4))
    
    # Patient Info
    extra = {}
    if doctor_name:
        extra["Referred By"] = f"Dr. {doctor_name}"
    
    report_date = lab_order.get("completed_at", lab_order.get("updated_at"))
    if report_date:
        if isinstance(report_date, datetime):
            extra["Report Date"] = report_date.strftime("%d %b %Y, %I:%M %p")
        else:
            extra["Report Date"] = str(report_date)
    
    story.append(build_patient_info_table(patient, styles, extra))
    story.append(Spacer(1, 6 * mm))
    
    # Test Name
    test_name = lab_order.get("test_name", "Laboratory Test")
    story.append(Paragraph(f"TEST: {test_name}", styles['SectionTitle']))
    story.append(Spacer(1, 2 * mm))
    
    # Results Table
    res_header = [
        Paragraph("<b>Parameter</b>", styles['FieldLabel']),
        Paragraph("<b>Result</b>", styles['FieldLabel']),
        Paragraph("<b>Unit</b>", styles['FieldLabel']),
        Paragraph("<b>Normal Range</b>", styles['FieldLabel']),
        Paragraph("<b>Status</b>", styles['FieldLabel']),
    ]
    
    res_data = [res_header]
    for r in results:
        value = str(r.get("value", "—"))
        normal_range = r.get("normal_range", "")
        is_abnormal = r.get("is_abnormal", False)
        
        value_style = styles['AbnormalValue'] if is_abnormal else styles['NormalValue']
        status_text = "⚠ ABNORMAL" if is_abnormal else "✓ Normal"
        status_color = BRAND_RED if is_abnormal else BRAND_GREEN
        
        res_data.append([
            Paragraph(r.get("parameter", r.get("test_parameter", "—")), styles['FieldValue']),
            Paragraph(value, value_style),
            Paragraph(r.get("unit", ""), styles['SmallText']),
            Paragraph(normal_range, styles['SmallText']),
            Paragraph(status_text, ParagraphStyle('Status', fontName='Helvetica-Bold', fontSize=8, textColor=status_color)),
        ])
    
    col_widths = [PAGE_WIDTH * 0.28, PAGE_WIDTH * 0.15, PAGE_WIDTH * 0.12, PAGE_WIDTH * 0.2, PAGE_WIDTH * 0.13]
    res_table = Table(res_data, colWidths=col_widths)
    res_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), BRAND_PRIMARY),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ('INNERGRID', (0, 1), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
    ]))
    story.append(res_table)
    story.append(Spacer(1, 6 * mm))
    
    # Comments
    comments = lab_order.get("comments", "")
    if comments:
        story.append(Paragraph("PATHOLOGIST COMMENTS", styles['SectionTitle']))
        story.append(Paragraph(comments, styles['FieldValue']))
        story.append(Spacer(1, 4 * mm))
    
    # QR Code
    qr_data = f"{base_url}/api/labs/results/{order_id}/verify" if base_url else f"LAB:{order_id}"
    qr_img = generate_qr_image(qr_data, size=55)
    qr_row = Table(
        [[qr_img, Paragraph(f"Lab Order ID: {order_id}<br/>Scan to verify report authenticity.", styles['SmallText'])]],
        colWidths=[65, PAGE_WIDTH * 0.5]
    )
    qr_row.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('LEFTPADDING', (1, 0), (1, 0), 10)]))
    story.append(qr_row)
    
    doc.build(story, onFirstPage=lambda c, d: build_footer(c, d, hospital_name),
              onLaterPages=lambda c, d: build_footer(c, d, hospital_name))
    
    return buffer.getvalue()


# ═══════════════════════════════════════════════════════════════════════════════
# DISCHARGE SUMMARY PDF GENERATOR
# ═══════════════════════════════════════════════════════════════════════════════

def generate_discharge_summary_pdf(
    admission: Dict,
    patient: Dict,
    hospital: Dict,
    doctor: Dict,
    visits: Optional[List[Dict]] = None,
    medications: Optional[List[Dict]] = None,
    base_url: str = ""
) -> bytes:
    """Generate a comprehensive IPD discharge summary PDF."""
    buffer = io.BytesIO()
    styles = get_styles()
    
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=30 * mm
    )
    
    story = []
    hospital_name = hospital.get("name", "Hospital")
    
    admit_date = admission.get("admitted_at", admission.get("created_at", datetime.utcnow()))
    if isinstance(admit_date, str):
        try:
            admit_date = datetime.fromisoformat(admit_date)
        except:
            admit_date = datetime.utcnow()
    
    discharge_date = admission.get("discharged_at", datetime.utcnow())
    if isinstance(discharge_date, str):
        try:
            discharge_date = datetime.fromisoformat(discharge_date)
        except:
            discharge_date = datetime.utcnow()
    
    admission_id = str(admission.get("id", admission.get("_id", "N/A")))
    date_str = discharge_date.strftime("%d %b %Y") if isinstance(discharge_date, datetime) else str(discharge_date)
    
    # Header
    story.append(build_header_table(hospital, "DISCHARGE SUMMARY", f"DS-{admission_id[-8:].upper()}", date_str, styles))
    story.append(Spacer(1, 4 * mm))
    story.append(HRFlowable(width="100%", thickness=2, color=BRAND_PRIMARY, spaceBefore=0, spaceAfter=4))
    
    # Patient Info
    extra = {
        "Attending Doctor": f"Dr. {doctor.get('name', 'N/A')}",
        "Admission Date": admit_date.strftime("%d %b %Y") if isinstance(admit_date, datetime) else str(admit_date),
        "Discharge Date": discharge_date.strftime("%d %b %Y") if isinstance(discharge_date, datetime) else str(discharge_date),
    }
    
    if admission.get("room_number"):
        extra["Room / Bed"] = f"{admission.get('room_number', '')} ({admission.get('room_type', '')})"
    
    # Calculate length of stay
    if isinstance(admit_date, datetime) and isinstance(discharge_date, datetime):
        los = (discharge_date - admit_date).days
        extra["Length of Stay"] = f"{los} day{'s' if los != 1 else ''}"
    
    story.append(build_patient_info_table(patient, styles, extra))
    story.append(Spacer(1, 6 * mm))
    
    # Diagnosis
    diagnosis = admission.get("diagnosis", admission.get("primary_diagnosis", ""))
    if diagnosis:
        story.append(Paragraph("FINAL DIAGNOSIS", styles['SectionTitle']))
        if isinstance(diagnosis, list):
            for d in diagnosis:
                story.append(Paragraph(f"• {d}", styles['FieldValue']))
        else:
            story.append(Paragraph(str(diagnosis), styles['FieldValue']))
        story.append(Spacer(1, 4 * mm))
    
    # History of Present Illness
    history = admission.get("history", admission.get("presenting_complaints", ""))
    if history:
        story.append(Paragraph("HISTORY OF PRESENT ILLNESS", styles['SectionTitle']))
        story.append(Paragraph(str(history), styles['FieldValue']))
        story.append(Spacer(1, 4 * mm))
    
    # Treatment Given
    treatment = admission.get("treatment_given", admission.get("treatment_summary", ""))
    if treatment:
        story.append(Paragraph("TREATMENT GIVEN", styles['SectionTitle']))
        story.append(Paragraph(str(treatment), styles['FieldValue']))
        story.append(Spacer(1, 4 * mm))
    
    # Condition at Discharge
    condition = admission.get("condition_at_discharge", "")
    if condition:
        story.append(Paragraph("CONDITION AT DISCHARGE", styles['SectionTitle']))
        story.append(Paragraph(str(condition), styles['FieldValue']))
        story.append(Spacer(1, 4 * mm))
    
    # Discharge Medications
    if medications:
        story.append(Paragraph("DISCHARGE MEDICATIONS", styles['SectionTitle']))
        med_header = [
            Paragraph("<b>#</b>", styles['FieldLabel']),
            Paragraph("<b>Medicine</b>", styles['FieldLabel']),
            Paragraph("<b>Dosage</b>", styles['FieldLabel']),
            Paragraph("<b>Frequency</b>", styles['FieldLabel']),
            Paragraph("<b>Duration</b>", styles['FieldLabel']),
        ]
        med_data = [med_header]
        for idx, med in enumerate(medications, 1):
            med_data.append([
                Paragraph(str(idx), styles['FieldValue']),
                Paragraph(f"<b>{med.get('name', med.get('drug_name', 'N/A'))}</b>", styles['FieldValue']),
                Paragraph(med.get("dosage", "N/A"), styles['FieldValue']),
                Paragraph(med.get("frequency", "N/A"), styles['FieldValue']),
                Paragraph(med.get("duration", "N/A"), styles['FieldValue']),
            ])
        
        col_widths = [PAGE_WIDTH * 0.05, PAGE_WIDTH * 0.3, PAGE_WIDTH * 0.18, PAGE_WIDTH * 0.2, PAGE_WIDTH * 0.15]
        med_table = Table(med_data, colWidths=col_widths)
        med_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), BRAND_PRIMARY),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ('INNERGRID', (0, 1), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
        ]))
        story.append(med_table)
        story.append(Spacer(1, 4 * mm))
    
    # Follow-up Advice
    follow_up = admission.get("follow_up", admission.get("follow_up_instructions", ""))
    if follow_up:
        story.append(Paragraph("FOLLOW-UP INSTRUCTIONS", styles['SectionTitle']))
        story.append(Paragraph(str(follow_up), styles['FieldValue']))
        story.append(Spacer(1, 4 * mm))
    
    # Diet & Lifestyle Advice
    diet = admission.get("diet_advice", "")
    if diet:
        story.append(Paragraph("DIET & LIFESTYLE ADVICE", styles['SectionTitle']))
        story.append(Paragraph(str(diet), styles['FieldValue']))
        story.append(Spacer(1, 4 * mm))
    
    # QR Code
    qr_data = f"{base_url}/api/ipd/admissions/{admission_id}/verify" if base_url else f"DS:{admission_id}"
    qr_img = generate_qr_image(qr_data, size=55)
    qr_row = Table(
        [[qr_img, Paragraph(f"Admission ID: {admission_id}<br/>Scan to verify discharge summary.", styles['SmallText'])]],
        colWidths=[65, PAGE_WIDTH * 0.5]
    )
    qr_row.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('LEFTPADDING', (1, 0), (1, 0), 10)]))
    story.append(qr_row)
    
    doc.build(story, onFirstPage=lambda c, d: build_footer(c, d, hospital_name),
              onLaterPages=lambda c, d: build_footer(c, d, hospital_name))
    
    return buffer.getvalue()
