"""
PDF generation service using ReportLab.

Generates clinic-branded PDFs for:
  - Prescriptions
  - Invoices (GST-compliant)
  - Encounter summaries
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any


# ---------------------------------------------------------------------------
# Data classes (plain, no ORM dependency)
# ---------------------------------------------------------------------------

@dataclass
class ClinicInfo:
    name: str
    address: str = ""
    phone: str = ""
    email: str = ""
    gstin: str = ""
    registration_number: str = ""
    logo_url: str | None = None


@dataclass
class DoctorInfo:
    full_name: str
    registration_number: str = ""
    qualifications: list[str] | None = None
    specializations: list[str] | None = None


@dataclass
class PatientInfo:
    full_name: str
    uhid: str
    age: str = ""
    gender: str = ""
    phone: str = ""
    abha_number: str | None = None


@dataclass
class PrescriptionItem:
    medicine_name: str
    dosage: str = ""
    frequency: str = ""
    duration: str = ""
    meal_relation: str = ""
    instructions: str = ""


@dataclass
class InvoiceLineItem:
    description: str
    quantity: float
    unit_price: float
    discount: float
    tax_rate: float
    tax_amount: float
    total: float


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_rl():
    """Lazy import ReportLab to keep module loadable even without it."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            HRFlowable,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
        return colors, A4, getSampleStyleSheet, ParagraphStyle, mm, HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError as e:
        raise RuntimeError("ReportLab is required for PDF generation. Install it: pip install reportlab") from e


def _base_doc(buffer: io.BytesIO, title: str):
    colors, A4, *_ = _get_rl()
    _, _, _, _, mm, _, _, SimpleDocTemplate, _, _, _ = _get_rl()
    return SimpleDocTemplate(
        buffer,
        pagesize=A4,
        title=title,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
    )


def _header_table(clinic: ClinicInfo, doctor: DoctorInfo | None, doc_type: str, ref: str, ref_date: str):
    colors, A4, getSampleStyleSheet, ParagraphStyle, mm, HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle = _get_rl()
    styles = getSampleStyleSheet()

    clinic_lines = [f"<b>{clinic.name}</b>"]
    if clinic.address:
        clinic_lines.append(clinic.address)
    if clinic.phone:
        clinic_lines.append(f"Phone: {clinic.phone}")
    if clinic.gstin:
        clinic_lines.append(f"GSTIN: {clinic.gstin}")

    right_lines = [f"<b>{doc_type}</b>"]
    right_lines.append(f"Ref: {ref}")
    right_lines.append(f"Date: {ref_date}")
    if doctor:
        right_lines.append(f"Dr. {doctor.full_name}")
        if doctor.registration_number:
            right_lines.append(f"Reg. No: {doctor.registration_number}")
        if doctor.qualifications:
            right_lines.append(", ".join(doctor.qualifications))

    left_para = Paragraph("<br/>".join(clinic_lines), styles["Normal"])
    right_para = Paragraph("<br/>".join(right_lines), ParagraphStyle("right", parent=styles["Normal"], alignment=2))

    t = Table([[left_para, right_para]], colWidths=["60%", "40%"])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def _patient_row(patient: PatientInfo):
    colors, A4, getSampleStyleSheet, ParagraphStyle, mm, HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle = _get_rl()
    styles = getSampleStyleSheet()

    info = [
        f"<b>Patient:</b> {patient.full_name}",
        f"<b>UHID:</b> {patient.uhid}",
    ]
    if patient.age:
        info.append(f"<b>Age/Sex:</b> {patient.age} / {patient.gender}")
    if patient.phone:
        info.append(f"<b>Phone:</b> {patient.phone}")
    if patient.abha_number:
        info.append(f"<b>ABHA:</b> {patient.abha_number}")

    para = Paragraph("   |   ".join(info), styles["Normal"])
    t = Table([[para]])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return t


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_prescription_pdf(
    *,
    clinic: ClinicInfo,
    doctor: DoctorInfo,
    patient: PatientInfo,
    prescription_id: str,
    prescription_date: date,
    items: list[PrescriptionItem],
    diagnosis_summary: str | None = None,
    notes: str | None = None,
) -> bytes:
    """Return PDF bytes for a prescription."""
    colors, A4, getSampleStyleSheet, ParagraphStyle, mm, HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle = _get_rl()
    styles = getSampleStyleSheet()
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
    )

    elements: list[Any] = []

    # Header
    elements.append(_header_table(
        clinic, doctor,
        "PRESCRIPTION",
        prescription_id[:8].upper(),
        prescription_date.strftime("%d %b %Y"),
    ))
    elements.append(Spacer(1, 4 * mm))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#E2E8F0")))
    elements.append(Spacer(1, 3 * mm))

    # Patient info
    elements.append(_patient_row(patient))
    elements.append(Spacer(1, 4 * mm))

    # Diagnosis
    if diagnosis_summary:
        elements.append(Paragraph(f"<b>Diagnosis:</b> {diagnosis_summary}", styles["Normal"]))
        elements.append(Spacer(1, 3 * mm))

    # Medicines table
    header_style = ParagraphStyle("th", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=8)
    cell_style = ParagraphStyle("td", parent=styles["Normal"], fontSize=8)

    table_data = [[
        Paragraph("Medicine", header_style),
        Paragraph("Dosage", header_style),
        Paragraph("Frequency", header_style),
        Paragraph("Duration", header_style),
        Paragraph("Instructions", header_style),
    ]]

    freq_labels = {
        "OD": "Once daily", "BD": "Twice daily", "TDS": "Thrice daily",
        "QID": "Four times", "SOS": "As needed", "HS": "At bedtime",
        "STAT": "Immediately", "OW": "Once a week",
    }
    meal_labels = {
        "before_food": "Before food", "after_food": "After food",
        "with_food": "With food", "empty_stomach": "Empty stomach",
    }

    for item in items:
        instr_parts = []
        if item.meal_relation:
            instr_parts.append(meal_labels.get(item.meal_relation, item.meal_relation))
        if item.instructions:
            instr_parts.append(item.instructions)
        table_data.append([
            Paragraph(item.medicine_name, cell_style),
            Paragraph(item.dosage or "—", cell_style),
            Paragraph(freq_labels.get(item.frequency, item.frequency or "—"), cell_style),
            Paragraph(f"{item.duration} days" if item.duration else "—", cell_style),
            Paragraph(", ".join(instr_parts) or "—", cell_style),
        ])

    med_table = Table(table_data, colWidths=["30%", "12%", "18%", "12%", "28%"])
    med_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A5F")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(med_table)
    elements.append(Spacer(1, 4 * mm))

    if notes:
        elements.append(Paragraph(f"<b>Notes:</b> {notes}", styles["Normal"]))
        elements.append(Spacer(1, 3 * mm))

    # Footer
    elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#E2E8F0")))
    elements.append(Spacer(1, 3 * mm))
    elements.append(Paragraph(
        f"<b>Dr. {doctor.full_name}</b>  |  Reg. No: {doctor.registration_number}",
        ParagraphStyle("footer_sig", parent=styles["Normal"], alignment=2),
    ))
    elements.append(Paragraph(
        "This prescription is computer generated and valid without signature.",
        ParagraphStyle("footer_note", parent=styles["Normal"], fontSize=7, textColor=colors.HexColor("#94A3B8"), alignment=1),
    ))

    doc.build(elements)
    return buffer.getvalue()


