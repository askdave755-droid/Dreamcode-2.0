import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition
import base64

def get_sendgrid_client():
    """Initialize SendGrid client"""
    api_key = os.getenv("SENDGRID_API_KEY")
    if not api_key:
        print("⚠️ SENDGRID_API_KEY not set, emails will not be sent")
        return None
    return SendGridAPIClient(api_key)

def send_dream_email(to_email, name, report, pdf_bytes, referral_code):
    """Send dream interpretation email with PDF attachment"""
    sg = get_sendgrid_client()
    if not sg:
        print(f"Skipping email to {to_email} - SendGrid not configured")
        return
    
    # Build email content
    interpretations_html = ""
    if 'interpretations' in report:
        for interp in report['interpretations']:
            interpretations_html += f"""
            <h3 style="color: #D4AF37;">{interp['title']}</h3>
            <p>{interp['meaning']}</p>
            """
    
    scripture_html = ""
    if 'scripture' in report:
        scripture = report['scripture']
        scripture_html = f"""
        <h3 style="color: #D4AF37;">Scriptural Foundation</h3>
        <p><i>"{scripture.get('text', '')}"</i></p>
        <p><b>{scripture.get('reference', '')}</b></p>
        <p>{scripture.get('context', '')}</p>
        """
    
    prayer_html = ""
    if 'prayer' in report:
        prayer_html = f"""
        <h3 style="color: #D4AF37;">Prayer for Your Dream</h3>
        <p>{report['prayer']}</p>
        """
    
    share_link = f"https://dreamcode-2-0.vercel.app/gift?code={referral_code}&from={name.replace(' ', '-')}"
    
    html_content = f"""
    <div style="font-family: Georgia, serif; max-width: 600px; margin: 0 auto; color: #333;">
        <h1 style="color: #D4AF37; text-align: center;">Your Dream Revelation</h1>
        <p>Hello {name},</p>
        <p>Your biblical dream interpretation is ready. Below is a summary, and your full report is attached as a PDF.</p>
        
        <hr style="border: none; border-top: 1px solid #D4AF37; margin: 20px 0;">
        
        {interpretations_html}
        
        {scripture_html}
        
        {prayer_html}
        
        <hr style="border: none; border-top: 1px solid #D4AF37; margin: 20px 0;">
        
        <div style="background: #f9f9f9; padding: 20px; border-radius: 5px; margin: 20px 0;">
            <h3 style="color: #D4AF37; margin-top: 0;">🕊️ Share the Blessing</h3>
            <p>Pass on a 50% discount to someone who needs spiritual insight:</p>
            <p><a href="{share_link}" style="color: #D4AF37; text-decoration: none; font-weight: bold;">{share_link}</a></p>
        </div>
        
        <p style="font-size: 12px; color: #666; margin-top: 30px;">
            <i>This interpretation is provided for spiritual guidance. Always seek confirmation through prayer and wise counsel.</i>
        </p>
    </div>
    """
    
    message = Mail(
        from_email=os.getenv("FROM_EMAIL", "askdave755@gmail.com"),
        to_emails=to_email,
        subject="Your Biblical Dream Interpretation is Ready",
        html_content=html_content
    )
    
    # Attach PDF
    if pdf_bytes:
        encoded = base64.b64encode(pdf_bytes).decode()
        attachment = Attachment()
        attachment.file_content = FileContent(encoded)
        attachment.file_name = FileName("dream-revelation.pdf")
        attachment.file_type = FileType("application/pdf")
        attachment.disposition = Disposition("attachment")
        message.add_attachment(attachment)
    
    try:
        response = sg.send(message)
        print(f"✅ Email sent to {to_email}, status: {response.status_code}")
    except Exception as e:
        print(f"❌ Email failed to {to_email}: {str(e)}")

def send_referrer_notification(referrer_email, referrer_name, new_user_name):
    """Notify referrer that someone used their code"""
    sg = get_sendgrid_client()
    if not sg:
        return
    
    html_content = f"""
    <div style="font-family: Georgia, serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #D4AF37;">Your Blessing is Spreading!</h2>
        <p>Hello {referrer_name},</p>
        <p>Great news! {new_user_name} has used your blessing code to receive their dream interpretation.</p>
        <p>"Freely you have received, freely give." — Matthew 10:8</p>
        <p>Your act of sharing continues to multiply blessings.</p>
    </div>
    """
    
    message = Mail(
        from_email=os.getenv("FROM_EMAIL", "askdave755@gmail.com"),
        to_emails=referrer_email,
        subject="Someone Used Your DreamDecode Blessing Code",
        html_content=html_content
    )
    
    try:
        response = sg.send(message)
        print(f"✅ Referrer notification sent to {referrer_email}")
    except Exception as e:
        print(f"❌ Referrer notification failed: {str(e)}")
