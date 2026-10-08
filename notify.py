import base64
import json
import os
import re
import socket
import urllib.parse
from email.mime.text import MIMEText

try:
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError:
    # Fallback placeholders if dependencies are still being resolved
    Credentials = None
    build = None
    HttpError = Exception
    RefreshError = Exception
    Request = None


# ------------------------------------------------------------------------------
# WhatsApp Helper Functions
# ------------------------------------------------------------------------------
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


# ------------------------------------------------------------------------------
# Google Gmail REST API (OAuth 2.0) Implementation
# ------------------------------------------------------------------------------
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
TOKEN_FILE_PATH = os.path.join(os.path.dirname(__file__), "gmail_token.json")


def _read_config(key: str, default: str = "") -> str:
    """Safely extracts a config value from Streamlit Secrets or Environment Variables."""
    val = ""
    try:
        import streamlit as st

        val = st.secrets.get(key, "")
    except Exception:
        pass
    if not val:
        val = os.getenv(key, default)
    return str(val).strip() if val else ""


def get_gmail_oauth_credentials(
    client_id: str = "",
    client_secret: str = "",
    refresh_token: str = "",
) -> tuple[Credentials | None, str]:
    """
    Constructs and refreshes Google OAuth 2.0 Credentials.
    Resolves credentials in order:
    1. Explicit parameters passed in.
    2. Environment variables / Streamlit Secrets: GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN.
    3. Local `gmail_token.json` file (generated by gmail_oauth_setup.py).
    """
    if Credentials is None:
        return None, "google-auth and google-api-python-client packages are not installed."

    c_id = client_id or _read_config("GMAIL_CLIENT_ID")
    c_secret = client_secret or _read_config("GMAIL_CLIENT_SECRET")
    r_token = refresh_token or _read_config("GMAIL_REFRESH_TOKEN")

    creds = None

    # Priority 1: Environment Variables / Secrets
    if c_id and c_secret and r_token:
        creds = Credentials(
            token=None,
            refresh_token=r_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=c_id,
            client_secret=c_secret,
            scopes=GMAIL_SCOPES,
        )
    # Priority 2: Local token file (for local development)
    elif os.path.exists(TOKEN_FILE_PATH):
        try:
            with open(TOKEN_FILE_PATH, "r", encoding="utf-8") as f:
                token_data = json.load(f)
            creds = Credentials(
                token=token_data.get("token"),
                refresh_token=token_data.get("refresh_token"),
                token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
                client_id=token_data.get("client_id"),
                client_secret=token_data.get("client_secret"),
                scopes=token_data.get("scopes", GMAIL_SCOPES),
            )
        except Exception as exc:
            return None, f"Failed to load local gmail_token.json: {exc}"

    if not creds:
        return None, (
            "Gmail OAuth 2.0 credentials not configured. Please run 'python gmail_oauth_setup.py' locally, "
            "or set GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, and GMAIL_REFRESH_TOKEN in your environment/secrets."
        )

    # Automatically refresh access token if needed
    try:
        if not creds.valid or creds.expired:
            creds.refresh(Request())
        return creds, "OK"
    except RefreshError:
        return None, (
            "Gmail API Authorization Error: OAuth refresh token is expired, revoked, or invalid. "
            "If your Google Cloud OAuth app is in 'Testing' mode, refresh tokens expire after 7 days. "
            "Please re-run 'python gmail_oauth_setup.py' to generate a fresh token."
        )
    except Exception as exc:
        return None, f"Gmail API Token Refresh Error: {type(exc).__name__}"


def is_gmail_api_configured() -> bool:
    """Returns True if either environment variables or local gmail_token.json exist."""
    c_id = _read_config("GMAIL_CLIENT_ID")
    r_token = _read_config("GMAIL_REFRESH_TOKEN")
    if c_id and r_token:
        return True
    return os.path.exists(TOKEN_FILE_PATH)


def send_email(
    to_address: str,
    subject: str,
    body: str,
    sender_address: str = "",
    client_id: str = "",
    client_secret: str = "",
    refresh_token: str = "",
) -> tuple[bool, str]:
    """
    Sends an expense report email using the official Google Gmail REST API (HTTPS).
    Replaces SMTP entirely to eliminate port 465/587 connection blocks on Render and local ISPs.

    Multi-User Support:
    - `to_address`: Any recipient email specified by the current session user.
    - `sender_address`: The authorized application Gmail account. If omitted, uses GMAIL_ADDRESS or 'me'.

    Returns:
        tuple[bool, str]: (Success status, descriptive message).
    """
    # 1. Recipient Input Validation & Anti-Abuse Checks
    if not to_address or not str(to_address).strip():
        return False, "Recipient email address is required."

    target_email = str(to_address).strip()
    if any(ch in target_email for ch in ["\r", "\n", ",", ";"]):
        return False, "Invalid recipient address: multiple addresses or newline injections are not permitted."

    email_regex = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    if not re.match(email_regex, target_email):
        return False, f"Invalid recipient email format: '{target_email}'."

    # 2. Resolve Sender Address
    from_email = sender_address or _read_config("GMAIL_ADDRESS") or "me"

    # 3. Obtain & Refresh OAuth 2.0 Credentials
    creds, creds_msg = get_gmail_oauth_credentials(
        client_id=client_id,
        client_secret=client_secret,
        refresh_token=refresh_token,
    )
    if not creds:
        return False, creds_msg

    # 4. Construct MIME Message
    try:
        mime_message = MIMEText(body, "plain", "utf-8")
        mime_message["To"] = target_email
        mime_message["From"] = from_email if from_email != "me" else ""
        mime_message["Subject"] = subject

        # Encode using URL-safe Base64 as required by Gmail API
        raw_bytes = mime_message.as_bytes()
        raw_b64 = base64.urlsafe_b64encode(raw_bytes).decode("utf-8")
    except Exception as exc:
        return False, f"Failed to encode email message: {exc}"

    # 5. Send via Gmail REST API over HTTPS (with timeout)
    socket_timeout = 15.0
    original_timeout = socket.getdefaulttimeout()

    try:
        socket.setdefaulttimeout(socket_timeout)
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        send_response = (
            service.users()
            .messages()
            .send(userId="me", body={"raw": raw_b64})
            .execute()
        )

        message_id = send_response.get("id", "N/A")
        # Notice: Accurately describe that Gmail API accepted the message for delivery
        return True, f"Expense report accepted by Gmail API for delivery (Message ID: {message_id})."

    except HttpError as http_err:
        status_code = http_err.resp.status if hasattr(http_err, "resp") else "Unknown"
        if status_code == 400:
            return False, "Gmail API Error (400): Bad Request — invalid message payload or recipient address."
        elif status_code == 401:
            return False, "Gmail API Error (401): Unauthorized — OAuth token expired or revoked. Please re-authenticate."
        elif status_code == 403:
            return False, "Gmail API Error (403): Quota exceeded or insufficient permissions for https://www.googleapis.com/auth/gmail.send."
        elif status_code == 429:
            return False, "Gmail API Error (429): Rate limit exceeded. Please wait a moment and try again."
        return False, f"Gmail API HTTP Error ({status_code}): Request failed."

    except (socket.timeout, TimeoutError):
        return False, "Gmail API Network Timeout: HTTPS request timed out while connecting to Google API servers."

    except Exception as exc:
        err_type = type(exc).__name__
        return False, f"Gmail API Delivery Failed ({err_type}). Please try again or use the fallback link."

    finally:
        socket.setdefaulttimeout(original_timeout)
