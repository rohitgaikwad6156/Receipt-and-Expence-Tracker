import json
import re
import smtplib
import urllib.parse
from email.mime.text import MIMEText

def clean_whatsapp_text(text: str) -> str:
    """Collapses whitespace/newlines for WhatsApp delivery, capping at 1500 chars."""
    if not text:
        return "No expense summary available."
    cleaned = " ".join(text.split())
    return cleaned[:1500] + "..." if len(cleaned) > 1500 else cleaned

def clean_phone_number(number: str) -> str:
    """Normalizes phone numbers, stripping spaces/dashes and ensuring leading plus."""
    digits = re.sub(r"[^\d+]", "", str(number).strip())
    if digits and not digits.startswith("+"):
        digits = f"+{digits}"
    return digits

def generate_whatsapp_web_url(to_number: str, text: str) -> str:
    """Generates a direct WhatsApp Click-to-Chat URL."""
    clean_num = re.sub(r"\D", "", clean_phone_number(to_number))
    encoded_text = urllib.parse.quote(text)
    if clean_num:
        return f"https://wa.me/{clean_num}?text={encoded_text}"
    return f"https://api.whatsapp.com/send?text={encoded_text}"

def generate_mailto_url(to_address: str, subject: str, body: str) -> str:
    """Generates a direct mailto URL."""
    enc_subject = urllib.parse.quote(subject)
    enc_body = urllib.parse.quote(body)
    return f"mailto:{to_address}?subject={enc_subject}&body={enc_body}"

def generate_gmail_web_url(to_address: str, subject: str, body: str) -> str:
    """Generates a direct Gmail Web Compose URL (opens Gmail with recipient, subject, and body pre-filled)."""
    enc_to = urllib.parse.quote(to_address)
    enc_su = urllib.parse.quote(subject)
    enc_body = urllib.parse.quote(body)
    return f"https://mail.google.com/mail/?view=cm&fs=1&to={enc_to}&su={enc_su}&body={enc_body}"


def send_whatsapp(
    to_number: str,
    user_name: str,
    summary: str,
    account_sid: str,
    auth_token: str,
    from_number: str,
    content_sid: str = "",
) -> tuple[bool, str]:
    """
    Sends an expense summary to a WhatsApp number via Twilio.
    Supports Twilio Content Template SID (business-initiated) or direct body text.
    """
    if not account_sid or not auth_token:
        return False, "Twilio Account SID and Auth Token are required in secrets.toml."
    
    clean_to = clean_phone_number(to_number)
    if not clean_to or len(clean_to) < 8:
        return False, f"Invalid destination phone number: '{to_number}'. Include country code (e.g. +91XXXXXXXXXX)."

    try:
        from twilio.rest import Client as TwilioClient
        client = TwilioClient(account_sid.strip(), auth_token.strip())
        
        formatted_to = f"whatsapp:{clean_to}" if not clean_to.startswith("whatsapp:") else clean_to
        formatted_from = from_number.strip()
        if not formatted_from.startswith("whatsapp:"):
            formatted_from = f"whatsapp:{formatted_from}"

        # 1. Try sending with Content Template SID if provided
        if content_sid and content_sid.strip():
            try:
                content_variables = json.dumps(
                    {"1": user_name, "2": clean_whatsapp_text(summary)},
                    ensure_ascii=False,
                )
                message = client.messages.create(
                    from_=formatted_from,
                    to=formatted_to,
                    content_sid=content_sid.strip(),
                    content_variables=content_variables,
                )
                return True, f"Message queued via Twilio Template (SID: {message.sid})"
            except Exception as template_err:
                err_str = str(template_err)
                # If Content Template fails on a trial account or requires body, try direct body fallback
                if "401" in err_str or "Trial account" in err_str or "400" in err_str:
                    pass
                else:
                    raise template_err

        # 2. Direct body message (standard for joined sandbox sessions)
        body_text = f"🧾 Hi {user_name}! Here is your ReceiptWise expense summary:\n\n{summary}"
        message = client.messages.create(
            from_=formatted_from,
            to=formatted_to,
            body=body_text[:1600],
        )
        return True, f"Message sent via Twilio (SID: {message.sid})"

    except Exception as error:
        err_msg = str(error)
        if "422" in err_msg or "verified recipient" in err_msg:
            return False, (
                f"Twilio Trial Restriction: The recipient {clean_to} is not verified in your Twilio Console. "
                "Twilio trial accounts require either: "
                "(1) Adding this number under Twilio Console > Phone Numbers > Manage > Verified Caller IDs, or "
                "(2) Sending your sandbox join message (e.g. 'join <code>') from WhatsApp to +1 415 523 8886."
            )
        if "400" in err_msg and "ContentSid Required" in err_msg:
            return False, "Twilio ContentSid is required for this WhatsApp sender. Please check TWILIO_CONTENT_SID."
        return False, f"Twilio WhatsApp error: {err_msg}"

def send_email(
    to_address: str,
    subject: str,
    body: str,
    gmail_address: str,
    app_password: str,
) -> tuple[bool, str]:
    """
    Sends an expense report email via Gmail SMTP (Option B in workshop guide).
    Uses a Google App Password for free, third-party-free delivery.
    Supports both SSL (port 465) and STARTTLS (port 587).
    """
    if not gmail_address or not app_password:
        return False, "Gmail address and App Password must be configured in secrets.toml."
    if not to_address or "@" not in to_address or "\n" in to_address:
        return False, "Invalid recipient email address."

    cleaned_password = app_password.replace(" ", "").strip()
    
    # Check for common mistake: regular account password instead of 16-char app password
    if len(cleaned_password) != 16 or any(c in cleaned_password for c in "@!#$%^&*()"):
        warning_hint = (
            " (Note: Google requires a 16-character App Password generated at "
            "https://myaccount.google.com/apppasswords, not your personal Gmail password)."
        )
    else:
        warning_hint = ""

    message = MIMEText(body, "plain", "utf-8")
    message["Subject"] = subject
    message["From"] = gmail_address.strip()
    message["To"] = to_address.strip()

    # Try port 465 (SSL) first with quick timeout
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=3) as server:
            server.login(gmail_address.strip(), cleaned_password)
            server.send_message(message)
        return True, "Email sent successfully via SSL (port 465)"
    except Exception as ssl_err:
        # Fallback to port 587 (STARTTLS)
        try:
            with smtplib.SMTP("smtp.gmail.com", 587, timeout=3) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(gmail_address.strip(), cleaned_password)
                server.send_message(message)
            return True, "Email sent successfully via TLS (port 587)"
        except Exception as tls_err:
            return False, f"SMTP Error: {tls_err}{warning_hint}. Local Wi-Fi/ISP blocks SMTP ports 465/587. Click '📧 Open in Gmail Web' below to send instantly via browser!"

