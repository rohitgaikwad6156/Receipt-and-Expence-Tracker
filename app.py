import importlib
import io
import os
from pathlib import Path
import re
import sys
import streamlit as st
from google import genai
from google.genai import types

# Ensure app root directory is at the front of sys.path on Streamlit Cloud & Render
_APP_DIR = str(Path(__file__).resolve().parent)
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)
elif sys.path[0] != _APP_DIR:
    sys.path.remove(_APP_DIR)
    sys.path.insert(0, _APP_DIR)

from finance import CURRENCIES, money, split_equal

try:
    from notify import (
        clean_phone_number,
        generate_gmail_web_url,
        generate_mailto_url,
        generate_whatsapp_web_url,
        is_gmail_api_configured,
        send_email,
        send_whatsapp,
    )
except ImportError:
    # If Streamlit Cloud hot-reload holds a stale cached bytecode or shadowed module, force reload
    if "notify" in sys.modules:
        import notify
        importlib.reload(notify)
        from notify import (
            clean_phone_number,
            generate_gmail_web_url,
            generate_mailto_url,
            generate_whatsapp_web_url,
            is_gmail_api_configured,
            send_email,
            send_whatsapp,
        )
    else:
        raise


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
    .block-container { max-width: 1100px; padding-top: 1.2rem; padding-bottom: 3rem; }
    .hero-banner {
        padding: 1.6rem 2rem;
        border-radius: 16px;
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        border: 1px solid #334155;
        margin-bottom: 1.2rem;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25);
    }
    .hero-banner h1 { margin: 0; font-size: 2.1rem; color: #f8fafc; font-weight: 700; }
    .hero-banner p { margin: 0.4rem 0 0; color: #94a3b8; font-size: 1.05rem; }
    .action-card {
        background: #1e293b;
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 1rem 1.2rem;
        margin-bottom: 1rem;
    }
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
GMAIL_CLIENT_ID = get_secret("GMAIL_CLIENT_ID")
GMAIL_CLIENT_SECRET = get_secret("GMAIL_CLIENT_SECRET")
GMAIL_REFRESH_TOKEN = get_secret("GMAIL_REFRESH_TOKEN")
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
        name = st.text_input("Your Name", placeholder="e.g. Rohit")

        delivery_option = st.radio(
            "Where would you like to receive your expense breakdowns?",
            ["📱 WhatsApp (Direct message to your phone)", "✉️ Email (Gmail report)", "Both WhatsApp & Email"],
            index=0,
            help="Choose how you prefer to receive summaries.",
        )

        c1, c2 = st.columns(2)
        with c1:
            whatsapp_input = st.text_input(
                "WhatsApp Number (with country code)",
                value="+919309280705",
                placeholder="+91XXXXXXXXXX",
                help="Your WhatsApp number for expense summaries and bill splits.",
            )
        with c2:
            email_input = st.text_input(
                "Email Address",
                value="grohit6156@gmail.com",
                placeholder="you@example.com",
                help="Your email address for expense reports.",
            )

        currency_choice = st.selectbox(
            "Default Currency",
            ["INR (₹)", "USD ($)", "EUR (€)", "GBP (£)"],
            index=0,
        )

        if not GEMINI_API_KEY:
            st.info("💡 Enter your Gemini API Key below for this session:")
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
            if not name.strip():
                st.warning("Please enter your name.")
            elif not whatsapp_input.strip() and not email_input.strip():
                st.warning("Please enter at least a WhatsApp number or an Email address.")
            elif not key_to_use:
                st.error("Please provide a Gemini API Key (or configure GEMINI_API_KEY in .streamlit/secrets.toml).")
            else:
                if manual_key.strip():
                    st.session_state.custom_api_key = manual_key.strip()
                    gemini_client = get_gemini_client(manual_key.strip())

                st.session_state.name = name.strip()
                st.session_state.whatsapp_number = clean_phone_number(whatsapp_input)
                st.session_state.email_address = email_input.strip()
                st.session_state.delivery_option = delivery_option
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
    # 5. User Profile & Message Helpers
    # --------------------------------------------------------------------------
    user_name = st.session_state.get("name", "User")
    user_wa = st.session_state.get("whatsapp_number", "")
    user_email = st.session_state.get("email_address", "")
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

        st.subheader("📱 Destination Settings")
        new_wa = st.text_input("WhatsApp Number", value=user_wa, placeholder="+91XXXXXXXXXX")
        if new_wa != user_wa:
            st.session_state.whatsapp_number = clean_phone_number(new_wa)
            user_wa = st.session_state.whatsapp_number

        new_email = st.text_input("Email Address", value=user_email, placeholder="you@example.com")
        if new_email != user_email:
            st.session_state.email_address = new_email.strip()
            user_email = st.session_state.email_address

        st.caption(f"Currency: {user_curr}")

        st.divider()

        st.subheader("Service Status")
        st.write("🟢 Gemini AI Vision & Chat" if active_api_key else "⚪ Gemini (No key)")
        gmail_ready = is_gmail_api_configured()
        st.write("🟢 Gmail API Active (OAuth 2.0)" if gmail_ready else "⚪ Gmail API (Needs OAuth setup)")

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
                curr_code = user_curr.split()[0]
                for person, share in result.items():
                    st.write(f"• **{person}**: {money(share, curr_code)}")

        st.divider()

        # Chat Transcript Download
        if len(st.session_state.get("messages", [])) > 1:
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
    # 7. Main Header & Unmissable Action Buttons (ALWAYS ENABLED)
    # --------------------------------------------------------------------------
    header_col, btn_wa_col, btn_email_col = st.columns([4.5, 2.5, 2], vertical_alignment="center")

    with header_col:
        st.title("🧾 ReceiptWise")
        st.caption(
            f"Logged in as **{user_name}** · Deliver to: 📱 WhatsApp: `{user_wa or 'Not set'}` | ✉️ Email: `{user_email or 'Not set'}`"
        )

    summary_generated = None

    # WHATSAPP BUTTON (Always Enabled & Clearly Visible)
    with btn_wa_col:
        wa_btn_label = "📱 Send to WhatsApp"
        if st.button(wa_btn_label, type="primary", use_container_width=True):
            if len(st.session_state.get("messages", [])) <= 1:
                st.info("💡 No expenses logged yet! Type an expense or upload a receipt photo below, then click here to send the WhatsApp summary.")
            elif not user_wa:
                st.warning("⚠️ Please enter a WhatsApp number in the sidebar.")
            else:
                with st.spinner("Preparing summary and sending to WhatsApp..."):
                    summary_text = ask_gemini([SUMMARY_REQUEST_PROMPT])
                    summary_generated = summary_text
                    success, info = send_whatsapp(
                        to_number=user_wa,
                        user_name=user_name,
                        summary=summary_text,
                        account_sid=TWILIO_ACCOUNT_SID,
                        auth_token=TWILIO_AUTH_TOKEN,
                        from_number=TWILIO_WHATSAPP_FROM,
                        content_sid=TWILIO_CONTENT_SID,
                    )
                    if success:
                        st.success(f"✅ {info}")
                    else:
                        st.warning(f"⚠️ {info}")

                    # Always provide a 1-click WhatsApp Click-to-Chat button
                    wa_url = generate_whatsapp_web_url(user_wa, summary_text)
                    st.link_button("💬 Open & Share in WhatsApp Directly", wa_url, use_container_width=True)

    # EMAIL BUTTON (Always Enabled)
    with btn_email_col:
        if st.button("✉️ Send to Email", use_container_width=True):
            if len(st.session_state.get("messages", [])) <= 1:
                st.info("💡 No expenses logged yet! Log an expense or receipt below first.")
            elif not user_email:
                st.warning("⚠️ Please enter an email address in the sidebar.")
            else:
                with st.spinner("Preparing summary and sending email..."):
                    summary_text = ask_gemini([SUMMARY_REQUEST_PROMPT])
                    summary_generated = summary_text
                    success, info = send_email(
                        to_address=user_email,
                        subject=f"ReceiptWise Expense Summary for {user_name}",
                        body=summary_text,
                        sender_address=GMAIL_ADDRESS,
                        client_id=GMAIL_CLIENT_ID,
                        client_secret=GMAIL_CLIENT_SECRET,
                        refresh_token=GMAIL_REFRESH_TOKEN,
                    )

                    if success:
                        st.success(f"✅ {info}")
                    else:
                        st.warning(f"⚠️ {info}")
                        gmail_url = generate_gmail_web_url(user_email, f"ReceiptWise Expense Summary for {user_name}", summary_text)
                        st.link_button("📧 Open in Gmail Web (1-Click Send)", gmail_url, type="primary", use_container_width=True)
                        mailto_url = generate_mailto_url(user_email, f"ReceiptWise Expense Summary for {user_name}", summary_text)
                        st.link_button("✉️ Open in Default Mail App", mailto_url, use_container_width=True)

    if summary_generated:
        with st.expander("📋 View Generated Expense Summary", expanded=True):
            st.text(summary_generated)
            c_copy1, c_copy2, c_copy3 = st.columns(3)
            with c_copy1:
                wa_share = generate_whatsapp_web_url(user_wa, summary_generated)
                st.link_button("💬 Share in WhatsApp", wa_share, use_container_width=True)
            with c_copy2:
                gmail_share = generate_gmail_web_url(user_email, f"ReceiptWise Expense Summary for {user_name}", summary_generated)
                st.link_button("📧 Send via Gmail Web", gmail_share, use_container_width=True)
            with c_copy3:
                st.download_button(
                    "⬇️ Download as Text",
                    data=summary_generated,
                    file_name="expense_summary.txt",
                    mime="text/plain",
                    use_container_width=True,
                )


    # --------------------------------------------------------------------------
    # 8. Step 6 — Render Chat History & Welcome Message
    # --------------------------------------------------------------------------
    if not st.session_state.messages:
        welcome_text = WELCOME_MESSAGE_TEMPLATE.format(
            name=user_name,
            button_label="Send to WhatsApp",
            channel="WhatsApp",
        )
        add_message("assistant", "text", welcome_text)
    else:
        for message in st.session_state.messages:
            render_message(message)

    # --------------------------------------------------------------------------
    # 9. Prominent Image Uploader & Quick Prompts
    # --------------------------------------------------------------------------
    with st.expander("📎 Upload Receipt Photo directly (or drag into chat bar below)", expanded=False):
        up_col1, up_col2 = st.columns([3, 1])
        with up_col1:
            direct_photo = st.file_uploader(
                "Upload a photo of your receipt or bill",
                type=["jpg", "jpeg", "png", "webp"],
                key="prominent_photo_uploader",
            )
        with up_col2:
            split_note = st.text_input("Split notes (optional)", placeholder="e.g. Split with 3 friends", key="direct_split_notes")
            analyze_clicked = st.button("✨ Analyze Receipt Photo", disabled=direct_photo is None, use_container_width=True, type="primary")

        if analyze_clicked and direct_photo is not None:
            photo_bytes = direct_photo.getvalue()
            add_message("user", "image", photo_bytes)
            user_caption = f"Analyze this receipt. {split_note}".strip()
            add_message("user", "text", user_caption)
            parts = [
                types.Part.from_bytes(data=photo_bytes, mime_type=direct_photo.type),
                user_caption + " Extract merchant, date, currency, itemized items with prices, tax, tip, and total. Categorize spending and compute the bill split.",
            ]
            with st.spinner("Analyzing receipt with Gemini..."):
                answer = ask_gemini(parts)
                add_message("assistant", "text", answer)
                st.rerun()

    # Quick suggestion chips
    st.markdown(
        """
        <div style="font-size: 0.85rem; color: #94a3b8; margin-top: 0.4rem; margin-bottom: 0.2rem;">
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

    # --------------------------------------------------------------------------
    # 10. Step 7 — Chat Input: Text and Photos
    # --------------------------------------------------------------------------
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
            default_photo_prompt = (
                "Read this receipt or bill. Extract the merchant name, date, currency, "
                "an itemized list of all items with their prices, tax/tip, and the final total amount. "
                "Categorize the expense, and offer to split the bill."
            )
            parts.append(default_photo_prompt)

        with st.spinner("Analyzing & calculating..."):
            answer = ask_gemini(parts)
            add_message("assistant", "text", answer)

        # Show prominent WhatsApp and Email action triggers right below the response
        st.markdown(
            """
            <div style="background: rgba(37, 211, 102, 0.1); border: 1px solid rgba(37, 211, 102, 0.3); border-radius: 8px; padding: 0.6rem 1rem; margin-top: 0.5rem;">
                <b>📱 Ready to share?</b> Click <b>📱 Send to WhatsApp</b> at the top of your screen to deliver this breakdown straight to your phone!
            </div>
            """,
            unsafe_allow_html=True,
        )
