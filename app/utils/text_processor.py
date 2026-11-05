import re
from dataclasses import dataclass
from typing import List


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
    """
    Split text into overlapping chunks

    Args:
        text: The text to split
        chunk_size: Size of each chunk in characters
        overlap: Number of characters to overlap between chunks

    Returns:
        List of text chunks
    """
    if not text or len(text) == 0:
        return []

    chunks = []
    start = 0

    while start < len(text):
        # Get chunk from start to start+chunk_size
        end = start + chunk_size
        chunk = text[start:end]

        # Add chunk if it's not empty
        if chunk.strip():
            chunks.append(chunk.strip())

        # Move start forward (chunk_size - overlap)
        start += (chunk_size - overlap)

    return chunks


@dataclass(frozen=True)
class Chunk:
    text: str
    page_start: int
    page_end: int


@dataclass(frozen=True)
class _Segment:
    text: str
    page: int
    kind: str  # "heading", "line" (table row or list item) or "sentence"


# Both patterns are anchored or fixed-width, so they run in linear time.
_LIST_ITEM = re.compile(r"^(?:[-*•]|\d{1,3}[.)]|[A-Za-z][.)])\s")
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"(\[])")
_TERMINAL = (".", "!", "?", ":", ";", ",")
# How full a chunk must be before a heading or a page break starts a new one.
# Measured with scripts/evaluate_retrieval.py: section- and page-aligned
# chunks ranked the right passage first more often than larger mixed ones.
_HEADING_BREAK_FILL = 0.1
_PAGE_BREAK_FILL = 0.25


def _is_structured_line(line: str) -> bool:
    return "|" in line or "\t" in line or bool(_LIST_ITEM.match(line))


def _is_heading(line: str, next_line: str, paragraph: list[str]) -> bool:
    if len(line) > 80 or len(line.split()) > 12 or line.endswith(_TERMINAL):
        return False
    if not (line[0].isupper() or line[0].isdigit()):
        return False
    if paragraph and not paragraph[-1].endswith((".", "!", "?", ":")):
        return False  # The line continues an unfinished sentence.
    return not next_line or next_line[0].isupper() or next_line[0].isdigit()


def _segments(page_number: int, text: str) -> list[_Segment]:
    lines = [line.strip() for line in text.splitlines()]
    segments: list[_Segment] = []
    paragraph: list[str] = []

    def flush():
        if paragraph:
            joined = " ".join(paragraph)
            for sentence in _SENTENCE_BREAK.split(joined):
                if sentence.strip():
                    segments.append(_Segment(sentence.strip(), page_number, "sentence"))
            paragraph.clear()

    for index, line in enumerate(lines):
        if not line:
            flush()
            continue
        next_line = next((candidate for candidate in lines[index + 1:] if candidate), "")
        # Headings are checked first so numbered ones ("2. Methods") are not
        # mistaken for list items.
        if "|" not in line and _is_heading(line, next_line, paragraph):
            flush()
            segments.append(_Segment(line, page_number, "heading"))
        elif _is_structured_line(line):
            flush()
            segments.append(_Segment(line, page_number, "line"))
        else:
            paragraph.append(line)
    flush()
    return segments


def _split_long(segment: _Segment, size: int) -> list[_Segment]:
    # Words longer than a chunk (URLs, encoded data) are cut into pieces
    # rather than truncated, so no text is lost.
    words = [
        word[start : start + size]
        for word in segment.text.split()
        for start in range(0, len(word), size)
    ]
    pieces, current = [], ""
    for word in words:
        if current and len(current) + 1 + len(word) > size:
            pieces.append(current)
            current = word
        else:
            current = f"{current} {word}" if current else word
    if current:
        pieces.append(current)
    return [_Segment(piece, segment.page, segment.kind) for piece in pieces]


def _join(segments: list[_Segment]) -> str:
    parts = []
    for previous, segment in zip([None, *segments], segments, strict=False):
        if previous is not None:
            block = segment.kind != "sentence" or previous.kind != "sentence"
            parts.append("\n" if block else " ")
        parts.append(segment.text)
    return "".join(parts)


def chunk_pages(
    pages: list[tuple[int, str]],
    chunk_size: int = 1000,
    overlap: int = 200,
    max_chunk_size: int = 1500,
) -> List[Chunk]:
    """Split page text into chunks along sentence, line and heading boundaries.

    Sentences, table rows and list items are never split unless a single one
    is longer than max_chunk_size. A heading starts a new chunk when the
    current chunk is already well filled, and a page break does too, so that
    chunks tend to stay within one section and one page. Consecutive chunks
    on the same page share up to `overlap` characters of trailing sentences;
    chunks that start at a heading or a page break do not, which keeps their
    page ranges exact.
    """
    segments: list[_Segment] = []
    for page_number, text in pages:
        for segment in _segments(page_number, text or ""):
            if len(segment.text) > max_chunk_size:
                segments.extend(_split_long(segment, chunk_size))
            else:
                segments.append(segment)

    chunks: list[Chunk] = []
    current: list[_Segment] = []

    def length(items):
        return len(_join(items))

    def emit(keep_overlap: bool) -> bool:
        nonlocal current
        if not any(item.kind != "heading" for item in current):
            return False  # Wait until a heading has some content after it.
        chunks.append(
            Chunk(
                _join(current),
                min(item.page for item in current),
                max(item.page for item in current),
            )
        )
        carried: list[_Segment] = []
        if keep_overlap:
            for item in reversed(current):
                if item.kind == "heading" or length([item, *carried]) > overlap:
                    break
                carried.insert(0, item)
        current = carried
        return True

    for segment in segments:
        if current:
            filled = length(current)
            if segment.kind == "heading" and filled >= chunk_size * _HEADING_BREAK_FILL:
                emit(keep_overlap=False)
            elif segment.page != current[-1].page and filled >= chunk_size * _PAGE_BREAK_FILL:
                emit(keep_overlap=False)
            elif filled + 1 + len(segment.text) > chunk_size:
                # Drop the carried overlap if it leaves no room, but never a
                # heading that has not been emitted yet.
                if emit(keep_overlap=True) and current and length([*current, segment]) > chunk_size:
                    current = []
        current.append(segment)

    if current:
        emit(keep_overlap=False)
        if current:  # Only headings were left over.
            chunks.append(
                Chunk(_join(current), current[0].page, current[-1].page)
            )
    return chunks
