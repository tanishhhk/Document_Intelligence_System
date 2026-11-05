from io import BytesIO
from pathlib import Path

from pypdf import PdfReader


def extract_pages(
    source: str | bytes,
    max_pages: int = 500,
    max_chars: int = 500_000,
) -> list[tuple[int, str]]:
    """Extract selectable text per page, as (page_number, text) pairs.

    source is a file path or the PDF's bytes. Raises ValueError with a
    message suitable for the user when the PDF cannot be processed.
    """
    if isinstance(source, bytes):
        stream = BytesIO(source)
    else:
        path = Path(source)
        if not path.is_file():
            raise FileNotFoundError(f"PDF file not found: {source}")
        stream = str(path)
    if max_pages < 1 or max_chars < 1:
        raise ValueError("PDF limits must be positive.")

    try:
        reader = PdfReader(stream, strict=True)
        if reader.is_encrypted:
            raise ValueError("Encrypted or password-protected PDFs are not supported.")
        page_count = len(reader.pages)
        if page_count > max_pages:
            raise ValueError(f"PDF has {page_count} pages; the limit is {max_pages}.")

        pages = []
        total_chars = 0
        for number, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text() or ""
            total_chars += len(page_text)
            if total_chars > max_chars:
                raise ValueError(
                    f"Extracted text exceeds the {max_chars}-character processing limit."
                )
            pages.append((number, page_text))
        return pages
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("The uploaded file is not a readable PDF.") from exc


def extract_text_from_pdf(
    source: str | bytes,
    max_pages: int = 500,
    max_chars: int = 500_000,
) -> str:
    """Extract selectable PDF text with server-side page and character caps."""
    pages = extract_pages(source, max_pages=max_pages, max_chars=max_chars)
    return "\n\n".join(text for _number, text in pages).strip()
