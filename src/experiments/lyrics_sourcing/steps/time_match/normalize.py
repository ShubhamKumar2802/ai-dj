"""Text normalization shared by lyrics and transcript (spec §4.4.1; = whisper_bakeoff §5.2). Pure.

NFKC + lowercase -> Devanagari to Roman (ITRANS, then ASCII fold) -> strip punctuation ->
collapse whitespace. Perso-Arabic script is left as-is and counted, not transliterated.
"""

import re
import unicodedata

from indic_transliteration import sanscript
from indic_transliteration.sanscript import transliterate

_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_PERSO_ARABIC = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")
_NON_WORD = re.compile(r"[^\w\s]|_")
_WHITESPACE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    if _DEVANAGARI.search(normalized):
        normalized = transliterate(normalized, sanscript.DEVANAGARI, sanscript.ITRANS)
        normalized = _ascii_fold(normalized)
    normalized = normalized.lower()
    normalized = _NON_WORD.sub(" ", normalized)
    return _WHITESPACE.sub(" ", normalized).strip()


def count_perso_arabic_words(text: str) -> int:
    return sum(1 for word in text.split() if _PERSO_ARABIC.search(word))


def _ascii_fold(text: str) -> str:
    # ITRANS marks long vowels/retroflexes with case and punctuation (A, I, U, .N, ~n); the
    # later lowercase + punctuation strip reduces those to plain letters. This fold only
    # removes any combining marks left behind.
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))
