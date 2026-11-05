from io import BytesIO
from pathlib import Path

from pypdf import PdfReader


def extract_text_from_pdf(
    source: str | bytes,
    max_pages: int = 500,
    max_chars: int = 500_000,
) -> str:
    """Extract selectable PDF text with server-side page and character caps.

    source is a file path or the PDF's bytes.
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
        page_count = len(reader.pages)
        if page_count > max_pages:
            raise ValueError(f"PDF has {page_count} pages; the limit is {max_pages}.")

        pieces = []
        total_chars = 0
        for index, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text() or ""
            total_chars += len(page_text)
            if total_chars > max_chars:
                raise ValueError(
                    f"Extracted text exceeds the {max_chars}-character processing limit."
                )
            pieces.append(page_text)

        return "\n\n".join(pieces).strip()
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("The uploaded file is not a readable PDF.") from exc
