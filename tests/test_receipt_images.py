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




class ReceiptDecodingTests(unittest.TestCase):
    def test_damaged_png_checksum_is_a_friendly_validation_error(self):
        data = bytearray(make_image("PNG"))
        data[data.index(b"IDAT") + 5] ^= 1
        with self.assertRaisesRegex(ValueError, "could not be opened"):
            read_receipt_image(FakeUpload(bytes(data)))

    def test_truncated_images_are_rejected(self):
        for fmt in ("JPEG", "PNG", "WEBP"):
            with self.subTest(format=fmt):
                buf = io.BytesIO()
                Image.new("RGB", (128, 128), "white").save(buf, fmt)
                with self.assertRaises(ValueError):
                    read_receipt_image(FakeUpload(buf.getvalue()[:-10]))

    def test_byte_limit_boundary(self):
        data = make_image("PNG")
        padded = data + b"\0" * (MAX_RECEIPT_BYTES - len(data))
        self.assertEqual(len(read_receipt_image(FakeUpload(padded))[0]), MAX_RECEIPT_BYTES)
        with self.assertRaisesRegex(ValueError, "larger than 10 MB"):
            read_receipt_image(FakeUpload(padded + b"\0"))

    def test_pixel_limit_boundary(self):
        from unittest.mock import patch
        from receipt_images import MAX_RECEIPT_PIXELS
        data = make_image("PNG")
        with patch("receipt_images.MAX_RECEIPT_PIXELS", 256):
            read_receipt_image(FakeUpload(data))
        with patch("receipt_images.MAX_RECEIPT_PIXELS", 255):
            with self.assertRaisesRegex(ValueError, "megapixels"):
                read_receipt_image(FakeUpload(data))
        self.assertEqual(MAX_RECEIPT_PIXELS, 20_000_000)

    def test_unsupported_and_animated_images(self):
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            read_receipt_image(FakeUpload(make_image("GIF")))
        buf = io.BytesIO()
        Image.new("RGB", (16, 16), "white").save(buf, "PNG", save_all=True,
              append_images=[Image.new("RGB", (16, 16), "black")])
        with self.assertRaisesRegex(ValueError, "Animated"):
            read_receipt_image(FakeUpload(buf.getvalue()))


if __name__ == "__main__":
    unittest.main()
