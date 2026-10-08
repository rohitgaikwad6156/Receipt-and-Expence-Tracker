from datetime import date
import json
import os
import re
import pandas as pd
import streamlit as st
from ai import scan_receipt, new_chat
from finance import CATEGORIES, CURRENCIES, expense_csv, expense_summary, make_expense, money, parse_receipt, split_by_item, split_equal, to_minor
from notify import send_email
from prompts import SUMMARY_REQUEST_PROMPT, WELCOME_MESSAGE_TEMPLATE

st.set_page_config(page_title="ReceiptWise | AI Expense Tracker", page_icon="🧾", layout="wide")
st.markdown("""<style>
.block-container {max-width:1200px;padding-top:2rem}
.hero {padding:1.7rem 2rem;border-radius:18px;background:linear-gradient(110deg,#293d91,#151e37);border:1px solid #4c5fa4;margin-bottom:1.5rem}
.hero h1 {color:white;margin:0;font-size:2.4rem}
.hero p {color:#c8d4ef;margin:.4rem 0 0}
[data-testid="stMetric"] {background:#171f34;border:1px solid #29344d;border-radius:14px;padding:1rem}
</style>""", unsafe_allow_html=True)

def secret(key):
    try:
        return os.getenv(key) or st.secrets.get(key) or ""
    except (FileNotFoundError, KeyError):
        return os.getenv(key) or ""

API_KEY = secret("GEMINI_API_KEY")
MODEL = secret("GEMINI_MODEL") or "gemini-2.5-flash"
GMAIL = secret("GMAIL_ADDRESS")
PASSWORD = secret("GMAIL_APP_PASSWORD")

if "profile" not in st.session_state:
    st.markdown('<div class="hero"><h1>🧾 ReceiptWise</h1><p>Scan receipts. Understand spending. Split bills in seconds.</p></div>', unsafe_allow_html=True)
    st.subheader("Welcome — set up your tracker")
    with st.form("onboard"):
        name = st.text_input("Your name")
        email = st.text_input("Report email address", placeholder="you@example.com")
        currency = st.selectbox("Currency", list(CURRENCIES))
        go = st.form_submit_button("Start tracking →", type="primary")
    if go:
        if not name.strip() or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email.strip()):
            st.error("Enter your name and a valid email.")
        else:
            st.session_state.profile = {"name": name.strip()[:80], "email": email.strip(), "currency": currency}
            st.session_state.expenses = []
            st.session_state.messages = []
            st.rerun()
    st.stop()

profile = st.session_state.profile
currency = profile["currency"]
records = st.session_state.expenses

with st.sidebar:
    st.title("🧾 ReceiptWise")
    st.write(f"**{profile['name']}**")
    st.caption(profile["email"])
    st.caption(f"Currency: {currency} · Session-only")
    st.divider()
    st.write(("🟢" if API_KEY else "⚪") + " Gemini vision & chat")
    st.write(("🟢" if GMAIL and PASSWORD else "⚪") + " Gmail delivery")
    st.caption("Set credentials in Streamlit Secrets. Manual tracking works without them.")
    st.download_button("⬇ Export CSV", expense_csv(records), "receiptwise_expenses.csv", "text/csv", use_container_width=True)
    st.caption("Receipt photos are sent to Gemini when scanned. Emails send only when requested.")

st.markdown('<div class="hero"><h1>Make every receipt count.</h1><p>From photo to spending insights — without the spreadsheets.</p></div>', unsafe_allow_html=True)
overview, scan_tab, expenses_tab, split_tab, chat_tab, email_tab = st.tabs(["📊 Overview", "📷 Scan receipt", "💳 Expenses", "👥 Split bill", "💬 AI chat", "✉️ Email report"])

