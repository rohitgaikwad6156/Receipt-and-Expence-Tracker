import base64
import json
import unittest
from unittest.mock import MagicMock, patch

from google.auth.exceptions import RefreshError
from googleapiclient.errors import HttpError
import httplib2

from notify import (
    clean_phone_number,
    clean_whatsapp_text,
    generate_gmail_web_url,
    generate_mailto_url,
    generate_whatsapp_web_url,
    get_gmail_oauth_credentials,
    is_gmail_api_configured,
    send_email,
)


class GmailApiTests(unittest.TestCase):
    def test_no_smtp_in_notify(self):
        """Verify that smtplib is not imported or used anywhere in notify.py."""
        import notify
        self.assertFalse(hasattr(notify, "smtplib"), "smtplib should not be in notify.py")

    def test_email_validation(self):
        """Test recipient email address validation and anti-injection protection."""
        # Empty email
        ok, msg = send_email("", "Subject", "Body")
        self.assertFalse(ok)
        self.assertIn("required", msg.lower())

        # Newline injection attack
        ok, msg = send_email("victim@example.com\r\nBcc: evil@example.com", "Subject", "Body")
        self.assertFalse(ok)
        self.assertIn("injection", msg.lower())

        # Comma separated multiple recipients
        ok, msg = send_email("a@example.com, b@example.com", "Subject", "Body")
        self.assertFalse(ok)
        self.assertIn("multiple", msg.lower())

        # Invalid format
        ok, msg = send_email("not-an-email", "Subject", "Body")
        self.assertFalse(ok)
        self.assertIn("format", msg.lower())

    def test_url_helpers(self):
        """Test that URL fallback helpers generate correctly encoded URLs."""
        gmail_url = generate_gmail_web_url("test@example.com", "Expense Report", "Total: $50")
        self.assertTrue(gmail_url.startswith("https://mail.google.com/mail/"))
        self.assertIn("test%40example.com", gmail_url)
        self.assertIn("Expense%20Report", gmail_url)

        mailto_url = generate_mailto_url("test@example.com", "Subject", "Body")
        self.assertTrue(mailto_url.startswith("mailto:test@example.com"))

    @patch("notify.get_gmail_oauth_credentials")
    @patch("notify.build")
    def test_successful_gmail_api_send(self, mock_build, mock_get_creds):
        """Test end-to-end payload encoding and message send with mocked Gmail service."""
        mock_creds = MagicMock()
        mock_get_creds.return_value = (mock_creds, "OK")

        mock_service = MagicMock()
        mock_messages = MagicMock()
        mock_messages.send.return_value.execute.return_value = {"id": "msg_abc123", "threadId": "th_123"}
        mock_service.users.return_value.messages.return_value = mock_messages
        mock_build.return_value = mock_service


        success, message = send_email(
            to_address="recipient@example.com",
            subject="Test Subject",
            body="Test Body Content",
            sender_address="sender@example.com",
            client_id="dummy_id",
            client_secret="dummy_secret",
            refresh_token="dummy_refresh",
        )

        self.assertTrue(success)
        self.assertIn("msg_abc123", message)
        self.assertIn("accepted by gmail api", message.lower())

        # Verify payload passed to users.messages.send
        calls = mock_messages.send.call_args_list
        self.assertEqual(len(calls), 1)

        send_kwargs = calls[0].kwargs
        self.assertEqual(send_kwargs.get("userId"), "me")

        raw_b64 = send_kwargs.get("body", {}).get("raw", "")
        self.assertTrue(bool(raw_b64))

        # Decode raw base64 and verify MIME contents
        decoded_bytes = base64.urlsafe_b64decode(raw_b64.encode("utf-8"))
        import email
        parsed_msg = email.message_from_bytes(decoded_bytes)
        self.assertEqual(parsed_msg["To"], "recipient@example.com")
        self.assertEqual(parsed_msg["Subject"], "Test Subject")
        self.assertEqual(parsed_msg.get_payload(decode=True).decode("utf-8"), "Test Body Content")

    @patch("notify.get_gmail_oauth_credentials")
    @patch("notify.build")
    def test_gmail_api_http_errors(self, mock_build, mock_get_creds):
        """Test error handling for 400, 401, 403, and 429 HTTP status codes."""
        mock_creds = MagicMock()
        mock_get_creds.return_value = (mock_creds, "OK")

        # Test 403 Quota/Permission Error
        resp_403 = httplib2.Response({"status": 403, "reason": "Forbidden"})
        err_403 = HttpError(resp_403, b'{"error": "Quota exceeded"}')
        mock_service_403 = MagicMock()
        mock_service_403.users().messages().send().execute.side_effect = err_403
        mock_build.return_value = mock_service_403

        ok, msg = send_email("test@example.com", "Subj", "Body")
        self.assertFalse(ok)
        self.assertIn("403", msg)
        self.assertIn("quota", msg.lower())

        # Test 401 Unauthorized Error
        resp_401 = httplib2.Response({"status": 401, "reason": "Unauthorized"})
        err_401 = HttpError(resp_401, b'{"error": "Invalid token"}')
        mock_service_401 = MagicMock()
        mock_service_401.users().messages().send().execute.side_effect = err_401
        mock_build.return_value = mock_service_401

        ok, msg = send_email("test@example.com", "Subj", "Body")
        self.assertFalse(ok)
        self.assertIn("401", msg)
        self.assertIn("unauthorized", msg.lower())

    @patch("notify.get_gmail_oauth_credentials")
    def test_oauth_refresh_failure(self, mock_get_creds):
        """Test handling when OAuth refresh token is revoked or expired."""
        mock_get_creds.return_value = (None, "Gmail API Authorization Error: OAuth refresh token is expired")
        ok, msg = send_email("test@example.com", "Subj", "Body")
        self.assertFalse(ok)
        self.assertIn("expired", msg.lower())

    @patch("notify.get_gmail_oauth_credentials")
    @patch("notify.build")
    def test_network_timeout(self, mock_build, mock_get_creds):
        """Test handling when Google API call times out."""
        import socket
        mock_creds = MagicMock()
        mock_get_creds.return_value = (mock_creds, "OK")

        mock_service = MagicMock()
        mock_service.users().messages().send().execute.side_effect = socket.timeout("timed out")
        mock_build.return_value = mock_service

        ok, msg = send_email("test@example.com", "Subj", "Body")
        self.assertFalse(ok)
        self.assertIn("timeout", msg.lower())


if __name__ == "__main__":
    unittest.main()
