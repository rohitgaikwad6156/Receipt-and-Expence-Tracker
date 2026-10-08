import io
import os
import streamlit as st
from google import genai
from google.genai import types

from finance import CURRENCIES, money, split_equal
from notify import send_email, send_whatsapp
from prompts import (
    SUMMARY_REQUEST_PROMPT,
    SYSTEM_PROMPT,
    WELCOME_MESSAGE_TEMPLATE,
)

# ------------------------------------------------------------------------------
# 1. Page Configuration & Aesthetics
# ------------------------------------------------------------------------------
st.set_page_config(
    page_title="ReceiptWise — AI Receipt & Expense Tracker",
    page_icon="🧾",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .block-container { max-width: 1100px; padding-top: 1.5rem; padding-bottom: 3rem; }
    .hero-banner {
        padding: 1.8rem 2.2rem;
        border-radius: 16px;
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        border: 1px solid #334155;
        margin-bottom: 1.5rem;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25);
    }
    .hero-banner h1 { margin: 0; font-size: 2.2rem; color: #f8fafc; font-weight: 700; }
    .hero-banner p { margin: 0.5rem 0 0; color: #94a3b8; font-size: 1.05rem; }
    .chip-container { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 1rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ------------------------------------------------------------------------------
# 2. Secret / Configuration Helpers
# ------------------------------------------------------------------------------
def get_secret(key: str, default: str = "") -> str:
    """Reads configuration safely from st.secrets or environment variables."""
    try:
        val = st.secrets.get(key)
        if val:
            return str(val).strip()
    except Exception:
        pass
    return os.getenv(key, default).strip()


GEMINI_API_KEY = get_secret("GEMINI_API_KEY")
MODEL_NAME = get_secret("GEMINI_MODEL", "gemini-3.5-flash")
GMAIL_ADDRESS = get_secret("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = get_secret("GMAIL_APP_PASSWORD")
TWILIO_ACCOUNT_SID = get_secret("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = get_secret("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_FROM = get_secret("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
TWILIO_CONTENT_SID = get_secret("TWILIO_CONTENT_SID")


# ------------------------------------------------------------------------------
# 3. Connecting to Gemini (Cached to survive Streamlit reruns)
# ------------------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def get_gemini_client(api_key: str):
    """Builds and caches the Gemini client once per session."""
    if not api_key:
        return None
    return genai.Client(api_key=api_key)


# Allow user-provided session API key if not configured in secrets
active_api_key = st.session_state.get("custom_api_key") or GEMINI_API_KEY
gemini_client = get_gemini_client(active_api_key) if active_api_key else None


# ------------------------------------------------------------------------------
# 4. Step 5 — Onboarding Screen
# ------------------------------------------------------------------------------
if "onboarded" not in st.session_state:
    st.markdown(
        """
        <div class="hero-banner">
            <h1>🧾 ReceiptWise</h1>
            <p>Snap it. Track it. Split it. Text or email yourself the results in seconds.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.subheader("Welcome! Set up your expense tracker")

    with st.form("onboarding_form"):
        name = st.text_input("Your Name", placeholder="e.g. Alex")

        channel = st.radio(
            "Where should your expense summaries be sent?",
            ["Email (Gmail - Recommended)", "WhatsApp"],
            horizontal=True,
            help="Choose how you want to receive your final receipt breakdown.",
        )

        if "Email" in channel:
            destination = st.text_input(
                "Your Email Address",
                placeholder="you@example.com",
                help="Your expense summaries and bill splits will be emailed here.",
            )
        else:
            destination = st.text_input(
                "WhatsApp Number (with country code)",
                placeholder="+91XXXXXXXXXX",
                help="Your expense summaries will be sent to this WhatsApp number.",
            )

        currency_choice = st.selectbox(
            "Default Currency",
            ["INR (₹)", "USD ($)", "EUR (€)", "GBP (£)"],
            index=0,
        )

        # In case secrets.toml was not populated yet, provide a friendly key field
        if not GEMINI_API_KEY:
            st.info("💡 You can also provide your Gemini API Key below for this session:")
            manual_key = st.text_input(
                "Google Gemini API Key",
                type="password",
                placeholder="AIzaSy...",
                help="Get a free key from https://aistudio.google.com",
            )
        else:
            manual_key = ""

        submitted = st.form_submit_button("Let's go 🚀", type="primary")

        if submitted:
            key_to_use = GEMINI_API_KEY or manual_key.strip()
            if not name.strip() or not destination.strip():
                st.warning("Please fill in both your name and recipient destination.")
            elif not key_to_use:
                st.error("Please provide a Gemini API Key (or configure GEMINI_API_KEY in .streamlit/secrets.toml).")
            else:
                if manual_key.strip():
                    st.session_state.custom_api_key = manual_key.strip()
                    gemini_client = get_gemini_client(manual_key.strip())

                st.session_state.name = name.strip()
                st.session_state.channel = "Email" if "Email" in channel else "WhatsApp"
                st.session_state.destination = destination.strip()
                st.session_state.currency = currency_choice

                # Initialize Gemini chat session with SYSTEM_PROMPT memory
                try:
                    st.session_state.chat = gemini_client.chats.create(
                        model=MODEL_NAME,
                        config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
                    )
                    st.session_state.messages = []
                    st.session_state.onboarded = True
                    st.rerun()
                except Exception as exc:
                    st.error(f"Could not connect to Gemini: {exc}")
    st.stop()
else:
    # --------------------------------------------------------------------------
    # 5. Chat Interface Helpers
    # --------------------------------------------------------------------------
    user_name = st.session_state.get("name", "User")
    user_dest = st.session_state.get("destination", "")
    user_channel = st.session_state.get("channel", "Email")
    user_curr = st.session_state.get("currency", "INR (₹)")

    def render_message(message: dict):
        """Renders a single message from history into the Streamlit UI."""
        with st.chat_message(message["role"]):
            if message["kind"] == "text":
                st.write(message["content"])
            elif message["kind"] == "image":
                st.image(message["content"])

    def add_message(role: str, kind: str, content):
        """Saves a message to session history and renders it immediately."""
        if "messages" not in st.session_state:
            st.session_state.messages = []
        st.session_state.messages.append({"role": role, "kind": kind, "content": content})
        render_message(st.session_state.messages[-1])

    def ask_gemini(parts) -> str:
        """Sends prompt parts (text / images) to the persistent Gemini chat session."""
        try:
            if "chat" not in st.session_state or st.session_state.chat is None:
                st.session_state.chat = gemini_client.chats.create(
                    model=MODEL_NAME,
                    config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
                )
            response = st.session_state.chat.send_message(parts)
            return response.text or "No response generated."
        except Exception as error:
            return f"Sorry, something went wrong: {error}"

    # --------------------------------------------------------------------------
    # 6. Sidebar Controls & Quick Tools
    # --------------------------------------------------------------------------
    with st.sidebar:
        st.title("🧾 ReceiptWise")
        st.markdown(f"👤 **{user_name}**")
        st.caption(f"Destination: `{user_dest}` ({user_channel})")
        st.caption(f"Currency: {user_curr}")

        st.divider()

        st.subheader("Service Status")
        st.write("🟢 Gemini AI Vision & Chat" if active_api_key else "⚪ Gemini (No key)")
        if user_channel == "Email":
            email_ready = bool(GMAIL_ADDRESS and GMAIL_APP_PASSWORD)
            st.write("🟢 Gmail SMTP Configured" if email_ready else "⚪ Gmail (Needs secrets.toml)")
        else:
            wa_ready = bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN)
            st.write("🟢 Twilio WhatsApp Configured" if wa_ready else "⚪ Twilio (Needs secrets.toml)")

    st.divider()

    with st.expander("⚡ Quick Bill Splitter (Offline)"):
        split_total = st.number_input("Total Amount", min_value=0.0, value=1200.0, step=50.0)
        split_people = st.number_input("Number of People", min_value=2, max_value=20, value=3)
        if st.button("Calculate Equal Split", use_container_width=True):
            minor_val = int(round(split_total * 100))
            people_names = [f"Person {i+1}" for i in range(split_people)]
            result = split_equal(minor_val, people_names)
            curr_code = st.session_state.currency.split()[0]
            for person, share in result.items():
                st.write(f"• **{person}**: {money(share, curr_code)}")

    st.divider()

    # Chat Transcript Download
    if len(st.session_state.messages) > 1:
        transcript_lines = []
        for m in st.session_state.messages:
            if m["kind"] == "text":
                transcript_lines.append(f"[{m['role'].upper()}]: {m['content']}\n")
        transcript_text = "\n".join(transcript_lines)
        st.download_button(
            "📥 Download Chat History",
            data=transcript_text,
            file_name="receiptwise_chat_history.txt",
            mime="text/plain",
            use_container_width=True,
        )

    if st.button("🔄 New Session / Reset", use_container_width=True):
        st.session_state.clear()
        st.rerun()

    # --------------------------------------------------------------------------
    # 7. Step 8 — Main Header & Action Button (Send to WhatsApp / Email)
    # --------------------------------------------------------------------------
    header_col, button_col = st.columns([5, 2], vertical_alignment="center")

    with header_col:
        st.title("🧾 ReceiptWise")
        st.caption(
            f"Logged in as **{user_name}** — updates go to `{user_dest}` ({user_channel})"
        )

    with button_col:
        # Button is disabled until at least one user exchange has taken place
        send_disabled = len(st.session_state.get("messages", [])) <= 1
        btn_label = f"📤 Send to {user_channel}"

        if st.button(btn_label, disabled=send_disabled, use_container_width=True, type="primary"):
            with st.spinner("Summarizing your expenses & bill splits..."):
                summary_text = ask_gemini([SUMMARY_REQUEST_PROMPT])

                if user_channel == "Email":
                    success, info = send_email(
                        to_address=user_dest,
                        subject=f"ReceiptWise Expense Summary for {user_name}",
                        body=summary_text,
                        gmail_address=GMAIL_ADDRESS,
                        app_password=GMAIL_APP_PASSWORD,
                    )
                else:
                    success, info = send_whatsapp(
                        to_number=user_dest,
                        user_name=user_name,
                        summary=summary_text,
                        account_sid=TWILIO_ACCOUNT_SID,
                        auth_token=TWILIO_AUTH_TOKEN,
                        from_number=TWILIO_WHATSAPP_FROM,
                        content_sid=TWILIO_CONTENT_SID,
                    )

                if success:
                    st.success(f"Sent! Check your {user_channel} 📲")
                else:
                    st.error(f"Could not send {user_channel} message: {info}")

                # Always display the summary in an expander so the user can view/copy it immediately
                with st.expander("📋 View Generated Expense Summary", expanded=True):
                    st.text(summary_text)

    # --------------------------------------------------------------------------
    # 8. Step 6 — Render Chat History & Welcome Message
    # --------------------------------------------------------------------------
    button_target_name = f"Send to {user_channel}"

    if not st.session_state.messages:
        welcome_text = WELCOME_MESSAGE_TEMPLATE.format(
            name=user_name,
            button_label=button_target_name,
            channel=user_channel,
        )
        add_message("assistant", "text", welcome_text)
    else:
        for message in st.session_state.messages:
            render_message(message)

    # --------------------------------------------------------------------------
    # 9. Step 7 — Handling Input: Text and Photos
    # --------------------------------------------------------------------------
    # Quick suggestion chips
    st.markdown(
        """
        <div style="font-size: 0.85rem; color: #94a3b8; margin-top: 0.5rem; margin-bottom: 0.2rem;">
            💡 <b>Quick prompts:</b>
        </div>
        """,
        unsafe_allow_html=True,
    )

    chip_col1, chip_col2, chip_col3, chip_col4 = st.columns(4)
    quick_prompt = None

    if chip_col1.button("💸 Split bill equally (3 people)", use_container_width=True):
        quick_prompt = "Split the latest receipt equally among 3 people: Alex, Sam, and Taylor."
    if chip_col2.button("🍽️ Break down food vs drinks", use_container_width=True):
        quick_prompt = "Break down the food items versus beverages and calculate totals for each category."
    if chip_col3.button("🧾 What was the total tax & tip?", use_container_width=True):
        quick_prompt = "What was the total tax and tip on this receipt, and what percentage of the total does it represent?"
    if chip_col4.button("📊 Summarize all expenses", use_container_width=True):
        quick_prompt = "Provide a running summary of all items, merchants, and total expenses discussed so far."

    user_input = st.chat_input(
        "Ask a question, or attach a photo of your receipt/bill",
        accept_file=True,
        file_type=["jpg", "jpeg", "png", "webp"],
    )

    active_prompt_text = quick_prompt or (user_input.text if user_input else "")
    active_photo = user_input.files[0] if (user_input and user_input.files) else None

    if user_input or quick_prompt:
        parts = []

        if active_photo is not None:
            photo_bytes = active_photo.getvalue()
            add_message("user", "image", photo_bytes)
            parts.append(types.Part.from_bytes(data=photo_bytes, mime_type=active_photo.type))

        if active_prompt_text:
            add_message("user", "text", active_prompt_text)
            parts.append(active_prompt_text)
        elif active_photo is not None:
            # Default instruction if a photo was provided with no caption (Step 7)
            default_photo_prompt = (
                "Read this receipt or bill. Extract the merchant name, date, currency, "
                "an itemized list of all items with their prices, tax/tip, and the final total amount. "
                "Categorize the expense, and offer to split the bill."
            )
            parts.append(default_photo_prompt)

        with st.spinner("Analyzing receipt & calculating..."):
            answer = ask_gemini(parts)
            add_message("assistant", "text", answer)

