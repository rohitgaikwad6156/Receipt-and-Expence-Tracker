"""
ReceiptWise — Gmail OAuth 2.0 Authorization Setup
=================================================
This script runs locally on your development machine (Windows/macOS/Linux)
to perform a one-time Google OAuth 2.0 consent flow.

It generates `gmail_token.json`, which contains the OAuth refresh token
needed for automated, headless email sending via the Gmail REST API (HTTPS).

Security Notice:
- Request only the minimal scope: https://www.googleapis.com/auth/gmail.send
- Never commit credentials.json or gmail_token.json to GitHub!
"""

import json
import os
import sys

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    print("Error: Missing required packages.")
    print("Please run: pip install -r requirements.txt")
    sys.exit(1)

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), "credentials.json")
TOKEN_FILE = os.path.join(os.path.dirname(__file__), "gmail_token.json")


def run_oauth_flow():
    print("=" * 65)
    print("   ReceiptWise — Google Gmail API OAuth 2.0 Setup")
    print("=" * 65)

    if not os.path.exists(CREDENTIALS_FILE):
        print(f"\n[ERROR] Credentials file not found at: {CREDENTIALS_FILE}")
        print("Please download your OAuth client credentials JSON from Google Cloud Console,")
        print("rename it to 'credentials.json', and place it in the project root directory.\n")
        sys.exit(1)

    print("\n[1/3] Reading OAuth client credentials...")
    try:
        with open(CREDENTIALS_FILE, "r", encoding="utf-8") as f:
            creds_data = json.load(f)
            client_id = creds_data.get("installed", {}).get("client_id")
            if not client_id:
                print("[ERROR] Invalid credentials.json: Missing 'installed.client_id'.")
                sys.exit(1)
        print("      Client ID verified.")
    except Exception as exc:
        print(f"[ERROR] Failed to parse credentials.json: {exc}")
        sys.exit(1)

    print("\n[2/3] Launching Google OAuth 2.0 consent flow in your browser...")
    print("      Requested scope: https://www.googleapis.com/auth/gmail.send")
    print("      Access type: offline (requesting persistent refresh token)")

    try:
        flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
        # prompt='consent' and access_type='offline' are critical to ensure a refresh_token is issued
        creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
    except Exception as exc:
        print(f"\n[ERROR] OAuth flow failed or was cancelled: {exc}")
        sys.exit(1)

    if not creds:
        print("\n[ERROR] No credentials received from authorization server.")
        sys.exit(1)

    if not creds.refresh_token:
        print("\n[WARNING] Google did not return a refresh token!")
        print("This can happen if you authorized this app previously without prompt='consent'.")
        print("Please visit https://myaccount.google.com/permissions, remove ReceiptWise,")
        print("and re-run this setup script to obtain a new refresh token.")
        sys.exit(1)

    print("\n[3/3] Saving authorized credentials to gmail_token.json...")
    token_payload = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
    }

    try:
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            json.dump(token_payload, f, indent=2)
        print("      Successfully generated gmail_token.json!")
    except Exception as exc:
        print(f"[ERROR] Failed to write gmail_token.json: {exc}")
        sys.exit(1)

    # Automatically update .streamlit/secrets.toml if it exists
    secrets_file = os.path.join(os.path.dirname(__file__), ".streamlit", "secrets.toml")
    if os.path.exists(secrets_file):
        try:
            with open(secrets_file, "r", encoding="utf-8") as sf:
                secrets_content = sf.read()
            
            # Replace GMAIL_REFRESH_TOKEN = "..." or append it
            if "GMAIL_REFRESH_TOKEN" in secrets_content:
                secrets_content = re.sub(
                    r'GMAIL_REFRESH_TOKEN\s*=\s*["\'].*?["\']',
                    f'GMAIL_REFRESH_TOKEN = "{creds.refresh_token}"',
                    secrets_content,
                )
            else:
                secrets_content += f'\nGMAIL_REFRESH_TOKEN = "{creds.refresh_token}"\n'

            with open(secrets_file, "w", encoding="utf-8") as sf:
                sf.write(secrets_content)
            print("      Updated local .streamlit/secrets.toml with your GMAIL_REFRESH_TOKEN!")
        except Exception as sec_exc:
            print(f"      [Notice] Could not auto-update secrets.toml: {sec_exc}")

    print("\n" + "=" * 65)
    print("   AUTHORIZATION SUCCESSFUL!")
    print("=" * 65)
    print("ReceiptWise is now authorized to send expense summaries via Gmail API.")
    print(f"\nSaved token file: {TOKEN_FILE}")
    print("\nNEXT STEP: Deploying on Streamlit Cloud & Render:")
    print("  1. In Streamlit Cloud: Click 'Manage app' (bottom-right) > ⋮ > 'Settings' > 'Secrets'.")
    print("     Paste the updated contents of your .streamlit/secrets.toml there.")
    print("  2. In Render: Go to Environment and set:")
    print("     - GMAIL_CLIENT_ID")
    print("     - GMAIL_CLIENT_SECRET")
    print("     - GMAIL_REFRESH_TOKEN")
    print("     - GMAIL_ADDRESS")
    print("\n(Note: Keep your refresh token and client secret private. Never commit them to Git.)\n")


if __name__ == "__main__":
    run_oauth_flow()
