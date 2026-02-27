from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition
import base64
import os
from datetime import datetime

def get_hebrew_year():
    return datetime.now().year + 3760

def send_dream_email(to_email: str, name: str, report: dict, pdf_bytes: bytes, referral_code: str):
    sg = SendGridAPIClient(os.getenv('SENDGRID_API_KEY'))
    base_url = os.getenv('FRONTEND_URL', 'https://dreamdecode.app')
    share_link = f"{base_url}/gift?code={referral_code}&from={name.replace(' ', '-')}"
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,600;1,400&family=Cinzel:wght@400;700&display=swap" rel="stylesheet">
        <style>
            body {{ font-family: 'Cormorant Garamond', Georgia, serif; color: #2c1810; background: #faf8f3; margin: 0; padding: 0; line-height: 1.6; }}
            .container {{ max-width: 600px; margin: 0 auto; background: #ffffff; }}
            .header {{ text-align: center; background: #1a1a2e; padding: 40px 20px; color: #d4af37; }}
            h1 {{ font-family: 'Cinzel', serif; font-size: 28px; letter-spacing: 2px; margin: 0; color: #d4af37; }}
            .content {{ padding: 40px 30px; background: #faf8f3; }}
            .preview-box {{ background: white; border-left: 4px solid #d4af37; padding: 20px; margin: 20px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }}
            .preview-box h3 {{ font-family: 'Cinzel', serif; color: #1a1a2e; margin-top: 0; }}
            .scripture {{ background: #f4f1ea; padding: 20px; margin: 25px 0; text-align: center; border: 1px solid #d4af37; font-style: italic; }}
            .blessing-box {{ background: linear-gradient(135deg, #1a1a2e 0%, #2d2d44 100%); color: #d4af37; padding: 30px; margin: 30px 0; border-radius: 8px; text-align: center; border: 2px solid #d4af37; }}
            .blessing-box h3 {{ font-family: 'Cinzel', serif; margin-top: 0; font-size: 22px; color: #d4af37; }}
            .share-button {{ display: inline-block; background: #d4af37; color: #1a1a2e; padding: 15px 30px; text-decoration: none; border-radius: 4px; font-weight: bold; margin: 10px; font-family: 'Cinzel', serif; text-transform: uppercase; letter-spacing: 1px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }}
            .share-link {{ background: rgba(0,0,0,0.3); padding: 12px; border-radius: 4px; font-family: monospace; font-size: 14px; margin: 15px 0; color: #fff; word-break: break-all; }}
            .stats {{ background: rgba(212, 175, 55, 0.1); padding: 15px; border-radius: 4px; margin-top: 20px; border: 1px solid rgba(212, 175, 55, 0.3); }}
            .footer {{ text-align: center; padding: 30px; background: #1a1a2e; color: #666; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>The Revelation of {name}</h1>
                <div style="font-style: italic; color: #c9b037; margin-top: 10px;">Your Biblical Dream Interpretation Has Arrived</div>
            </div>
            
            <div class="content">
                <p style="font-size: 18px; color: #4a4a4a;">Dear {name},</p>
                
                <p style="font-size: 16px; color: #555;">
                    Your dream has been interpreted according to the ancient wisdom of Scripture. 
                    As Joseph said, <em>"Do not interpretations belong to God?"</em> (Genesis 40:8)
                </p>
                
                <div class="preview-box">
                    <h3>The Revelation</h3>
                    <p>{report['interpretations'][0]['meaning'][:200]}...</p>
                </div>
                
                <div class="preview-box">
                    <h3>The Action Step</h3>
                    <p>{report['interpretations'][2]['meaning'][:150]}...</p>
                </div>
                
                <div class="scripture">
                    <p style="margin: 0; font-size: 16px; color: #2c1810;">"{report['scripture']['text']}"</p>
                    <p style="margin: 10px 0 0 0; font-weight: bold; color: #d4af37; font-style: normal; font-family: 'Cinzel', serif;">{report['scripture']['reference']}</p>
                </div>
                
                <p style="text-align: center; color: #666; margin: 25px 0;">
                    Your complete revelation is attached as a PDF.<br>Keep it for your prayer and meditation.
                </p>
                
                <div class="blessing-box">
                    <h3>🕊️ Pass the Blessing Forward</h3>
                    <p><strong>"Freely you have received, freely give."</strong><br><span style="font-size: 13px; opacity: 0.8;">— Matthew 10:8</span></p>
                    <p>Has this revelation touched your spirit? Gift a <strong>50% discount</strong> on a dream interpretation to someone you love.</p>
                    
                    <a href="{share_link}" class="share-button">Gift a Revelation</a>
                    
                    <div style="margin: 20px 0;">
                        <p style="font-size: 14px; margin-bottom: 8px; color: #d4af37;">Or share this mystical link:</p>
                        <div class="share-link">{share_link}</div>
                    </div>
                    
                    <div class="stats">
                        <p style="margin: 0; font-size: 14px;">
                            Your Blessing Code: <strong style="color: #d4af37; font-size: 16px;">{referral_code}</strong><br>
                            <span style="font-size: 12px; opacity: 0.7;">Track how many visions you help unveil</span>
                        </p>
                    </div>
                </div>
                
                <p style="font-size: 14px; color: #888; border-top: 1px solid #ddd; padding-top: 20px; margin-top: 30px;">
                    <strong>A Prayer for Your Journey:</strong><br><em>{report['prayer'][:200]}...</em>
                </p>
            </div>
            
            <div class="footer">
                <p style="font-family: 'Cinzel', serif; color: #d4af37; font-size: 14px;">DreamDecode</p>
                <p>"In the last days, God says, I will pour out my Spirit on all people..." — Acts 2:17</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    encoded_pdf = base64.b64encode(pdf_bytes).decode()
    
    attachment = Attachment(
        FileContent(encoded_pdf),
        FileName(f"dream-revelation-{name.replace(' ', '-')}.pdf"),
        FileType('application/pdf'),
        Disposition('attachment')
    )
    
    message = Mail(
        from_email=os.getenv('FROM_EMAIL', 'revelations@dreamdecode.app'),
        to_emails=to_email,
        subject=f'🕊️ Your Dream Revelation: The Vision of {name}',
        html_content=html_content
    )
    message.attachment = attachment
    
    try:
        response = sg.send(message)
        print(f"Email sent to {to_email}, Status: {response.status_code}")
        return True
    except Exception as e:
        print(f"Email error: {str(e)}")
        return False

def send_referrer_notification(email: str, name: str, friend_name: str):
    sg = SendGridAPIClient(os.getenv('SENDGRID_API_KEY'))
    
    html = f"""
    <div style="font-family: 'Cormorant Garamond', serif; max-width: 600px; margin: 0 auto; background: #faf8f3; padding: 40px;">
        <div style="text-align: center; border-bottom: 3px double #d4af37; padding-bottom: 20px; margin-bottom: 30px;">
            <h1 style="font-family: 'Cinzel', serif; color: #1a1a2e;">A Blessing Has Been Passed</h1>
        </div>
        
        <p style="font-size: 18px; color: #2c1810;">Dear {name},</p>
        
        <p style="font-size: 16px; color: #555; line-height: 1.6;">
            <strong>{friend_name}</strong> has used your blessing code to receive their own dream revelation.
        </p>
        
        <div style="background: #1a1a2e; color: #d4af37; padding: 25px; border-radius: 8px; text-align: center; margin: 25px 0;">
            <p style="margin: 0; font-size: 18px; font-style: italic;">
                "He who waters will also be watered himself."
            </p>
            <p style="margin: 10px 0 0 0; font-size: 14px;">— Proverbs 11:25</p>
        </div>
        
        <div style="text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; color: #999; font-size: 12px;">
            DreamDecode | Pass the Blessing Forward
        </div>
    </div>
    """
    
    message = Mail(
        from_email=os.getenv('FROM_EMAIL', 'revelations@dreamdecode.app'),
        to_emails=email,
        subject=f'Someone Received Your Blessing, {name}',
        html_content=html
    )
    
    try:
        sg.send(message)
        return True
    except Exception as e:
        print(f"Referrer email error: {e}")
        return False
