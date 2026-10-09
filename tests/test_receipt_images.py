"""Tests for capturing and validating receipts before Gemini analysis."""

import io
import unittest

from PIL import Image

from receipt_images import (
    MAX_RECEIPT_BYTES,
    read_receipt_image,
    receipt_analysis_prompt,
)


class FakeUpload:
    def __init__(self, data, file_type="application/octet-stream"):
        self._data = data
        self.type = file_type

    def getvalue(self):
        return self._data


def make_image(fmt):
    output = io.BytesIO()
    Image.new("RGB", (16, 16), color="white").save(output, format=fmt)
    return output.getvalue()


class ReceiptImageTests(unittest.TestCase):
    def test_camera_jpeg_uses_verified_mime_type(self):
        data = make_image("JPEG")
        received, mime = read_receipt_image(FakeUpload(data, "image/png"))
        self.assertEqual(data, received)
        self.assertEqual(mime, "image/jpeg")

    def test_uploaded_png(self):
        _, mime = read_receipt_image(FakeUpload(make_image("PNG")))
        self.assertEqual(mime, "image/png")

    def test_uploaded_webp(self):
        _, mime = read_receipt_image(FakeUpload(make_image("WEBP")))
        self.assertEqual(mime, "image/webp")

    def test_no_image(self):
        with self.assertRaisesRegex(ValueError, "Take a photo"):
            read_receipt_image(None)

    def test_empty_image(self):
        with self.assertRaisesRegex(ValueError, "empty"):
            read_receipt_image(FakeUpload(b""))

    def test_invalid_image(self):
        with self.assertRaisesRegex(ValueError, "could not be opened"):
            read_receipt_image(FakeUpload(b"not a photo"))

    def test_corrupt_jpeg(self):
        with self.assertRaises(ValueError):
            read_receipt_image(FakeUpload(b"\xff\xd8\xffinvalid"))

    def test_oversized_image(self):
        with self.assertRaisesRegex(ValueError, "larger than 10 MB"):
            read_receipt_image(FakeUpload(b"x" * (MAX_RECEIPT_BYTES + 1)))

    def test_prompt_lists_required_receipt_fields(self):
        prompt = receipt_analysis_prompt("Split with 3 friends")
        self.assertIn("final total", prompt)
        self.assertIn("merchant", prompt)
        self.assertIn("Split with 3 friends", prompt)
        self.assertIn("unknown rather than guessing", prompt)

    def test_prompt_limits_optional_notes(self):
        prompt = receipt_analysis_prompt("x" * 1000)
        self.assertNotIn("x" * 301, prompt)
        self.assertIn("x" * 300, prompt)


if __name__ == "__main__":
    unittest.main()
