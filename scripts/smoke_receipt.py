"""Opt-in live Gemini smoke test. Reads its key from the environment; never sends messages."""
import argparse
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from google import genai
from google.genai import types
from prompts import SUMMARY_REQUEST_PROMPT
from receipt_service import analyze_receipt, generate_answer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="A non-sensitive receipt image with a known total")
    args = parser.parse_args()
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        parser.error("Set GEMINI_API_KEY in your environment first; do not paste it in the command.")
    try:
        data = args.image.read_bytes()
    except OSError:
        parser.error("Could not read the receipt image.")
    class Upload:
        def getvalue(self):
            return data
    history, messages = [], []
    models = [os.getenv("GEMINI_MODEL", "gemini-flash-latest")]
    with genai.Client(api_key=key, http_options=types.HttpOptions(timeout=30_000)) as client:
        result = analyze_receipt(client, models, history, messages, Upload())
        if not result.ok:
            print(result.error, file=sys.stderr)
            return 1
        print("Receipt analysis:\n" + result.text)
        for label, prompt in (("Follow-up", "Split this receipt equally between 3 people."),
                              ("Summary", SUMMARY_REQUEST_PROMPT)):
            result = generate_answer(client, models, history, [prompt])
            if not result.ok:
                print(result.error, file=sys.stderr)
                return 1
            print(f"\n{label}:\n{result.text}")
    print("\nAPI flow completed. Compare extracted amounts with the original receipt manually.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
