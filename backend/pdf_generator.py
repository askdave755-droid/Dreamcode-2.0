from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from datetime import datetime
import io

def get_hebrew_year():
    """Calculate Hebrew year (approximate)"""
    gregorian_year = datetime.now().year
    hebrew_year = gregorian_year + 3760
    return hebrew_year

def generate_dream_pdf(name, report_data):
    """Generate luxury PDF report using ReportLab.

    name may be None (it is no longer collected up front).
    """
    display_name = (name or "").strip() or "Friend"
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=72,
        leftMargin=72,
        topMargin=72,
        bottomMargin=18
    )
    
    # Container for elements
    elements = []
    
    # Styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#D4AF37'),  # Gold
        spaceAfter=30,
        alignment=1  # Center
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=colors.HexColor('#8B4513'),  # Saddle brown
        spaceAfter=12
    )
    
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['BodyText'],
        fontSize=11,
        textColor=colors.HexColor('#2F4F4F'),
        spaceAfter=12
    )
    
    # Header
    elements.append(Paragraph("DreamDecode", title_style))
    elements.append(Paragraph("Biblical Dream Reflection Report", styles['Heading2']))
    elements.append(Paragraph(f"Prepared for {display_name} — Hebrew Year {get_hebrew_year()}", styles['Italic']))
    elements.append(Spacer(1, 0.2*inch))

    # Discernment note (when the report includes one)
    discernment_note = (report_data.get('discernment_note') or "").strip()
    if discernment_note:
        elements.append(Paragraph(
            f"<b>A note on discernment:</b> {discernment_note}",
            normal_style
        ))
        elements.append(Spacer(1, 0.1*inch))
    
    # Interpretations
    if 'interpretations' in report_data:
        for interp in report_data['interpretations']:
            elements.append(Paragraph(interp['title'], heading_style))
            elements.append(Paragraph(interp['meaning'], normal_style))
            elements.append(Spacer(1, 0.1*inch))

    # Reflection Questions
    reflection_questions = report_data.get('reflection_questions') or []
    if reflection_questions:
        elements.append(Spacer(1, 0.15*inch))
        elements.append(Paragraph("Questions for Personal Reflection", heading_style))
        for idx, question in enumerate(reflection_questions, start=1):
            elements.append(Paragraph(f"{idx}. {question}", normal_style))
    
    # Dream Symbol Dictionary
    symbol_dictionary = report_data.get('symbol_dictionary')
    if symbol_dictionary:
        elements.append(Spacer(1, 0.2*inch))
        elements.append(Paragraph("Dream Symbol Dictionary", heading_style))
        elements.append(Paragraph(
            "<i>Possible meanings to weigh through the language of Scripture</i>",
            normal_style
        ))
        elements.append(Spacer(1, 0.05*inch))
        for entry in symbol_dictionary:
            elements.append(Paragraph(
                f"<b>{entry.get('symbol', '').title()}</b> — {entry.get('biblical_meaning', '')}",
                normal_style
            ))
            elements.append(Paragraph(
                f"<i>{entry.get('scripture', '')}</i>",
                styles['Normal']
            ))
            elements.append(Spacer(1, 0.08*inch))
    
    # Source Discernment
    discernment = report_data.get('source_discernment')
    if discernment:
        elements.append(Spacer(1, 0.2*inch))
        elements.append(Paragraph("Source Discernment", heading_style))
        elements.append(Paragraph(
            f"For prayerful discernment — this dream may flow from: <b>{discernment.get('source', '')}</b>",
            normal_style
        ))
        elements.append(Paragraph(discernment.get('explanation', ''), normal_style))
        elements.append(Paragraph(
            f"<b>Counsel:</b> {discernment.get('counsel', '')}",
            normal_style
        ))
    
    # Scripture
    if 'scripture' in report_data:
        elements.append(Spacer(1, 0.2*inch))
        elements.append(Paragraph("Scriptural Anchor", heading_style))
        
        scripture = report_data['scripture']
        elements.append(Paragraph(f"<i>{scripture.get('text', '')}</i>", normal_style))
        elements.append(Paragraph(f"<b>{scripture.get('reference', '')}</b>", styles['Normal']))
        elements.append(Paragraph(scripture.get('context', ''), styles['Normal']))
    
    # Joseph & Daniel Anchor
    anchor = report_data.get('joseph_daniel_anchor')
    if anchor:
        elements.append(Spacer(1, 0.2*inch))
        elements.append(Paragraph("The Joseph & Daniel Anchor", heading_style))
        
        joseph = anchor.get('joseph', {})
        if joseph:
            elements.append(Paragraph("<b>Joseph — The Interpreter of Pharaoh's Dreams</b>", styles['Normal']))
            elements.append(Spacer(1, 0.05*inch))
            elements.append(Paragraph(f"<i>{joseph.get('reference', '')}</i>", normal_style))
            elements.append(Paragraph(joseph.get('connection', ''), normal_style))
            elements.append(Paragraph(f"<b>Insight:</b> {joseph.get('insight', '')}", normal_style))
            elements.append(Spacer(1, 0.1*inch))
        
        daniel = anchor.get('daniel', {})
        if daniel:
            elements.append(Paragraph("<b>Daniel — The Interpreter of Visions</b>", styles['Normal']))
            elements.append(Spacer(1, 0.05*inch))
            elements.append(Paragraph(f"<i>{daniel.get('reference', '')}</i>", normal_style))
            elements.append(Paragraph(daniel.get('connection', ''), normal_style))
            elements.append(Paragraph(f"<b>Insight:</b> {daniel.get('insight', '')}", normal_style))
    
    # Prayer
    if 'prayer' in report_data:
        elements.append(Spacer(1, 0.2*inch))
        elements.append(Paragraph("Prayer for Your Dream", heading_style))
        elements.append(Paragraph(report_data['prayer'], normal_style))
    
    # Footer
    elements.append(Spacer(1, 0.5*inch))
    elements.append(Paragraph(
        "<i>These reflections are prompts for personal discernment — not prophecy, not a definitive "
        "message from God, and not a substitute for Scripture, prayer, or pastoral counsel. "
        "\"Test everything; hold fast what is good.\" — 1 Thessalonians 5:21</i>",
        styles['Normal']
    ))
    
    # Build PDF
    doc.build(elements)
    pdf = buffer.getvalue()
    buffer.close()
    
    return pdf
