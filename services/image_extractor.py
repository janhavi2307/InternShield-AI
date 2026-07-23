from functools import lru_cache
from io import BytesIO
from pathlib import Path

import easyocr
import numpy as np
from PIL import Image, UnidentifiedImageError


MAX_IMAGE_SIZE = 5 * 1024 * 1024
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

Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


class ImageExtractionError(Exception):
    pass


@lru_cache(maxsize=1)
def get_ocr_reader():
    return easyocr.Reader(
        ["en"],
        gpu=False,
    )


def validate_image_filename(filename: str) -> None:
    if not filename:
        raise ImageExtractionError(
            "Select an image to upload."
        )

    extension = Path(filename).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise ImageExtractionError(
            "Upload a PNG, JPG, JPEG or WEBP image."
        )


def extract_image_text(file_storage) -> str:
    validate_image_filename(file_storage.filename)

    file_bytes = file_storage.read()

    if not file_bytes:
        raise ImageExtractionError(
            "The uploaded image is empty."
        )

    if len(file_bytes) > MAX_IMAGE_SIZE:
        raise ImageExtractionError(
            "The image must be smaller than 5 MB."
        )

    try:
        with Image.open(BytesIO(file_bytes)) as image:
            image.verify()

        with Image.open(BytesIO(file_bytes)) as image:
            if image.format not in ALLOWED_FORMATS:
                raise ImageExtractionError(
                    "The uploaded file is not a supported image."
                )

            image = image.convert("RGB")

            if (
                image.width > MAX_IMAGE_WIDTH
                or image.height > MAX_IMAGE_HEIGHT
            ):
                image.thumbnail(
                    (
                        MAX_IMAGE_WIDTH,
                        MAX_IMAGE_HEIGHT,
                    )
                )

            image_array = np.array(image)

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

    try:
        reader = get_ocr_reader()

        detected_lines = reader.readtext(
            image_array,
            detail=0,
            paragraph=True,
        )

    except Exception as error:
        raise ImageExtractionError(
            "Text recognition could not be completed."
        ) from error

    extracted_text = "\n".join(
        line.strip()
        for line in detected_lines
        if line and line.strip()
    ).strip()

    if len(extracted_text) < 20:
        raise ImageExtractionError(
            "Very little readable text was found in the image. "
            "Upload a clearer screenshot."
        )

    return extracted_text[:MAX_EXTRACTED_CHARACTERS]