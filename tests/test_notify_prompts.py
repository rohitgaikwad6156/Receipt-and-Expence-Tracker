import unittest
from prompts import SYSTEM_PROMPT, WELCOME_MESSAGE_TEMPLATE, SUMMARY_REQUEST_PROMPT
from notify import clean_whatsapp_text

class PromptsAndNotifyTests(unittest.TestCase):
    def test_prompts_presence(self):
        self.assertIn("ReceiptWise", SYSTEM_PROMPT)
        self.assertIn("receipt", SYSTEM_PROMPT.lower())
        self.assertIn("split", SYSTEM_PROMPT.lower())
        
        welcome = WELCOME_MESSAGE_TEMPLATE.format(name="Alex", button_label="Send to Email", channel="Email")
        self.assertIn("Alex", welcome)
        self.assertIn("Send to Email", welcome)
        
        self.assertIn("Summarize every receipt", SUMMARY_REQUEST_PROMPT)

    def test_clean_whatsapp_text(self):
        text = "  Hello   world \n\n this is   a   test  "
        cleaned = clean_whatsapp_text(text)
        self.assertEqual(cleaned, "Hello world this is a test")
        
        empty = clean_whatsapp_text("")
        self.assertEqual(empty, "No expense summary available.")
        
        long_text = "a" * 2000
        capped = clean_whatsapp_text(long_text)
        self.assertTrue(len(capped) <= 1503)
        self.assertTrue(capped.endswith("..."))

if __name__ == "__main__":
    unittest.main()