def generate_invoice_pdf(
    *,
    clinic: ClinicInfo,
    patient: PatientInfo,
    invoice_number: str,
    invoice_date: date,
    line_items: list[InvoiceLineItem],
    subtotal: float,
    discount_amount: float,
    cgst_amount: float,
    sgst_amount: float,
    igst_amount: float,
    total_amount: float,
    paid_amount: float,
    outstanding_amount: float,
    notes: str | None = None,
) -> bytes:
    """Return PDF bytes for a GST-compliant invoice."""
    colors, A4, getSampleStyleSheet, ParagraphStyle, mm, HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle = _get_rl()
    styles = getSampleStyleSheet()
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
    )

    elements: list[Any] = []

    elements.append(_header_table(
        clinic, None,
        "TAX INVOICE",
        invoice_number,
        invoice_date.strftime("%d %b %Y"),
    ))
    elements.append(Spacer(1, 4 * mm))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#E2E8F0")))
    elements.append(Spacer(1, 3 * mm))
    elements.append(_patient_row(patient))
    elements.append(Spacer(1, 4 * mm))

    # Line items table
    header_style = ParagraphStyle("th", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=8)
    cell_style = ParagraphStyle("td", parent=styles["Normal"], fontSize=8)

    def fmt(v: float) -> str:
        return f"₹{v:,.2f}"

    table_data = [[
        Paragraph("#", header_style),
        Paragraph("Description", header_style),
        Paragraph("Qty", header_style),
        Paragraph("Rate", header_style),
        Paragraph("Discount", header_style),
        Paragraph("Tax", header_style),
        Paragraph("Amount", header_style),
    ]]
    for i, item in enumerate(line_items, 1):
        table_data.append([
            Paragraph(str(i), cell_style),
            Paragraph(item.description, cell_style),
            Paragraph(str(item.quantity), cell_style),
            Paragraph(fmt(item.unit_price), cell_style),
            Paragraph(fmt(item.discount), cell_style),
            Paragraph(f"{item.tax_rate:.0f}%", cell_style),
            Paragraph(fmt(item.total), cell_style),
        ])

    line_table = Table(table_data, colWidths=["5%", "35%", "8%", "13%", "13%", "10%", "16%"])
    line_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A5F")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(line_table)
    elements.append(Spacer(1, 4 * mm))

    # Totals block (right-aligned)
    summary_style = ParagraphStyle("sum", parent=styles["Normal"], fontSize=9)
    bold_style = ParagraphStyle("sumb", parent=styles["Normal"], fontSize=10, fontName="Helvetica-Bold")

    totals = [
        ["Subtotal:", fmt(subtotal)],
    ]
    if discount_amount:
        totals.append(["Discount:", f"- {fmt(discount_amount)}"])
    if cgst_amount:
        totals.append(["CGST:", fmt(cgst_amount)])
    if sgst_amount:
        totals.append(["SGST:", fmt(sgst_amount)])
    if igst_amount:
        totals.append(["IGST:", fmt(igst_amount)])
    totals.append(["Total Amount:", fmt(total_amount)])
    if paid_amount:
        totals.append(["Paid:", fmt(paid_amount)])
    totals.append(["Outstanding:", fmt(outstanding_amount)])

    totals_table_data = [[Paragraph(r, summary_style), Paragraph(v, bold_style if r.startswith("Total") or r.startswith("Outstanding") else summary_style)] for r, v in totals]
    totals_table = Table(totals_table_data, colWidths=["70%", "30%"])
    totals_table.setStyle(TableStyle([
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LINEABOVE", (0, -1), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
    ]))
    elements.append(totals_table)

    if notes:
        elements.append(Spacer(1, 3 * mm))
        elements.append(Paragraph(f"<b>Notes:</b> {notes}", styles["Normal"]))

    # Footer
    elements.append(Spacer(1, 4 * mm))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#E2E8F0")))
    elements.append(Spacer(1, 2 * mm))
    elements.append(Paragraph(
        "This is a computer-generated invoice and does not require a physical signature.",
        ParagraphStyle("footer", parent=styles["Normal"], fontSize=7, textColor=colors.HexColor("#94A3B8"), alignment=1),
    ))

    doc.build(elements)
    return buffer.getvalue()


