from __future__ import annotations

from difflib import SequenceMatcher
import re


_TR_TRANSLATION = str.maketrans({
    "ı": "i",
    "ğ": "g",
    "ü": "u",
    "ş": "s",
    "ö": "o",
    "ç": "c",
    "İ": "i",
    "Ğ": "g",
    "Ü": "u",
    "Ş": "s",
    "Ö": "o",
    "Ç": "c",
})


def normalize_for_intent(text: str) -> str:
    normalized = text.translate(_TR_TRANSLATION).lower()
    normalized = re.sub(r"[^a-z0-9+@.]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def compact_for_intent(text: str) -> str:
    return normalize_for_intent(text).replace(" ", "")


def tokenize_for_intent(text: str) -> list[str]:
    return [token for token in normalize_for_intent(text).split() if token]


def fuzzy_contains(text: str, phrases: list[str], *, threshold: float = 0.84) -> bool:
    normalized = normalize_for_intent(text)
    compact = compact_for_intent(text)
    tokens = tokenize_for_intent(text)

    for phrase in phrases:
        normalized_phrase = normalize_for_intent(phrase)
        if not normalized_phrase:
            continue
        compact_phrase = normalized_phrase.replace(" ", "")
        if normalized_phrase in normalized or compact_phrase in compact:
            return True

        phrase_tokens = normalized_phrase.split()
        if len(phrase_tokens) == 1:
            target = phrase_tokens[0]
            if any(SequenceMatcher(None, token, target).ratio() >= threshold for token in tokens):
                return True
            continue

        window_size = len(phrase_tokens)
        for index in range(0, max(0, len(tokens) - window_size + 1)):
            candidate = " ".join(tokens[index:index + window_size])
            if SequenceMatcher(None, candidate, normalized_phrase).ratio() >= threshold:
                return True

    return False


def any_phrase(text: str, phrases: list[str]) -> bool:
    normalized = normalize_for_intent(text)
    return any(normalize_for_intent(phrase) in normalized for phrase in phrases)
