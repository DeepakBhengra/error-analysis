from __future__ import annotations

import copy
import random
import re
import string
from typing import Any

_TRAILING_DIGITS = re.compile(r"^(.*?)(\d+)$")
_STEM_CHARS = re.compile(r"[A-Za-z]+")
MAX_CUSTOMER_ORDER_NUMBER_LENGTH = 18
_RANDOM_ALPHABET = string.ascii_uppercase + string.digits


def bump_trailing_number(
    value: str,
    max_length: int = MAX_CUSTOMER_ORDER_NUMBER_LENGTH,
) -> str:
    """Increment trailing digits by 1, preserving width when possible.

    Examples: DEEPAKDDTEST11 -> DEEPAKDDTEST12, TEST011 -> TEST012.
    If no trailing digits, append '1' when it fits in ``max_length``.
    The result always differs from the input and never exceeds ``max_length``.
    """
    if max_length < 1:
        raise ValueError("max_length must be at least 1")
    text = value.strip()
    match = _TRAILING_DIGITS.match(text)
    if match:
        prefix, digits = match.group(1), match.group(2)
        bumped_digits = str(int(digits) + 1).zfill(len(digits))
        result = f"{prefix}{bumped_digits}"
    elif len(text) < max_length:
        result = f"{text}1"
    else:
        result = f"{text[: max_length - 1]}1"

    if len(result) > max_length:
        overflow = _TRAILING_DIGITS.match(result)
        if overflow:
            prefix, digits = overflow.group(1), overflow.group(2)
            room = max(0, max_length - len(digits))
            result = f"{prefix[:room]}{digits}"[:max_length]
        else:
            result = result[:max_length]

    if result != text and result != text[:max_length]:
        return result

    base = (text or "P")[: max(1, max_length) - 1]
    for suffix in "123456789ABCDEFGHJKLMNPQRSTUVWXYZ":
        candidate = f"{base}{suffix}"
        if candidate != text and candidate != text[:max_length]:
            return candidate
    return f"{base}X"


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
    """Build a random order number that never exceeds ``max_length`` (default 18).

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


def customer_order_number_from_body(body: dict[str, Any] | None) -> str:
    """Read customerOrderNumber from a v6 body, ignoring key casing."""
    if not isinstance(body, dict):
        return ""
    for key, value in body.items():
        if key.lower() != "customerordernumber" or value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def apply_order_number(body: dict[str, Any], new_number: str) -> dict[str, Any]:
    """Deep-copy body and set customerOrderNumber / endCustomerOrderNumber."""
    updated = copy.deepcopy(body)
    found_customer = False
    for key in list(updated):
        lower = key.lower()
        if lower == "customerordernumber":
            updated[key] = new_number
            found_customer = True
        elif lower == "endcustomerordernumber":
            updated[key] = new_number
    if not found_customer:
        updated["customerOrderNumber"] = new_number
    return updated


def resolve_replay_order_number(
    original: str,
    *,
    explicit: str | None = None,
    use_random: bool = False,
    max_length: int = MAX_CUSTOMER_ORDER_NUMBER_LENGTH,
) -> str:
    """Pick the replay order number from CLI/UI mode flags.

    One-up increments the PO currently in the curl. Random builds a new value
    up to ``max_length`` (18). Both results stay within that limit.
    """
    source = (original or "").strip()
    if explicit and explicit.strip():
        return _clamp_order_number(explicit, max_length)
    if use_random:
        value = random_order_number(prefix=source, max_length=max_length)
        if value != source:
            return value
        return random_order_number(prefix="R", max_length=max_length)
    bumped = bump_trailing_number(source, max_length=max_length)
    return _clamp_order_number(bumped, max_length)
