from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from io import BytesIO
import datetime

def get_hebrew_year():
    """Convert current Gregorian year to Hebrew year"""
    gregorian_year = datetime.datetime.now().year
    hebrew_year = gregorian_year + 3760
    return hebrew_year

def generate_dream_pdf(dream_text, interpretation, email):
    """Generate a luxury PDF report using ReportLab"""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=72,
        leftMargin=72,
        topMargin=72,
        bottomMargin=18
    )
    
    # Container for the 'Flowable' objects
    elements = []
    
    # Styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#D4AF37'),  # Gold color
        spaceAfter=30,
        alignment=1  # Center alignment
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=colors.HexColor('#2C1810'),  # Dark brown
        spaceAfter=12
    )
    
    body_style = ParagraphStyle(
        'CustomBody',
        parent=styles['BodyText'],
        fontSize=11,
        textColor=colors.HexColor('#3D2817'),
        spaceAfter=12,
        leading=16
    )
    
    # Hebrew year
    hebrew_year = get_hebrew_year()
    
    # Title
    elements.append(Paragraph("DreamDecode™ Biblical Report", title_style))
    elements.append(Spacer(1, 0.2*inch))
    
    # Subtitle with Hebrew year
    elements.append(Paragraph(f"Year {hebrew_year} Anno Mundi", heading_style))
    elements.append(Spacer(1, 0.3*inch))
    
    # Dream Section
    elements.append(Paragraph("THE DREAM", heading_style))
    dream_para = dream_text.replace('\n', '<br/>')
    elements.append(Paragraph(dream_para, body_style))
    elements.append(Spacer(1, 0.2*inch))
    
    # Interpretation Section
    elements.append(Paragraph("BIBLICAL INTERPRETATION", heading_style))
    interp_para = interpretation.replace('\n', '<br/>')
    elements.append(Paragraph(interp_para, body_style))
    elements.append(Spacer(1, 0.3*inch))
    
    # Footer
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.grey,
        alignment=1
    )
    elements.append(Paragraph(f"Prepared for: {email} | DreamDecode™ | www.dreamdecode.app", footer_style))
    
    # Build PDF
    doc.build(elements)
    
    # Get the value of the BytesIO buffer
    pdf = buffer.getvalue()
    buffer.close()
    
    return pdf
