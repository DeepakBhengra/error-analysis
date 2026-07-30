from __future__ import annotations

import copy
import random
import re
import string
from typing import Any

_TRAILING_DIGITS = re.compile(r"^(.*?)(\d+)$")
_STEM_CHARS = re.compile(r"[A-Za-z]+")
MAX_CUSTOMER_ORDER_NUMBER_LENGTH = 20
_RANDOM_ALPHABET = string.ascii_uppercase + string.digits


def bump_trailing_number(value: str) -> str:
    """Increment trailing digits by 1, preserving width when possible.

    Examples: DEEPAKDDTEST11 -> DEEPAKDDTEST12, TEST011 -> TEST012.
    If no trailing digits, append '1'.
    """
    text = value.strip()
    match = _TRAILING_DIGITS.match(text)
    if not match:
        return f"{text}1"
    prefix, digits = match.group(1), match.group(2)
    bumped = str(int(digits) + 1).zfill(len(digits))
    return f"{prefix}{bumped}"


def _clamp_order_number(value: str, max_length: int = MAX_CUSTOMER_ORDER_NUMBER_LENGTH) -> str:
    text = value.strip()
    if max_length < 1:
        raise ValueError("max_length must be at least 1")
    return text[:max_length]


def _random_stem(prefix: str | None) -> str:
    """Keep a short alphabetic cue from the original PO (no embedded digits)."""
    base = (prefix or "").strip()
    if not base:
        return "R"
    match = _TRAILING_DIGITS.match(base)
    alpha = match.group(1) if match else base
    letters = "".join(_STEM_CHARS.findall(alpha)).upper()
    if not letters:
        return "R"
    return letters[:4]


def random_order_number(
    prefix: str | None = None,
    *,
    max_length: int = MAX_CUSTOMER_ORDER_NUMBER_LENGTH,
) -> str:
    """Build a random order number that never exceeds ``max_length`` (default 20).

    Uses a short alphabetic stem from the original (at most 4 letters), then
    fills the rest with random A-Z/0-9 so the value cannot resemble a long
    original PO (e.g. MP-103923L10401876EX).
    """
    if max_length < 1:
        raise ValueError("max_length must be at least 1")

    stem = _random_stem(prefix)
    # Leave at least half the budget for randomness when possible.
    max_stem = min(len(stem), max(1, max_length // 3), 4)
    stem = stem[:max_stem]
    fill_len = max_length - len(stem)
    filled = "".join(random.choices(_RANDOM_ALPHABET, k=fill_len))
    return _clamp_order_number(f"{stem}{filled}", max_length)


def apply_order_number(body: dict[str, Any], new_number: str) -> dict[str, Any]:
    """Deep-copy body and set customerOrderNumber / endCustomerOrderNumber when present."""
    updated = copy.deepcopy(body)
    if "customerOrderNumber" in updated:
        updated["customerOrderNumber"] = new_number
    if "endCustomerOrderNumber" in updated:
        updated["endCustomerOrderNumber"] = new_number
    return updated


def resolve_replay_order_number(
    original: str,
    *,
    explicit: str | None = None,
    use_random: bool = False,
    max_length: int = MAX_CUSTOMER_ORDER_NUMBER_LENGTH,
) -> str:
    """Pick the replay order number from CLI/UI mode flags."""
    if explicit and explicit.strip():
        return _clamp_order_number(explicit, max_length)
    if use_random:
        return random_order_number(prefix=original, max_length=max_length)
    return _clamp_order_number(bump_trailing_number(original), max_length)
