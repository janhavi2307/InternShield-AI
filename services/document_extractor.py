from pathlib import Path

import fitz


MAX_PDF_SIZE = 5 * 1024 * 1024
MAX_PDF_PAGES = 20
MAX_EXTRACTED_CHARACTERS = 50_000


class DocumentExtractionError(Exception):
    pass


def validate_pdf_filename(filename: str) -> None:
    if not filename:
        raise DocumentExtractionError(
            "Select a PDF document to upload."
        )

    extension = Path(filename).suffix.lower()

    if extension != ".pdf":
        raise DocumentExtractionError(
            "Only PDF documents are currently supported."
        )


def extract_pdf_text(file_storage) -> str:
    validate_pdf_filename(file_storage.filename)

    file_bytes = file_storage.read()

    if not file_bytes:
        raise DocumentExtractionError(
            "The uploaded PDF is empty."
        )

    if len(file_bytes) > MAX_PDF_SIZE:
        raise DocumentExtractionError(
            "The PDF must be smaller than 5 MB."
        )

    if not file_bytes.startswith(b"%PDF"):
        raise DocumentExtractionError(
            "The uploaded file is not a valid PDF document."
        )

    try:
        document = fitz.open(
            stream=file_bytes,
            filetype="pdf",
        )

    except Exception as error:
        raise DocumentExtractionError(
            "The PDF could not be opened."
        ) from error

    try:
        if document.needs_pass:
            raise DocumentExtractionError(
                "Password-protected PDFs are not supported."
            )

        if document.page_count == 0:
            raise DocumentExtractionError(
                "The PDF does not contain any pages."
            )

        if document.page_count > MAX_PDF_PAGES:
            raise DocumentExtractionError(
                "The PDF cannot contain more than 20 pages."
            )

        extracted_pages = []

        for page in document:
            page_text = page.get_text("text").strip()

            if page_text:
                extracted_pages.append(page_text)

        extracted_text = "\n\n".join(extracted_pages).strip()

        if not extracted_text:
            raise DocumentExtractionError(
                "No selectable text was found. The document "
                "may contain scanned images; image OCR will be "
                "added in the next stage."
            )

        if len(extracted_text) > MAX_EXTRACTED_CHARACTERS:
            extracted_text = extracted_text[
                :MAX_EXTRACTED_CHARACTERS
            ]

        return extracted_text

    finally:
        document.close()