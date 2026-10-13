"""Run the real Streamlit app with mocked camera, network and delivery services."""
import io
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from PIL import Image
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app.py")


class Upload:
    def __init__(self, data):
        self.data = data

    def getvalue(self):
        return self.data


def photo():
    buf = io.BytesIO()
    Image.new("RGB", (128, 128), "white").save(buf, "JPEG")
    return Upload(buf.getvalue())


class AppReceiptTests(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.client.models.generate_content.return_value = SimpleNamespace(text="Test Store; Total INR 120")
        self.upload = photo()
        self.camera_photo = self.upload
        self.incoming = []
        self.patches = [
            patch("google.genai.Client", return_value=self.client),
            patch("streamlit.camera_input", side_effect=lambda *a, **k: self.camera_photo),
            patch("streamlit.file_uploader", side_effect=lambda *a, **k: self.upload),
            patch("streamlit.chat_input", side_effect=lambda *a, **k: self.incoming.pop(0) if self.incoming else None),
            patch("notify.send_email", return_value=(True, "accepted")),
            patch("notify.send_whatsapp", return_value=(True, "accepted")),
        ]
        self.mocks = [p.start() for p in self.patches]
        self.addCleanup(lambda: [p.stop() for p in reversed(self.patches)])
        # cache_resource is process-wide; clear it between fake clients.
        import streamlit as st
        st.cache_resource.clear()
        self.app = AppTest.from_file(APP, default_timeout=15)
        initial_state = {
            "onboarded": True, "name": "Test", "custom_api_key": "test-only-not-real",
            "whatsapp_number": "+911234567890", "email_address": "test@example.com",
            "currency": "INR (₹)", "messages": [], "gemini_history": [],
        }
        for key, value in initial_state.items():
            self.app.session_state[key] = value
        self.app.run()
        self.assertEqual(len(self.app.exception), 0)

    def click_label(self, label):
        next(b for b in self.app.button if b.label == label).click().run()
        self.assertEqual(len(self.app.exception), 0)

    def test_camera_and_upload_save_once_and_reruns_do_not_resend(self):
        for key in ("analyze_camera_receipt", "analyze_uploaded_receipt"):
            self.app.button(key=key).click().run()
            self.assertEqual(len(self.app.exception), 0)
        self.assertEqual(self.client.models.generate_content.call_count, 2)
        messages = self.app.session_state["messages"]
        self.assertEqual(sum(m["kind"] == "image" for m in messages), 2)
        self.app.run()
        self.assertEqual(self.client.models.generate_content.call_count, 2)

    def test_invalid_camera_upload_and_chat_make_zero_requests(self):
        self.upload = Upload(b"not a photo")
        self.camera_photo = self.upload
        for key in ("analyze_camera_receipt", "analyze_uploaded_receipt"):
            self.app.button(key=key).click().run()
            self.assertGreater(len(self.app.error), 0)
            self.assertEqual(len(self.app.exception), 0)
        self.incoming.append(SimpleNamespace(text="Analyze", files=[self.upload]))
        self.app.run()
        self.assertGreater(len(self.app.error), 0)
        self.assertEqual(len(self.app.exception), 0)
        self.client.models.generate_content.assert_not_called()
        self.assertEqual(self.app.session_state["gemini_history"], [])

    def test_chat_failure_has_working_retry_without_duplicate_receipt(self):
        self.client.models.generate_content.side_effect = TimeoutError()
        self.incoming.append(SimpleNamespace(text="Split in 3", files=[self.upload]))
        self.app.run()
        self.assertGreater(len(self.app.error), 0)
        self.assertEqual(self.app.session_state["gemini_history"], [])
        self.client.models.generate_content.side_effect = None
        self.app.button(key="retry_chat_request").click().run()
        self.assertEqual(len(self.app.exception), 0)
        self.assertEqual(sum(m["kind"] == "image" for m in self.app.session_state["messages"]), 1)
        self.assertEqual(len(self.app.session_state["gemini_history"]), 2)
        self.assertNotIn("pending_chat", self.app.session_state._state.filtered_state)
        self.app.run()
        self.assertEqual(self.client.models.generate_content.call_count, 2)

    def test_successful_summaries_include_receipt_and_deliver(self):
        self.app.button(key="analyze_camera_receipt").click().run()
        self.click_label("✉️ Send to Email")
        self.click_label("📱 Send to WhatsApp")
        self.mocks[4].assert_called_once()
        self.mocks[5].assert_called_once()
        request = self.client.models.generate_content.call_args.kwargs
        self.assertIsNotNone(request["contents"][0].parts[0].inline_data)

    def test_failed_summary_never_delivers_email_or_whatsapp(self):
        self.app.button(key="analyze_camera_receipt").click().run()
        self.client.models.generate_content.side_effect = TimeoutError()
        for label in ("✉️ Send to Email", "📱 Send to WhatsApp"):
            self.click_label(label)
            self.assertGreater(len(self.app.error), 0)
        self.mocks[4].assert_not_called()
        self.mocks[5].assert_not_called()
        self.assertEqual(len(self.app.session_state["gemini_history"]), 2)

    def test_missing_camera_keeps_capture_button_disabled_and_upload_available(self):
        self.camera_photo = None
        self.app.run()
        self.assertTrue(self.app.button(key="analyze_camera_receipt").disabled)
        self.assertFalse(self.app.button(key="analyze_uploaded_receipt").disabled)
        self.client.models.generate_content.assert_not_called()
        self.app.button(key="analyze_uploaded_receipt").click().run()
        self.assertEqual(len(self.app.exception), 0)
        self.client.models.generate_content.assert_called_once()


if __name__ == "__main__":
    unittest.main()