with overview:
    total = sum(r["amount_minor"] for r in records)
    categories = {}
    for r in records:
        categories[r["category"]] = categories.get(r["category"], 0) + r["amount_minor"]
    a,b,c,d = st.columns(4)
    a.metric("Total spending", money(total,currency))
    b.metric("Expenses",len(records))
    c.metric("Average receipt",money(round(total/len(records)),currency) if records else money(0,currency))
    d.metric("Top category",max(categories,key=categories.get) if categories else "—")
    if records:
        x,y = st.columns(2)
        with x:
            st.subheader("By category")
            st.bar_chart(pd.DataFrame([{"Category":k,"Amount":v/100} for k,v in categories.items()]).set_index("Category"),horizontal=True)
        with y:
            st.subheader("Over time")
            daily = {}
            for r in records:
                daily[r["date"]] = daily.get(r["date"],0) + r["amount_minor"]/100
            st.line_chart(pd.DataFrame([{"Date":pd.Timestamp(k),"Amount":v} for k,v in sorted(daily.items())]).set_index("Date"))
        st.dataframe(pd.DataFrame([{"Date":r["date"],"Merchant":r["merchant"],"Category":r["category"],"Amount":money(r["amount_minor"],currency)} for r in sorted(records,key=lambda r:r["date"],reverse=True)[:8]]),hide_index=True,use_container_width=True)
    else:
        st.info("Scan a receipt or add your first expense to see insights.")

with scan_tab:
    st.subheader("Scan a receipt with Gemini")
    upload = st.file_uploader("Upload a JPG, PNG or WebP receipt (max 8 MB)",type=["jpg","jpeg","png","webp"])
    if upload:
        st.image(upload,width=320)
        if st.button("✨ Extract receipt",disabled=not bool(API_KEY),type="primary"):
            if upload.size > 8*1024*1024:
                st.error("Resize the image to less than 8 MB.")
            else:
                try:
                    with st.spinner("Reading receipt..."):
                        st.session_state.pending = parse_receipt(scan_receipt(upload.getvalue(),upload.type,API_KEY,MODEL),currency)
                    st.success("Review all amounts below before saving.")
                except Exception as exc:
                    st.error(f"Extraction failed: {exc}")
        if not API_KEY:
            st.warning("Set GEMINI_API_KEY in Streamlit Secrets to enable scanning.")
    if "pending" in st.session_state:
        p = st.session_state.pending
        st.subheader("Verify extracted details")
        if p["date"] is None:
            st.warning("Purchase date could not be read. Check the date below.")
        with st.form("confirm_scan"):
            merchant = st.text_input("Merchant",value=p["merchant"])
            when = st.date_input("Date",value=p["date"] or date.today())
            category = st.selectbox("Category",CATEGORIES,index=CATEGORIES.index(p["category"]))
            amount = st.number_input(f"Verified total ({currency})",min_value=0.0,value=p["amount_minor"]/100,format="%.2f")
            edited = st.data_editor(pd.DataFrame([{"Item":i["name"],"Amount":i["amount_minor"]/100} for i in p["items"]],columns=["Item","Amount"]),num_rows="dynamic",hide_index=True)
            if st.form_submit_button("✓ Save expense",type="primary"):
                try:
                    items = [{"name":str(row["Item"]),"amount_minor":to_minor(row["Amount"])} for _,row in edited.iterrows() if pd.notna(row["Amount"])]
                    records.append(make_expense(merchant,amount,when,category,"Gemini scan","Verified",items,currency))
                    del st.session_state.pending
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))

with expenses_tab:
    st.subheader("Add an expense manually")
    with st.form("manual"):
        merchant = st.text_input("Merchant or description")
        amount = st.number_input(f"Amount ({currency})",min_value=0.0,format="%.2f")
        when = st.date_input("Date",date.today())
        category = st.selectbox("Category",CATEGORIES)
        notes = st.text_input("Notes")
        if st.form_submit_button("+ Add expense",type="primary"):
            try:
                records.append(make_expense(merchant,amount,when,category,notes=notes,currency=currency))
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
    if records:
        st.divider()
        selected = st.multiselect("Filter by category",CATEGORIES)
        filtered = [r for r in records if not selected or r["category"] in selected]
        st.dataframe(pd.DataFrame([{"Date":r["date"],"Merchant":r["merchant"],"Category":r["category"],"Amount":money(r["amount_minor"],currency),"Source":r["source"]} for r in filtered]),hide_index=True,use_container_width=True)
        with st.expander("Delete an expense"):
            chosen = st.selectbox("Choose expense",list(range(len(records))),format_func=lambda i:f'{records[i]["merchant"]} · {money(records[i]["amount_minor"],currency)}')
            if st.button("Delete selected"):
                records.pop(chosen)
                st.rerun()

