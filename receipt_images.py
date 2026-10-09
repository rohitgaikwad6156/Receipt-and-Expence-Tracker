"""Shared image validation and prompts for uploaded and camera-captured receipts."""

from io import BytesIO

from PIL import Image, UnidentifiedImageError

MAX_RECEIPT_BYTES = 10 * 1024 * 1024
SUPPORTED_FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}


def read_receipt_image(uploaded_file) -> tuple[bytes, str]:
    """Return verified image bytes and its MIME type for the Gemini API.

    Streamlit camera_input and file_uploader both return UploadedFile objects,
    which expose getvalue(). Validate file content instead of trusting its
    filename or browser-provided MIME type.
    """
    if uploaded_file is None:
        raise ValueError("Take a photo or choose a receipt image first.")

    try:
        image_bytes = uploaded_file.getvalue()
    except (AttributeError, OSError) as exc:
        raise ValueError("Could not read the selected image. Please try again.") from exc

    if not isinstance(image_bytes, bytes) or not image_bytes:
        raise ValueError("The receipt image is empty. Please take another photo.")
    if len(image_bytes) > MAX_RECEIPT_BYTES:
        raise ValueError("The receipt image is larger than 10 MB. Use a smaller image.")

    try:
        with Image.open(BytesIO(image_bytes)) as image:
            mime_type = SUPPORTED_FORMATS.get(image.format)
            if mime_type is None:
                raise ValueError("Unsupported image type. Use JPG, PNG, or WebP.")
            image.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError(
            "The image could not be opened. Retake the photo or upload a valid JPG, PNG, or WebP."
        ) from exc

    return image_bytes, mime_type


def receipt_analysis_prompt(split_note: str = "") -> str:
    """Ask Gemini to extract receipt details without inventing unreadable data."""
    instruction = (
        "Analyze the attached receipt or bill image. Return a clear, readable "
        "breakdown with: merchant/store, purchase date (if visible), currency, "
        "individual items and prices, subtotal, tax, tip, discounts, final total, "
        "and suggested spending category. Mark any unreadable or missing values "
        "as unknown rather than guessing. Mention when the itemized amounts do "
        "not match the final total. Do not invent a bill split unless requested."
    )
    notes = str(split_note or "").strip()[:300]
    if notes:
        instruction += f" The user also requests this split or analysis: {notes}"
    return instruction
