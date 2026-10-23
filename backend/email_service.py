import os
import json
import base64
import requests

# ---------- Provider selection ----------
# Brevo is checked first (free tier: 300 emails/day, no credit card).
# SendGrid is the fallback (free tier: 100 emails/day).
# Set either BREVO_API_KEY or SENDGRID_API_KEY in Railway — the active
# provider is auto-detected. No other code change needed to switch.

FROM_NAME = "DreamDecode"

def _brevo_key():
    return os.getenv("BREVO_API_KEY")

def _sendgrid_key():
    return os.getenv("SENDGRID_API_KEY")

def email_provider():
    """Which email provider is active, based on which env key is set"""
    if _brevo_key():
        return "brevo"
    if _sendgrid_key():
        return "sendgrid"
    return None

def _from_email():
    return os.getenv("FROM_EMAIL", "askdave755@gmail.com")

# ---------- Low-level senders ----------

def _send_via_brevo(to_email, subject, html_content, pdf_bytes=None, pdf_name="dream-reflection.pdf"):
    """Send via Brevo (formerly Sendinblue) transactional API"""
    payload = {
        "sender": {"email": _from_email(), "name": FROM_NAME},
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": html_content
    }
    if pdf_bytes:
        payload["attachment"] = [{
            "content": base64.b64encode(pdf_bytes).decode(),
            "name": pdf_name
        }]
    try:
        r = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={
                "api-key": _brevo_key(),
                "Content-Type": "application/json",
                "Accept": "application/json"
            },
            data=json.dumps(payload),
            timeout=30
        )
        if r.status_code in (200, 201, 202):
            print(f"✅ Brevo email sent to {to_email}, status: {r.status_code}")
            return {"sent": True, "provider": "brevo", "status_code": r.status_code}
        print(f"❌ Brevo email failed to {to_email}: {r.status_code} | body: {r.text}")
        return {"sent": False, "provider": "brevo", "error": f"HTTP {r.status_code}", "provider_body": r.text}
    except Exception as e:
        print(f"❌ Brevo email exception to {to_email}: {e}")
        return {"sent": False, "provider": "brevo", "error": str(e)}

def _send_via_sendgrid(to_email, subject, html_content, pdf_bytes=None, pdf_name="dream-reflection.pdf"):
    """Send via SendGrid (legacy path)"""
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition
    
    sg = SendGridAPIClient(_sendgrid_key())
    message = Mail(
        from_email=_from_email(),
        to_emails=to_email,
        subject=subject,
        html_content=html_content
    )
    
    if pdf_bytes:
        encoded = base64.b64encode(pdf_bytes).decode()
        attachment = Attachment()
        attachment.file_content = FileContent(encoded)
        attachment.file_name = FileName(pdf_name)
        attachment.file_type = FileType("application/pdf")
        attachment.disposition = Disposition("attachment")
        message.add_attachment(attachment)
    
    try:
        response = sg.send(message)
        print(f"✅ SendGrid email sent to {to_email}, status: {response.status_code}")
        return {"sent": True, "provider": "sendgrid", "status_code": response.status_code}
    except Exception as e:
        body = getattr(e, 'body', None)
        print(f"❌ SendGrid email failed to {to_email}: {str(e)} | body: {body}")
        return {"sent": False, "provider": "sendgrid", "error": str(e), "provider_body": str(body)}

def send_email(to_email, subject, html_content, pdf_bytes=None, pdf_name="dream-reflection.pdf"):
    """Unified sender — routes to whichever provider is configured.
    Always returns a result dict so failures are visible, never silent."""
    provider = email_provider()
    if provider == "brevo":
        return _send_via_brevo(to_email, subject, html_content, pdf_bytes, pdf_name)
    if provider == "sendgrid":
        return _send_via_sendgrid(to_email, subject, html_content, pdf_bytes, pdf_name)
    print(f"⚠️ No email provider configured (set BREVO_API_KEY or SENDGRID_API_KEY) — skipping email to {to_email}")
    return {"sent": False, "error": "No email provider configured (BREVO_API_KEY or SENDGRID_API_KEY missing)"}

# ---------- DreamDecode emails ----------

