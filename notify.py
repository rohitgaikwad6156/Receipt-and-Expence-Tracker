from email.message import EmailMessage
import smtplib

def send_email(to_address, subject, body, gmail_address, app_password):
    if not all((to_address, gmail_address, app_password)):
        raise ValueError("Gmail credentials and recipient are required")
    if "\n" in to_address or "\r" in to_address or "@" not in to_address:
        raise ValueError("Invalid recipient address")
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = gmail_address
    msg["To"] = to_address
    msg.set_content(body)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as server:
        server.login(gmail_address, app_password)
        server.send_message(msg)