def generate_encounter_summary_pdf(
    *,
    clinic: ClinicInfo,
    doctor: DoctorInfo,
    patient: PatientInfo,
    encounter_id: str,
    encounter_date: datetime,
    soap: dict[str, str | None],
    vitals: dict[str, Any] | None = None,
    diagnoses: list[str] | None = None,
) -> bytes:
    """Return PDF bytes for a clinical encounter summary."""
    colors, A4, getSampleStyleSheet, ParagraphStyle, mm, HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle = _get_rl()
    styles = getSampleStyleSheet()
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
    )

    elements: list[Any] = []

    elements.append(_header_table(
        clinic, doctor,
        "ENCOUNTER SUMMARY",
        encounter_id[:8].upper(),
        encounter_date.strftime("%d %b %Y  %H:%M"),
    ))
    elements.append(Spacer(1, 4 * mm))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#E2E8F0")))
    elements.append(Spacer(1, 3 * mm))
    elements.append(_patient_row(patient))
    elements.append(Spacer(1, 4 * mm))

    section_title = ParagraphStyle("sec_title", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=9, textColor=colors.HexColor("#1E3A5F"), spaceBefore=6, spaceAfter=2)
    body = ParagraphStyle("body", parent=styles["Normal"], fontSize=8.5)

    soap_labels = {
        "chief_complaint": "Chief Complaint",
        "history_of_present_illness": "History of Present Illness",
        "past_medical_history": "Past Medical History",
        "family_history": "Family History",
        "social_history": "Social History",
        "general_examination": "General Examination",
        "systemic_examination": "Systemic Examination",
        "clinical_impression": "Clinical Impression",
        "treatment_plan": "Treatment Plan",
        "follow_up_instructions": "Follow-up Instructions",
        "referral_to": "Referral",
    }

    for key, label in soap_labels.items():
        value = soap.get(key)
        if value:
            elements.append(Paragraph(label, section_title))
            elements.append(Paragraph(value, body))

    # Vitals
    if vitals:
        elements.append(Paragraph("Vitals", section_title))
        vital_labels = {
            "systolic_bp": "BP (sys)", "diastolic_bp": "BP (dia)",
            "pulse_rate": "Pulse", "temperature": "Temp (°C)",
            "spo2": "SpO2 (%)", "weight_kg": "Weight (kg)", "height_cm": "Height (cm)",
        }
        vital_parts = [f"{lbl}: {vitals[k]}" for k, lbl in vital_labels.items() if vitals.get(k)]
        if vital_parts:
            elements.append(Paragraph("   |   ".join(vital_parts), body))

    # Diagnoses
    if diagnoses:
        elements.append(Paragraph("Diagnoses", section_title))
        for d in diagnoses:
            elements.append(Paragraph(f"• {d}", body))

    # Footer
    elements.append(Spacer(1, 6 * mm))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#E2E8F0")))
    elements.append(Spacer(1, 2 * mm))
    elements.append(Paragraph(
        f"<b>Dr. {doctor.full_name}</b>  |  {doctor.registration_number}",
        ParagraphStyle("sig", parent=styles["Normal"], alignment=2, fontSize=8),
    ))

    doc.build(elements)
    return buffer.getvalue()
