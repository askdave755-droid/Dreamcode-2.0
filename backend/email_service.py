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
    """Send dream interpretation email with PDF attachment.
    Returns a result dict so callers (and logs) can see exactly what SendGrid said."""
    sg = get_sendgrid_client()
    if not sg:
        print(f"Skipping email to {to_email} - SendGrid not configured")
        return {"sent": False, "error": "SENDGRID_API_KEY not set"}
    
    # Build email content
    interpretations_html = ""
    if 'interpretations' in report:
        for interp in report['interpretations']:
            interpretations_html += f"""
            <h3 style="color: #D4AF37;">{interp['title']}</h3>
            <p>{interp['meaning']}</p>
            """
    
    symbol_dictionary_html = ""
    symbol_dictionary = report.get('symbol_dictionary')
    if symbol_dictionary:
        entries = ""
        for entry in symbol_dictionary:
            entries += f"""
            <p style="margin-bottom: 12px;">
                <b style="color: #8B4513;">{entry.get('symbol', '').title()}</b> —
                {entry.get('biblical_meaning', '')}<br>
                <i style="color: #888;">{entry.get('scripture', '')}</i>
            </p>
            """
        symbol_dictionary_html = f"""
        <h3 style="color: #D4AF37;">Dream Symbol Dictionary</h3>
        <p><i>Every symbol decoded through the language of Scripture</i></p>
        {entries}
        """
    
    discernment_html = ""
    discernment = report.get('source_discernment')
    if discernment:
        discernment_html = f"""
        <h3 style="color: #D4AF37;">🕊️ Source Discernment</h3>
        <p>This dream most likely flows from: <b>{discernment.get('source', '')}</b></p>
        <p>{discernment.get('explanation', '')}</p>
        <p><b>Counsel:</b> {discernment.get('counsel', '')}</p>
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
    
    anchor_html = ""
    anchor = report.get('joseph_daniel_anchor')
    if anchor:
        joseph = anchor.get('joseph', {})
        daniel = anchor.get('daniel', {})
        anchor_html = f"""
        <h3 style="color: #D4AF37;">The Joseph & Daniel Anchor</h3>
        <p><b>Joseph — The Interpreter of Pharaoh's Dreams</b><br>
        <i>{joseph.get('reference', '')}</i><br>
        {joseph.get('connection', '')}<br>
        <b>Insight:</b> {joseph.get('insight', '')}</p>
        <p><b>Daniel — The Revealer of Mysteries</b><br>
        <i>{daniel.get('reference', '')}</i><br>
        {daniel.get('connection', '')}<br>
        <b>Insight:</b> {daniel.get('insight', '')}</p>
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
        
        {symbol_dictionary_html}
        
        {discernment_html}
        
        {scripture_html}
        
        {anchor_html}
        
        {prayer_html}
        
        <hr style="border: none; border-top: 1px solid #D4AF37; margin: 20px 0;">
        
        <div style="background: #f9f9f9; padding: 20px; border-radius: 5px; margin: 20px 0;">
            <h3 style="color: #D4AF37; margin-top: 0;">🕊️ Share the Blessing</h3>
            <p>Pass on the gift of free dream interpretation to someone who needs spiritual insight:</p>
            <p><a href="{share_link}" style="color: #D4AF37; text-decoration: none; font-weight: bold;">{share_link}</a></p>
        </div>
        
        <p style="font-size: 12px; color: #666; margin-top: 30px;">
            <i>This interpretation is provided for spiritual guidance. Always seek confirmation through prayer and wise counsel.</i>
        </p>
    </div>
    """
    
    from_email = os.getenv("FROM_EMAIL", "askdave755@gmail.com")
    
    message = Mail(
        from_email=from_email,
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
        return {"sent": True, "status_code": response.status_code}
    except Exception as e:
        # SendGrid errors carry the response body — that body is the real diagnosis
        body = getattr(e, 'body', None)
        print(f"❌ Email failed to {to_email}: {str(e)} | body: {body}")
        return {"sent": False, "error": str(e), "sendgrid_body": str(body)}

def send_test_email():
    """Diagnostic: send a test email to the app's own FROM_EMAIL and report
    exactly what SendGrid returned (status code or error body)."""
    sg = get_sendgrid_client()
    if not sg:
        return {"sent": False, "error": "SENDGRID_API_KEY not set"}
    
    from_email = os.getenv("FROM_EMAIL", "askdave755@gmail.com")
    
    message = Mail(
        from_email=from_email,
        to_emails=from_email,
        subject="DreamDecode Email Diagnostic",
        html_content="""
        <div style="font-family: Georgia, serif; max-width: 600px; margin: 0 auto; color: #333;">
            <h2 style="color: #D4AF37;">Email Pipeline Working</h2>
            <p>If you're reading this, SendGrid accepted and delivered the message.</p>
            <p>The full report pipeline (interpretation + symbol dictionary + PDF) uses this same path.</p>
        </div>
        """
    )
    
    try:
        response = sg.send(message)
        print(f"✅ Diagnostic email sent, status: {response.status_code}")
        return {
            "sent": True,
            "status_code": response.status_code,
            "from_email": from_email,
            "to_email": from_email,
            "note": "202 = SendGrid accepted it for delivery"
        }
    except Exception as e:
        body = getattr(e, 'body', None)
        print(f"❌ Diagnostic email failed: {str(e)} | body: {body}")
        return {
            "sent": False,
            "error": str(e),
            "sendgrid_body": str(body),
            "from_email": from_email
        }

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
        body = getattr(e, 'body', None)
        print(f"❌ Referrer notification failed: {str(e)} | body: {body}")
