"""
InternShield AI - lightweight image text extraction.

Production design:
- validates uploaded PNG/JPG/JPEG/WEBP files locally
- sends image bytes to Gemini for text transcription
- avoids EasyOCR / PyTorch in the Flask process
- keeps the same public API used by app.py:
    ImageExtractionError
    extract_image_text(file_storage)
"""

from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError

try:
    from google import genai
    from google.genai import types
except Exception:
    genai = None
    types = None


MAX_IMAGE_SIZE = 4 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000
MAX_IMAGE_WIDTH = 2400
MAX_IMAGE_HEIGHT = 2400
MAX_EXTRACTED_CHARACTERS = 50_000

ALLOWED_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
}

ALLOWED_FORMATS = {
    "PNG",
    "JPEG",
    "WEBP",
}

FORMAT_TO_MIME = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "WEBP": "image/webp",
}

Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


class ImageExtractionError(Exception):
    pass


def _timeout_ms() -> int:
    raw_value = (
        os.getenv("GEMINI_TIMEOUT_MS")
        or "15000"
    ).strip()

    try:
        timeout = int(raw_value)
    except ValueError:
        timeout = 15000

    return max(
        3000,
        min(
            timeout,
            45000,
        ),
    )


def _ocr_model() -> str:
    return (
        os.getenv("GEMINI_OCR_MODEL")
        or os.getenv("GEMINI_MODEL")
        or "gemini-3.5-flash-lite"
    ).strip()


def validate_image_filename(
    filename: str,
) -> None:
    if not filename:
        raise ImageExtractionError(
            "Select an image to upload."
        )

    extension = (
        Path(filename)
        .suffix
        .lower()
    )

    if extension not in ALLOWED_EXTENSIONS:
        raise ImageExtractionError(
            "Upload a PNG, JPG, JPEG or WEBP image."
        )


def _validate_image_bytes(
    file_bytes: bytes,
) -> str:
    """
    Validate the actual image content and return its MIME type.
    """

    try:
        with Image.open(
            BytesIO(file_bytes)
        ) as image:
            image.verify()

        with Image.open(
            BytesIO(file_bytes)
        ) as image:
            image_format = (
                image.format
                or ""
            ).upper()

            if (
                image_format
                not in ALLOWED_FORMATS
            ):
                raise ImageExtractionError(
                    "The uploaded file is not "
                    "a supported image."
                )

            if (
                image.width > MAX_IMAGE_WIDTH
                or image.height > MAX_IMAGE_HEIGHT
            ):
                # Large screenshots are still accepted.
                # Gemini can read them directly without us
                # allocating a large NumPy array in memory.
                pass

            return FORMAT_TO_MIME[
                image_format
            ]

    except Image.DecompressionBombError as error:
        raise ImageExtractionError(
            "The image dimensions are too large."
        ) from error

    except UnidentifiedImageError as error:
        raise ImageExtractionError(
            "The uploaded file is not a valid image."
        ) from error

    except ImageExtractionError:
        raise

    except Exception as error:
        raise ImageExtractionError(
            "The image could not be processed."
        ) from error


def _extract_with_gemini(
    *,
    file_bytes: bytes,
    mime_type: str,
) -> str:
    if (
        genai is None
        or types is None
    ):
        raise ImageExtractionError(
            "Image text recognition is temporarily "
            "unavailable."
        )

    api_key = (
        os.getenv("GEMINI_API_KEY")
        or ""
    ).strip()

    if not api_key:
        raise ImageExtractionError(
            "Image text recognition is not configured."
        )

    enabled = (
        os.getenv(
            "GEMINI_AI_ENABLED",
            "true",
        )
        or "true"
    ).strip().lower()

    if enabled in {
        "0",
        "false",
        "no",
        "off",
        "disabled",
    }:
        raise ImageExtractionError(
            "Image text recognition is currently disabled."
        )

    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(
            timeout=_timeout_ms()
        ),
    )

    prompt = (
        "Transcribe all readable text from this internship-related "
        "screenshot or image. Return only the extracted text, preserving "
        "the natural reading order and useful line breaks. Do not "
        "summarize, explain, classify, infer missing words, or add any "
        "commentary. If a word is genuinely unreadable, omit it rather "
        "than guessing."
    )

    try:
        response = (
            client.models.generate_content(
                model=_ocr_model(),
                contents=[
                    types.Part.from_bytes(
                        data=file_bytes,
                        mime_type=mime_type,
                    ),
                    prompt,
                ],
            )
        )

        extracted_text = (
            getattr(
                response,
                "text",
                "",
            )
            or ""
        ).strip()

    except Exception as error:
        raise ImageExtractionError(
            "Text recognition could not be completed "
            "right now. Please try again."
        ) from error

    finally:
        try:
            client.close()
        except Exception:
            pass

    if len(extracted_text) < 20:
        raise ImageExtractionError(
            "Very little readable text was found in "
            "the image. Upload a clearer screenshot."
        )

    return extracted_text[
        :MAX_EXTRACTED_CHARACTERS
    ]


def extract_image_text(
    file_storage,
) -> str:
    """
    Extract text from an uploaded internship screenshot/image.

    The function signature intentionally matches the previous
    EasyOCR implementation so app.py does not need to change.
    """

    validate_image_filename(
        file_storage.filename
    )

    file_bytes = (
        file_storage.read()
    )

    if not file_bytes:
        raise ImageExtractionError(
            "The uploaded image is empty."
        )

    if len(file_bytes) > MAX_IMAGE_SIZE:
        raise ImageExtractionError(
            "The image must be smaller than 4 MB."
        )

    mime_type = _validate_image_bytes(
        file_bytes
    )

    return _extract_with_gemini(
        file_bytes=file_bytes,
        mime_type=mime_type,
    )
