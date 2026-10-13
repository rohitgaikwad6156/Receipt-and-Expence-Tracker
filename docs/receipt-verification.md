# Receipt capture verification

## Automated checks

Install `requirements.txt` in a fresh Python 3.11 or 3.12 environment, then run:

```sh
python -m pip check
python -m unittest discover -s tests -v
```

The workflow runs these checks on pushes and pull requests. Tests use mocked Gemini,
camera inputs and delivery services. They verify actual app buttons, transactional
history, explicit retry, failover history replay and blocked delivery on failed analysis.
They do not establish real model accuracy, browser camera permissions or real delivery.
NumPy 2.2.6 is pinned because the unconstrained clean install selected 2.5.4 and
crashed on import during image rendering in the verification environment.

## Optional live API smoke test

Set `GEMINI_API_KEY` securely in your environment, optionally set `GEMINI_MODEL`, then:

```sh
python scripts/smoke_receipt.py /path/to/non-sensitive-receipt.jpg
```

This deliberately invokes the live API and may consume quota. It analyzes a receipt,
asks a follow-up split and generates a summary without sending email or WhatsApp.
Exit status 0 verifies that the API flow completed; manually compare the amounts
against the receipt to establish accuracy. The script never prints the API key.

## HTTPS device and delivery checks required before merging

Deploy the PR branch to an HTTPS preview using the deployment's existing secrets.
Record the URL, deployed commit, date, device, OS and browser for every check.

- [ ] On a phone, allow camera access, capture a known receipt and analyze it.
- [ ] On a laptop, capture and analyze a receipt with its webcam.
- [ ] Deny camera permission: verify that Upload Receipt still works.
- [ ] Retake a photo and verify that the newly captured image is analyzed.
- [ ] Upload valid JPEG, PNG and WebP images. Repeat using chat attachments.
- [ ] Verify a receipt with known merchant, items, currency, tax, discounts and total.
- [ ] Verify unreadable data is identified as unknown; do not approve fabricated amounts.
- [ ] Ask for a split and compare rounded shares with the receipt total.
- [ ] Change an unrelated sidebar field; ensure it does not resubmit the receipt.
- [ ] Use an invalid API key and exhaust/mock quota: show an error, save no analysis,
      correct the problem and retry once. The receipt should appear exactly once.
- [ ] Ask a receipt follow-up and generate a summary; confirm both keep receipt context.
- [ ] Send the summary to your own test email and WhatsApp. Confirm receipt amounts
      in the received messages. Do not use other people's destinations for this test.
- [ ] Confirm corrupt, animated, over-20-megapixel and over-10-MiB images are rejected.

The byte ceiling is exactly 10 * 1024 * 1024 bytes (10 MiB), inclusive.
Streamlit's server upload limit is also set to 10 MiB. The decoded image ceiling is
20,000,000 pixels. Supported images must be a single frame and fully decode.

## Evidence record

- Automated checks: record command, Python/dependency versions and results.
- Live API: pending until run with configured credentials.
- HTTPS preview and physical phone/laptop cameras: pending until device testing.
- Real email/WhatsApp delivery: pending until confirmed in your test accounts.

Keep pending checks explicit in the PR; a skipped CodeRabbit review is not validation.
