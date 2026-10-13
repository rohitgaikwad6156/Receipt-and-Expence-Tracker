import io
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock

import httpx
from PIL import Image

from prompts import SUMMARY_REQUEST_PROMPT
from receipt_service import analyze_receipt, generate_answer


class Upload:
    def __init__(self, data):
        self.data = data
        self.type = "image/png"  # Deliberately wrong: bytes are JPEG.

    def getvalue(self):
        return self.data


def receipt_photo():
    buf = io.BytesIO()
    Image.new("RGB", (128, 128), "white").save(buf, "JPEG")
    return Upload(buf.getvalue())


class APIError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__("private API key must never appear in the UI")


class ReceiptServiceTests(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.client.models.generate_content.return_value = SimpleNamespace(text="Store: Test; Total: INR 120")
        self.history, self.messages = [], []
        self.models = ["primary", "fallback"]

    def scan(self, photo=None, source="camera"):
        return analyze_receipt(self.client, self.models, self.history, self.messages,
                               photo or receipt_photo(), "Split between 3", source)

    def test_all_entry_points_use_verified_bytes_and_commit_one_receipt(self):
        for source in ("camera", "upload", "chat"):
            with self.subTest(source=source):
                self.setUp()
                photo = receipt_photo()
                result = self.scan(photo, source)
                self.assertTrue(result.ok)
                request = self.client.models.generate_content.call_args.kwargs
                parts = request["contents"][-1].parts
                self.assertEqual(parts[0].inline_data.data, photo.data)
                self.assertEqual(parts[0].inline_data.mime_type, "image/jpeg")
                self.assertIn("Split between 3", parts[1].text)
                self.assertEqual(len(self.history), 2)
                self.assertEqual(len(self.messages), 3)
                self.assertEqual(self.client.models.generate_content.call_count, 1)

    def test_invalid_images_never_call_gemini(self):
        for data in (b"invalid", b"", receipt_photo().data[:-2], b"x" * (10 * 1024 * 1024 + 1)):
            with self.subTest(size=len(data)):
                result = self.scan(Upload(data))
                self.assertFalse(result.ok)
                self.assertEqual(self.history, [])
                self.assertEqual(self.messages, [])
        self.client.models.generate_content.assert_not_called()

    def test_failure_does_not_commit_and_retry_commits_once(self):
        self.client.models.generate_content.side_effect = [APIError(401), SimpleNamespace(text="Total: INR 120")]
        result = self.scan()
        self.assertFalse(result.ok)
        self.assertNotIn("private", result.error)
        self.assertEqual(self.history, [])
        self.assertEqual(self.messages, [])
        self.assertTrue(self.scan().ok)
        self.assertEqual(len(self.messages), 3)
        self.assertEqual(len(self.history), 2)

    def test_timeout_empty_quota_and_unexpected_failure_are_explicit(self):
        for error in (TimeoutError(), httpx.ReadTimeout("private"), APIError(429), RuntimeError("private")):
            with self.subTest(error=type(error).__name__):
                self.client.models.generate_content.side_effect = error
                self.assertFalse(self.scan().ok)
                self.assertEqual(self.messages, [])
                self.assertEqual(self.history, [])
        self.client.models.generate_content.side_effect = None
        for text in (None, "", "   "):
            self.client.models.generate_content.return_value = SimpleNamespace(text=text)
            self.assertFalse(self.scan().ok)
            self.assertEqual(self.history, [])

    def test_failover_preserves_receipt_followup_and_summary_context(self):
        self.scan()
        self.assertTrue(generate_answer(self.client, self.models, self.history, ["Who owes what?"]).ok)
        saved = list(self.history)
        self.client.models.generate_content.side_effect = [APIError(404), SimpleNamespace(text="Expense summary: INR 120")]
        result = generate_answer(self.client, self.models, self.history, [SUMMARY_REQUEST_PROMPT])
        self.assertTrue(result.ok)
        calls = self.client.models.generate_content.call_args_list[-2:]
        for call in calls:
            self.assertEqual(call.kwargs["contents"][:-1], saved)
            self.assertEqual(call.kwargs["contents"][0].parts[0].inline_data.data, receipt_photo().data)
        self.assertEqual(calls[1].kwargs["model"], "fallback")
        self.assertEqual(len(self.history), len(saved) + 2)

    def test_failed_followup_keeps_previous_successful_history(self):
        self.scan()
        saved = list(self.history)
        self.client.models.generate_content.side_effect = APIError(429)
        self.assertFalse(generate_answer(self.client, self.models, self.history, ["Summary"]).ok)
        self.assertEqual(self.history, saved)

    def test_missing_client_is_explicit(self):
        result = generate_answer(None, self.models, self.history, ["receipt"])
        self.assertFalse(result.ok)
        self.assertEqual(self.history, [])


if __name__ == "__main__":
    unittest.main()
