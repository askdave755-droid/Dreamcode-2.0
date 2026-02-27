from jinja2 import Template
import weasyprint
from datetime import datetime

def get_hebrew_year():
    return datetime.now().year + 3760

def generate_dream_pdf(name: str, report: dict) -> bytes:
    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,600;1,400&family=Cinzel:wght@400;700&display=swap" rel="stylesheet">
        <style>
            body { 
                font-family: 'Cormorant Garamond', serif; 
                color: #2c1810; 
                background: #faf8f3; 
                padding: 50px;
                line-height: 1.6;
            }
            .header { 
                text-align: center; 
                border-bottom: 3px double #d4af37; 
                padding-bottom: 30px; 
                margin-bottom: 40px; 
            }
            h1 { 
                font-family: 'Cinzel', serif;
                color: #1a1a2e; 
                font-size: 32px; 
                letter-spacing: 3px;
                margin-bottom: 10px;
            }
            .subtitle { font-style: italic; color: #666; font-size: 16px; }
            .timestamp { 
                text-align: center; 
                font-family: 'Cinzel', serif;
                color: #666; 
                font-size: 12px; 
                margin-bottom: 30px; 
                letter-spacing: 2px; 
            }
            .interpretation { 
                background: white; 
                padding: 25px; 
                margin: 20px 0; 
                border-left: 5px solid #d4af37; 
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            }
            .interpretation h3 {
                font-family: 'Cinzel', serif;
                color: #1a1a2e;
                margin-top: 0;
            }
            .scripture { 
                font-style: italic; 
                background: #f4f1ea; 
                padding: 25px; 
                margin: 30px 0; 
                border-radius: 8px;
                text-align: center;
                border: 1px solid #d4af37;
            }
            .scripture-ref {
                font-weight: bold;
                font-family: 'Cinzel', serif;
                color: #d4af37;
                margin-top: 10px;
                display: block;
            }
            .prayer { 
                background: #1a1a2e; 
                color: #d4af37; 
                padding: 30px; 
                border-radius: 8px; 
                line-height: 1.8;
                font-size: 18px;
                text-align: center;
                margin-top: 30px;
            }
            .prayer h3 {
                color: #d4af37;
                font-family: 'Cinzel', serif;
                margin-top: 0;
                border-bottom: 1px solid #d4af37;
                padding-bottom: 10px;
                display: inline-block;
            }
            .footer {
                text-align: center;
                margin-top: 50px;
                font-size: 10px;
                color: #999;
                border-top: 1px solid #ddd;
                padding-top: 20px;
            }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>The Revelation of {{ name }}</h1>
            <div class="subtitle">A Biblical Interpretation</div>
        </div>
        
        <div class="timestamp">Interpreted on {{ date }} | Hebrew Year {{ hebrew_year }}</div>
        
        <div style="text-align: center; margin: 20px 0; font-style: italic;">
            "In the last days, God says, I will pour out my Spirit on all people..." — Acts 2:17
        </div>

        <h2 style="font-family: 'Cinzel', serif; color: #1a1a2e; border-bottom: 2px solid #d4af37; display: inline-block;">Three Revelations</h2>
        
        {% for interp in interpretations %}
        <div class="interpretation">
            <h3>{{ interp.title }}</h3>
            <p>{{ interp.meaning }}</p>
        </div>
        {% endfor %}
        
        <div class="scripture">
            <h3 style="font-family: 'Cinzel', serif; color: #1a1a2e;">Scriptural Anchor</h3>
            <p style="font-size: 18px; margin: 15px 0;">"{{ scripture.text }}"</p>
            <span class="scripture-ref">{{ scripture.reference }}</span>
            <p style="font-size: 14px; color: #666; margin-top: 10px;">{{ scripture.context }}</p>
        </div>
        
        <div class="prayer">
            <h3>A Prayer for Your Dream</h3>
            <p>{{ prayer }}</p>
        </div>
        
        <div class="footer">
            <p>"Do not interpretations belong to God?" — Genesis 40:8</p>
            <p><strong>DreamDecode</strong> | Biblical Dream Interpretation</p>
        </div>
    </body>
    </html>
    """
    
    template = Template(html_template)
    html_content = template.render(
        name=name,
        date=datetime.now().strftime("%B %d, %Y"),
        hebrew_year=get_hebrew_year(),
        interpretations=report['interpretations'],
        scripture=report['scripture'],
        prayer=report['prayer']
    )
    
    pdf = weasyprint.HTML(string=html_content).write_pdf()
    return pdf