with split_tab:
    st.subheader("Split a receipt")
    if not records:
        st.info("Save an expense first.")
    else:
        idx = st.selectbox("Expense",list(range(len(records))),format_func=lambda i:f'{records[i]["merchant"]} · {money(records[i]["amount_minor"],currency)}')
        r = records[idx]
        people = [p.strip() for p in st.text_input("Participants, separated by commas","Alex, Sam").split(",") if p.strip()]
        valid = 2 <= len(people) <= 20 and len(set(people)) == len(people)
        mode = st.radio("Split method",["Equal","By item"],disabled=not bool(r["items"]),horizontal=True)
        assignments = {}
        if mode == "By item" and r["items"] and valid:
            for j,item in enumerate(r["items"]):
                assignments[j] = st.multiselect(f'{item["name"]} · {money(item["amount_minor"],currency)}',people,default=people,key=f'{r["id"]}_{j}')
        if not valid:
            st.warning("Enter 2–20 unique names.")
        if st.button("Calculate split",disabled=not valid):
            try:
                shares = split_by_item(r["amount_minor"],r["items"],assignments,people) if mode=="By item" else split_equal(r["amount_minor"],people)
                st.session_state.last_split = {"id":r["id"],"shares":shares}
            except ValueError as exc:
                st.error(str(exc))
        if st.session_state.get("last_split",{}).get("id")==r["id"]:
            st.dataframe(pd.DataFrame([{"Person":p,"Owes":money(v,currency)} for p,v in st.session_state.last_split["shares"].items()]),hide_index=True,use_container_width=True)
            st.caption("Remainder cents/paise are distributed exactly.")

with chat_tab:
    st.subheader("Ask your expense assistant")
    if not API_KEY:
        st.warning("Configure GEMINI_API_KEY to enable AI chat.")
    else:
        st.info(WELCOME_MESSAGE_TEMPLATE.format(name=profile["name"]))
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.write(msg["text"])
        prompt = st.chat_input("Ask about your spending...")
        if prompt:
            st.session_state.messages.append({"role":"user","text":prompt})
            with st.chat_message("user"):
                st.write(prompt)
            try:
                if "chat" not in st.session_state:
                    st.session_state.chat = new_chat(API_KEY,MODEL)
                ledger = json.dumps([{"date":r["date"],"merchant":r["merchant"],"category":r["category"],"amount_minor":r["amount_minor"]} for r in records])
                answer = st.session_state.chat.send_message(f"Verified ledger in {currency}: {ledger}\nQuestion: {prompt}").text or "No answer returned."
                st.session_state.messages.append({"role":"assistant","text":answer})
                with st.chat_message("assistant"):
                    st.write(answer)
            except Exception as exc:
                st.error(f"Gemini error: {exc}")

with email_tab:
    st.subheader("Send your expense report")
    if not records:
        st.info("Add expenses to generate a report.")
    else:
        report = expense_summary(records,currency,profile["name"])
        last = st.session_state.get("last_split")
        if last and st.checkbox("Include latest bill split",value=True):
            report += "\n\nLatest bill split:\n" + "\n".join(f'{p}: {money(v,currency)}' for p,v in last["shares"].items())
        st.text_area("Verified report",report,height=260)
        st.download_button("⬇ Download report",report,"receiptwise_report.txt","text/plain")
        if not GMAIL or not PASSWORD:
            st.warning("Set GMAIL_ADDRESS and GMAIL_APP_PASSWORD in Streamlit Secrets to enable sending.")
        if st.button("✉ Send to my email",disabled=not bool(GMAIL and PASSWORD),type="primary"):
            try:
                body = report
                if API_KEY:
                    try:
                        note = new_chat(API_KEY,MODEL).send_message(SUMMARY_REQUEST_PROMPT+"\n"+report).text
                        if note:
                            body += "\n\nAI observation (verify):\n"+note[:600]
                    except Exception:
                        pass
                send_email(profile["email"],"ReceiptWise expense report",body,GMAIL,PASSWORD)
                st.success(f'Report sent to {profile["email"]}')
            except Exception as exc:
                st.error(f"Email not sent: {exc}")
