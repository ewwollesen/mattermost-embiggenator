"""Literary passage bank — loads bundled texts and serves random passages."""

from __future__ import annotations

import random
from pathlib import Path


_TEXTS_DIR = Path(__file__).parent.parent / "data" / "texts"

# Minimum characters for a passage to be considered usable
_MIN_PASSAGE_LEN = 20

# Chapter heading pattern (skip these as standalone passages)
_CHAPTER_PREFIXES = ("chapter ", "volume ")


class PassageBank:
    """Loads prose from bundled text files and serves random passages.

    Passages are split at paragraph boundaries (double newlines).
    Gutenberg headers/footers and short fragments are filtered out.
    """

    def __init__(self, text_dir: Path | None = None) -> None:
        self._paragraphs: list[str] = []
        text_dir = text_dir or _TEXTS_DIR
        for txt_file in sorted(text_dir.glob("*.txt")):
            self._paragraphs.extend(_parse_paragraphs(txt_file))
        if not self._paragraphs:
            raise RuntimeError(f"No usable paragraphs found in {text_dir}")
        # Pre-filter short paragraphs for reply use
        self._short_paragraphs: list[str] = [p for p in self._paragraphs if len(p) < 500]
        if not self._short_paragraphs:
            self._short_paragraphs = self._paragraphs

    @property
    def count(self) -> int:
        return len(self._paragraphs)

    def get_passage(self, rng: random.Random, min_paragraphs: int = 1, max_paragraphs: int = 3) -> str:
        """Return a random passage of 1-3 consecutive paragraphs."""
        n = rng.randint(min_paragraphs, max_paragraphs)
        # Pick a starting index that allows n consecutive paragraphs
        max_start = len(self._paragraphs) - n
        if max_start < 0:
            max_start = 0
            n = len(self._paragraphs)
        start = rng.randint(0, max_start)
        return "\n\n".join(self._paragraphs[start : start + n])

    def get_short_reply(self, rng: random.Random) -> str:
        """Return a single short paragraph suitable for a thread reply."""
        return rng.choice(self._short_paragraphs)


def _parse_paragraphs(path: Path) -> list[str]:
    """Split a text file into cleaned paragraphs."""
    text = path.read_text(encoding="utf-8")
    raw_paragraphs = text.split("\n\n")

    result: list[str] = []
    for para in raw_paragraphs:
        cleaned = " ".join(para.split())  # normalize whitespace
        if len(cleaned) < _MIN_PASSAGE_LEN:
            continue
        if cleaned.lower().startswith(_CHAPTER_PREFIXES):
            continue
        result.append(cleaned)
    return result
