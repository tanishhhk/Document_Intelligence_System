"""Turn story text into something a voice can read aloud naturally.

Text-to-speech engines read symbols literally, so "quarterly_report" becomes
"quarterly underscore report" and a table row becomes a list of "pipe"s.
"""
import re

_URL = re.compile(r"\b(?:https?://|www\.)\S+", re.IGNORECASE)
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")
_WORDS = [
    (re.compile(r"(?<=\d)\s*%"), " percent"),
    (re.compile(r"\s*&\s*"), " and "),
    # "pages 3-5" is a range; dates such as 2026-11-05 are left alone.
    (re.compile(r"(?<![\d-])(\d{1,4})\s*-\s*(\d{1,4})(?![\d-])"), r"\1 to \2"),
    (re.compile(r"\band/or\b", re.IGNORECASE), "and or"),
    (re.compile(r"(?<=[^\W\d])/(?=[^\W\d])"), " or "),
    (re.compile(r"(?<=\d)\s*\+"), " plus"),
    (re.compile(r"\s*=\s*"), " equals "),
    (re.compile(r"[•●▪‣⁃]"), ", "),
]
# Symbols with no spoken meaning in prose; each becomes a space.
_SILENT = re.compile(r"[_|*#~^`<>\[\]{}\\@]+")


def speakable(text: str) -> str:
    """Text for the narration voice: no symbols read aloud, links skipped."""
    text = _URL.sub(" a link ", text or "")
    text = _EMAIL.sub(" an email address ", text)
    for pattern, words in _WORDS:
        text = pattern.sub(words, text)
    text = _SILENT.sub(" ", text)
    text = re.sub(r"[—–]", ", ", text)  # Dashes become a pause.
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"([,.;:!?])(?:\s*[,;])+", r"\1", text)
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n\n", text)).strip()


def display_name(text: str) -> str:
    """A label for slides and titles: symbols and underscores become spaces."""
    return re.sub(r"\s+", " ", _SILENT.sub(" ", text or "")).strip()
