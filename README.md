# 🧾 ReceiptWise — AI Receipt & Expense Tracker / Bill Splitter

ReceiptWise is an AI-powered receipt scanner, expense tracker, and emergency bill splitter built with **Streamlit**, **Google Gemini (Vision + Chat)**, and **Gmail SMTP / Twilio WhatsApp** delivery.

Built for the **AI Vision ChatBot Workshop** following the *MacroSnap* architectural blueprint (Project 2: *Receipt & Expense Tracker / Bill Splitter*).

---

## 🌟 Features

- **📸 Instant Receipt Vision Scanning**: Photograph or upload any receipt, bill, or invoice (`JPG`, `PNG`, `WebP`) directly in the chat input. Gemini extracts merchant names, purchase dates, itemized item prices, tax, tip, and grand totals.
- **💬 Conversational Expense Assistant**: Ask natural-language follow-ups like *"Split this bill between 3 people"*, *"Who owes what if Alex had the pasta and Sam had the salad?"*, or *"How much did I spend on taxes?"*.
- **👥 Smart Bill Splitting**: Automatically splits bills equally or by itemized order with mathematically exact cent/paise rounding.
- **📤 One-Click Delivery**: Click **"Send to Email"** or **"Send to WhatsApp"** to get a clean, formatted expense summary sent straight to your inbox or phone.
- **⚡ Quick Offline Bill Splitter**: Handy offline calculator in the sidebar for quick math without an API call.
- **📥 Chat History Export**: Download full transcripts and breakdowns anytime.
- **🔒 Privacy & Security**: All credentials are saved in `.streamlit/secrets.toml` and kept out of Git.

---

## 📁 Project Structure

```text
Receipt-and-Expence-Tracker/
├── app.py                      # Main Streamlit chat app & UI
├── prompts.py                  # Scoped system prompt, welcome & summary templates
├── notify.py                   # Email (Gmail SMTP) & WhatsApp (Twilio) senders
├── finance.py                  # Currency, split calculations & money helpers
├── requirements.txt            # Python dependencies
├── .gitignore                  # Excludes secrets.toml, venv, pycache
├── .streamlit/
│   ├── config.toml             # Streamlit visual theme
│   └── secrets.toml.example    # Template for API keys and secrets
└── tests/
    ├── test_finance.py         # Unit tests for finance math and splits
    └── test_notify_prompts.py  # Unit tests for prompt structure & formatters
```

---

## 🚀 Step-by-Step Setup & Running Locally

### 1. Prerequisites
- **Python 3.9+** installed
- A free **Google Gemini API Key** from [Google AI Studio](https://aistudio.google.com)
- *(Recommended)* A Gmail account with 2-Step Verification enabled to create a free [Google App Password](https://myaccount.google.com/apppasswords) for email delivery, **OR** a free [Twilio account](https://www.twilio.com/try-twilio) for WhatsApp sandbox delivery.

### 2. Clone and Setup Environment

```bash
# Clone the repository
git clone https://github.com/rohitgaikwad6156/Receipt-and-Expence-Tracker.git
cd Receipt-and-Expence-Tracker

# Create a virtual environment
python -m venv venv

# Activate the virtual environment
# On Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# On macOS / Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure Secrets

Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`:

```bash
# Windows PowerShell:
Copy-Item .streamlit/secrets.toml.example .streamlit/secrets.toml

# macOS / Linux:
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

Open `.streamlit/secrets.toml` and fill in your keys:

```toml
# Required: Gemini API Key
GEMINI_API_KEY = "your-gemini-api-key-here"
GEMINI_MODEL = "gemini-2.5-flash"

# Option B: Gmail SMTP (Recommended - Free)
GMAIL_ADDRESS = "your-email@gmail.com"
GMAIL_APP_PASSWORD = "your-16-character-app-password"

# Option A: Twilio WhatsApp (Optional)
TWILIO_ACCOUNT_SID = "your-twilio-account-sid-here"
TWILIO_AUTH_TOKEN = "your-twilio-auth-token-here"
TWILIO_WHATSAPP_FROM = "whatsapp:+14155238886"
TWILIO_CONTENT_SID = ""
```

> **Note**: Never commit `.streamlit/secrets.toml` to GitHub! The `.gitignore` file is already configured to keep it private.

### 4. Run the Application

```bash
streamlit run app.py
```

The app will open automatically at `http://localhost:8501`.

---

## 🧪 Running Automated Tests

Run the test suite to verify money calculations, bill splitting math, and prompt templates:

```bash
python -m unittest discover -s tests -v
```

---

## ☁️ Deploying to Streamlit Community Cloud

1. Push your repository to GitHub (ensure `.streamlit/secrets.toml` is not committed).
2. Visit [share.streamlit.io](https://share.streamlit.io) and log in with your GitHub account.
3. Click **"New app"**, select your repository, branch (`main`), and set the main file path to `app.py`.
4. In the app settings under **Settings → Secrets**, paste the contents of your `.streamlit/secrets.toml`.
5. Click **Deploy**. Your live app URL will be generated!

---

## 📋 Evaluation Criteria Alignment

| Criteria | Weight | Implementation |
| :--- | :---: | :--- |
| **Functionality** | 40% | Core end-to-end flow: Onboarding → photo/text chat input → Gemini vision analysis → One-click Email/WhatsApp delivery works smoothly. |
| **Prompt Design** | 20% | `SYSTEM_PROMPT` strictly scoped to receipts, expense tracking, currency, and fair bill-splitting, with guardrails against off-topic queries. |
| **Code Quality** | 20% | Modularized files (`app.py`, `prompts.py`, `notify.py`, `finance.py`), cached Gemini connection, comprehensive unit tests, zero committed secrets. |
| **Creativity & Polish**| 20% | Dark glassmorphic theme, quick prompt suggestions, offline bill split calculator, chat download, multi-channel support (Email & WhatsApp). |
