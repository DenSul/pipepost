"""Slug generation and transliteration utilities."""

from __future__ import annotations

import datetime
import re


_CYRILLIC_MAP: dict[str, str] = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "yo",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "kh",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "shch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}


def transliterate(text: str) -> str:
    """Transliterate Cyrillic characters to Latin equivalents."""
    return "".join(_CYRILLIC_MAP.get(ch, ch) for ch in text)


def slugify(text: str) -> str:
    """Convert text to URL-friendly slug with date prefix and transliteration."""
    prefix = datetime.date.today().isoformat()  # noqa: DTZ011
    text = transliterate(text.lower().strip())
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    slug = text[:60].strip("-")
    return f"{prefix}-{slug}"