def send_dream_email(to_email, name, report, pdf_bytes, referral_code):
    """Send dream interpretation email with PDF attachment"""
    if not email_provider():
        print(f"Skipping email to {to_email} - no email provider configured")
        return {"sent": False, "error": "No email provider configured"}
    
    display_name = (name or "").strip() or "Friend"

    # Build email content
    interpretations_html = ""
    if 'interpretations' in report:
        for interp in report['interpretations']:
            interpretations_html += f"""
            <h3 style="color: #D4AF37;">{interp['title']}</h3>
            <p>{interp['meaning']}</p>
            """

    questions_html = ""
    reflection_questions = report.get('reflection_questions') or []
    if reflection_questions:
        items = "".join(f"<li style='margin-bottom: 8px;'>{q}</li>" for q in reflection_questions)
        questions_html = f"""
        <h3 style="color: #D4AF37;">Questions for Personal Reflection</h3>
        <ol style="padding-left: 20px;">{items}</ol>
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
        <p><i>Possible meanings to weigh through the language of Scripture</i></p>
        {entries}
        """
    
    discernment_html = ""
    discernment = report.get('source_discernment')
    if discernment:
        discernment_html = f"""
        <h3 style="color: #D4AF37;">🕊️ Source Discernment</h3>
        <p>For prayerful discernment — this dream may flow from: <b>{discernment.get('source', '')}</b></p>
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
        <p><b>Daniel — The Interpreter of Visions</b><br>
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
    
    frontend_url = os.getenv("FRONTEND_URL", "https://dreamcode-2-0.vercel.app").rstrip("/")
    share_link = f"{frontend_url}/gift?code={referral_code}"

    discernment_note = (report.get('discernment_note') or "").strip()
    discernment_note_html = (
        f'<p style="background: #faf6ec; border-left: 3px solid #D4AF37; padding: 10px 14px;">'
        f"<b>A note on discernment:</b> {discernment_note}</p>"
        if discernment_note else ""
    )

    html_content = f"""
    <div style="font-family: Georgia, serif; max-width: 600px; margin: 0 auto; color: #333;">
        <h1 style="color: #D4AF37; text-align: center;">Your Dream Reflection Report</h1>
        <p>Hello {display_name},</p>
        <p>Your biblical dream reflection report is ready. Below is a summary, and your full report is attached as a PDF.</p>
        {discernment_note_html}
        
        <hr style="border: none; border-top: 1px solid #D4AF37; margin: 20px 0;">
        
        {interpretations_html}
        
        {questions_html}
        
        {symbol_dictionary_html}
        
        {discernment_html}
        
        {scripture_html}
        
        {anchor_html}
        
        {prayer_html}
        
        <hr style="border: none; border-top: 1px solid #D4AF37; margin: 20px 0;">
        
        <div style="background: #f9f9f9; padding: 20px; border-radius: 5px; margin: 20px 0;">
            <h3 style="color: #D4AF37; margin-top: 0;">🕊️ Share the Blessing</h3>
            <p>Share a free dream reflection preview with someone who would appreciate it:</p>
            <p><a href="{share_link}" style="color: #D4AF37; text-decoration: none; font-weight: bold;">{share_link}</a></p>
        </div>
        
        <p style="font-size: 12px; color: #666; margin-top: 30px;">
            <i>These reflections are prompts for personal discernment — not prophecy, not a definitive message from God, and not a substitute for Scripture, prayer, or pastoral counsel. "Test everything; hold fast what is good." — 1 Thessalonians 5:21</i>
        </p>
    </div>
    """
    
    return send_email(
        to_email,
        "Your Biblical Dream Reflection Report is Ready",
        html_content,
        pdf_bytes
    )

def send_test_email():
    """Diagnostic: send a test email to the app's own FROM_EMAIL via the
    active provider and report exactly what the provider said."""
    provider = email_provider()
    if not provider:
        return {"sent": False, "error": "No email provider configured (BREVO_API_KEY or SENDGRID_API_KEY missing)"}
    
    html_content = """
    <div style="font-family: Georgia, serif; max-width: 600px; margin: 0 auto; color: #333;">
        <h2 style="color: #D4AF37;">Email Pipeline Working</h2>
        <p>If you're reading this, the email provider accepted and delivered the message.</p>
        <p>The full report pipeline (interpretation + symbol dictionary + PDF) uses this same path.</p>
    </div>
    """
    
    result = send_email(
        _from_email(),
        "DreamDecode Email Diagnostic",
        html_content
    )
    result["provider"] = provider
    result["from_email"] = _from_email()
    result["to_email"] = _from_email()
    if result.get("sent"):
        result["note"] = "Provider accepted it for delivery — check the inbox (and spam folder)"
    return result

def send_referrer_notification(referrer_email, referrer_name, new_user_name):
    """Notify referrer that someone used their code"""
    if not email_provider():
        return

    referrer_display = (referrer_name or "").strip() or "Friend"
    new_user_display = (new_user_name or "").strip() or "Someone"

    html_content = f"""
    <div style="font-family: Georgia, serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #D4AF37;">Your Blessing is Spreading!</h2>
        <p>Hello {referrer_display},</p>
        <p>Great news! {new_user_display} has used your blessing code to receive their dream reflection report.</p>
        <p>"Freely you have received, freely give." — Matthew 10:8</p>
        <p>Your act of sharing continues to multiply blessings.</p>
    </div>
    """
    
    return send_email(
        referrer_email,
        "Someone Used Your DreamDecode Blessing Code",
        html_content
    )
