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
    """Generate luxury PDF report using ReportLab"""
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
    elements.append(Paragraph(f"Biblical Dream Interpretation for {name}", styles['Heading2']))
    elements.append(Paragraph(f"Hebrew Year {get_hebrew_year()}", styles['Italic']))
    elements.append(Spacer(1, 0.2*inch))
    
    # Interpretations
    if 'interpretations' in report_data:
        for interp in report_data['interpretations']:
            elements.append(Paragraph(interp['title'], heading_style))
            elements.append(Paragraph(interp['meaning'], normal_style))
            elements.append(Spacer(1, 0.1*inch))
    
    # Scripture
    if 'scripture' in report_data:
        elements.append(Spacer(1, 0.2*inch))
        elements.append(Paragraph("Scriptural Foundation", heading_style))
        
        scripture = report_data['scripture']
        elements.append(Paragraph(f"<i>{scripture.get('text', '')}</i>", normal_style))
        elements.append(Paragraph(f"<b>{scripture.get('reference', '')}</b>", styles['Normal']))
        elements.append(Paragraph(scripture.get('context', ''), styles['Normal']))
    
    # Prayer
    if 'prayer' in report_data:
        elements.append(Spacer(1, 0.2*inch))
        elements.append(Paragraph("Prayer for Your Dream", heading_style))
        elements.append(Paragraph(report_data['prayer'], normal_style))
    
    # Footer
    elements.append(Spacer(1, 0.5*inch))
    elements.append(Paragraph(
        "<i>This interpretation is provided for spiritual guidance. Always seek confirmation through prayer and wise counsel.</i>",
        styles['Normal']
    ))
    
    # Build PDF
    doc.build(elements)
    pdf = buffer.getvalue()
    buffer.close()
    
    return pdf
