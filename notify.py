import json
import smtplib
from email.mime.text import MIMEText

def clean_whatsapp_text(text: str) -> str:
    """Collapses whitespace/newlines for WhatsApp delivery, capping at 1500 chars."""
    if not text:
        return "No expense summary available."
    cleaned = " ".join(text.split())
    return cleaned[:1500] + "..." if len(cleaned) > 1500 else cleaned

def send_whatsapp(to_number: str, user_name: str, summary: str, account_sid: str, auth_token: str, from_number: str, content_sid: str = "") -> tuple[bool, str]:
    """
    Sends an expense summary to a WhatsApp number via Twilio.
    Supports Twilio Content Template SID (business-initiated) or direct body text.
    """
    if not account_sid or not auth_token:
        return False, "Twilio Account SID and Auth Token are required in secrets."
    
    try:
        from twilio.rest import Client as TwilioClient
        client = TwilioClient(account_sid, auth_token)
        
        # Ensure recipient is prefixed with whatsapp:
        formatted_to = to_number.strip()
        if not formatted_to.startswith("whatsapp:"):
            formatted_to = f"whatsapp:{formatted_to}"
            
        formatted_from = from_number.strip()
        if not formatted_from.startswith("whatsapp:"):
            formatted_from = f"whatsapp:{formatted_from}"

        if content_sid:
            content_variables = json.dumps(
                {"1": user_name, "2": clean_whatsapp_text(summary)},
                ensure_ascii=False
            )
            message = client.messages.create(
                from_=formatted_from,
                to=formatted_to,
                content_sid=content_sid,
                content_variables=content_variables,
            )
        else:
            # Fallback direct message (works in active 24h conversation sandbox)
            body_text = f"🧾 Hi {user_name}! Here is your ReceiptWise expense summary:\n\n{summary}"
            message = client.messages.create(
                from_=formatted_from,
                to=formatted_to,
                body=body_text[:1600],
            )
        return True, message.sid
    except Exception as error:
        return False, str(error)

def send_email(to_address: str, subject: str, body: str, gmail_address: str, app_password: str) -> tuple[bool, str]:
    """
    Sends an expense report email via Gmail SMTP (Option B in workshop guide).
    Uses a Google App Password for free, third-party-free delivery.
    Supports both SSL (port 465) and STARTTLS (port 587).
    """
    if not gmail_address or not app_password:
        return False, "Gmail address and App Password must be configured in secrets."
    if not to_address or "@" not in to_address or "\n" in to_address:
        return False, "Invalid recipient email address."

    cleaned_password = app_password.replace(" ", "").strip()
    
    message = MIMEText(body, "plain", "utf-8")
    message["Subject"] = subject
    message["From"] = gmail_address.strip()
    message["To"] = to_address.strip()

    # Try port 465 (SSL) first
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as server:
            server.login(gmail_address.strip(), cleaned_password)
            server.send_message(message)
        return True, "Email sent successfully via SSL (port 465)"
    except Exception as ssl_err:
        # Fallback to port 587 (STARTTLS)
        try:
            with smtplib.SMTP("smtp.gmail.com", 587, timeout=10) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(gmail_address.strip(), cleaned_password)
                server.send_message(message)
            return True, "Email sent successfully via TLS (port 587)"
        except Exception as tls_err:
            return False, f"SMTP connection failed: {tls_err} (Note: local ISP/firewalls may block outbound SMTP; this will work when deployed to Streamlit Cloud)"

