import json
import streamlit as st
from google import genai
from google.genai import types
from prompts import EXTRACTION_PROMPT, SYSTEM_PROMPT

@st.cache_resource(show_spinner=False)
def get_client(api_key):
    return genai.Client(api_key=api_key)

def scan_receipt(data, mime, key, model):
    response = get_client(key).models.generate_content(
        model=model,
        contents=[types.Part.from_bytes(data=data, mime_type=mime), EXTRACTION_PROMPT],
        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0))
    if not response.text:
        raise ValueError("Empty response from Gemini")
    return json.loads(response.text)

def new_chat(key, model):
    return get_client(key).chats.create(
        model=model, config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT))
