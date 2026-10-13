"""Receipt requests with explicit errors and transactional conversation history."""

from dataclasses import dataclass

import httpx
from google.genai import types

from prompts import SYSTEM_PROMPT
from receipt_images import read_receipt_image, receipt_analysis_prompt


@dataclass(frozen=True)
class AnalysisResult:
    text: str = ""
    error: str = ""

    @property
    def ok(self):
        return bool(self.text) and not self.error


def generate_answer(client, models, history, parts):
    """Replay successful turns on every model; commit only a successful response.

    No SDK chat object owns the history, so a failed request cannot insert a
    partial turn or lose receipts when switching models. Errors never contain
    raw SDK exceptions, which can include sensitive configuration.
    """
    if client is None:
        return AnalysisResult(error="Configure a Gemini API key before analyzing receipts.")
    user_turn = types.Content(role="user", parts=[
        types.Part.from_text(text=part) if isinstance(part, str) else part
        for part in parts
    ])
    error_message = "No Gemini model is configured."
    for model in dict.fromkeys(model for model in models if model):
        try:
            response = client.models.generate_content(
                model=model,
                contents=[*history, user_turn],
                config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
            )
            text = (response.text or "").strip() if response else ""
            if not text:
                return AnalysisResult(error="Gemini returned no analysis. Please retry or use a clearer photo.")
            history.extend([
                user_turn,
                types.Content(role="model", parts=[types.Part.from_text(text=text)]),
            ])
            return AnalysisResult(text=text)
        except (TimeoutError, httpx.TimeoutException):
            return AnalysisResult(error="Gemini timed out. Please retry; the receipt was not saved.")
        except Exception as exc:
            code = getattr(exc, "code", None)
            if code in (404, 429, 500, 502, 503, 504):
                error_message = "Gemini is unavailable or its quota is exhausted. Please retry later."
                continue
            if code in (400, 401, 403):
                return AnalysisResult(error="Gemini rejected the request. Check your API key, model access and image.")
            return AnalysisResult(error="Gemini could not analyze this request. Please retry.")
    return AnalysisResult(error=error_message)


def analyze_receipt(client, models, history, messages, uploaded_file, notes="", source="upload"):
    """Validate first and save receipt/UI entries only after Gemini succeeds."""
    try:
        data, mime = read_receipt_image(uploaded_file)
    except ValueError as exc:
        return AnalysisResult(error=str(exc))
    result = generate_answer(client, models, history, [
        types.Part.from_bytes(data=data, mime_type=mime),
        receipt_analysis_prompt(notes),
    ])
    if result.ok:
        caption = "Analyze the receipt I just photographed." if source == "camera" else "Analyze my uploaded receipt."
        if str(notes or "").strip():
            caption += f" Instructions: {str(notes).strip()[:300]}"
        messages.extend([
            {"role": "user", "kind": "image", "content": data},
            {"role": "user", "kind": "text", "content": caption},
            {"role": "assistant", "kind": "text", "content": result.text},
        ])
    return result
