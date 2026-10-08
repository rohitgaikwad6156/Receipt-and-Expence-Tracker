# 🧾 ReceiptWise — AI Receipt & Expense Tracker

ReceiptWise is a Streamlit receipt-and-expense tracker built for the AI Vision ChatBot workshop's **Receipt & Expense Tracker / Bill Splitter** project.

### Features
- Scan real receipt photos with Google Gemini and **review extracted merchant, date, itemized charges, category and total before saving**.
- Track manual and scanned expenses, view spending charts and category summaries, and export CSV.
- Split bills evenly or item-by-item with exact cent/paise rounding.
- Chat with Gemini about the verified current expense ledger.
- Email an expense summary using Gmail SMTP, or download a TXT report.
- All live secrets stay in Streamlit Secrets and are excluded from GitHub.

### Run locally

Requires **Python 3.9+**:

```bash
git clone https://github.com/rohitgaikwad6156/Receipt-and-Expence-Tracker.git
cd Receipt-and-Expence-Tracker
python -m venv venv
# Windows: .\venv\Scripts\Activate.ps1
# macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
# Copy .streamlit/secrets.toml.example to .streamlit/secrets.toml and set real values
streamlit run app.py
```

Go to http://localhost:8501 and onboard with your name, email, and one ledger currency. The manual entry, bill splitter and CSV export work without external keys.

### Secrets

Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and replace placeholders:

```toml
GEMINI_API_KEY = "your-key-from-google-ai-studio"
GEMINI_MODEL = "gemini-2.5-flash"
GMAIL_ADDRESS = "your-sender@gmail.com"
GMAIL_APP_PASSWORD = "your-16-character-google-app-password"
```

Obtain a Gemini key from [Google AI Studio](https://aistudio.google.com/app/apikey). For the **recommended email action tool** in the workshop guide, enable Gmail 2-Step Verification and create a [Google App Password](https://myaccount.google.com/apppasswords). Do not commit real keys.

### Deploy (submission requirement)

1. At [Streamlit Community Cloud](https://share.streamlit.io), create a new app from this repository, branch `main`, entry point `app.py`.
2. Enter your keys into the deployed app's **Settings → Secrets** (never check them into source control).
3. Deploy and verify receipt scan, chat, manual tracking, and Gmail sending.
4. Submit **both** your public GitHub repository URL and the deployed Streamlit URL.

### Privacy and constraints

This is a **session-only prototype**, not a permanent database: export your expense CSV before closing the session. Uploaded receipt images are sent to Gemini for analysis; AI-extracted values must be verified. Currency conversion is not automatic. Actual email sending requires a valid Gmail App Password and network access.

### Tests

```bash
python -m unittest discover -s tests -v
python -m compileall -q .
```

### Project files

`app.py` Streamlit UI · `ai.py` Gemini vision/chat · `finance.py` pure finance helpers · `notify.py` Gmail action · `prompts.py` AI prompts · `requirements.txt` dependencies · `.streamlit/secrets.toml.example` safe template · `.gitignore` secret protection · `tests/test_finance.py` unit tests.

Based on the handout's **onboarding → Gemini chat/vision → structured image extraction → email summary** workflow, with dashboards and validation added for polish.
