"""Text normalization used for merchant matching and keys."""

import re
import unicodedata

_NON_WORD = re.compile(r"[^0-9a-zऀ-ॿ]+")  # keep ASCII letters/digits and Devanagari


def _strip_latin_accents(text: str) -> str:
    """'café' -> 'cafe', but leave Devanagari signs (virama, nukta) alone: 'श्रेष्ठ' stays."""
    out: list[str] = []
    for ch in unicodedata.normalize("NFD", text):
        if unicodedata.combining(ch) and out and out[-1].isascii():
            continue  # accent on a Latin letter
        out.append(ch)
    return unicodedata.normalize("NFC", "".join(out))


def normalize_merchant(name: str) -> str:
    """'Café Dhukuti  (Jhamsikhel)' -> 'cafe dhukuti jhamsikhel'. Stable key for a merchant."""
    return _NON_WORD.sub(" ", _strip_latin_accents(name.casefold())).strip()
