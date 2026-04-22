"""Parse human-readable durations like ``10m``, ``1h``, ``2d``."""
from __future__ import annotations

_UNITS = {
    "s": 1,
    "m": 60,
    "h": 60 * 60,
    "d": 60 * 60 * 24,
    "w": 60 * 60 * 24 * 7,
}


def parse_duration(text: str) -> int | None:
    """Return the duration in seconds, or ``None`` if the input is invalid.

    Examples: ``"30"`` (seconds), ``"10m"``, ``"1h30m"``, ``"2d"``.
    """
    text = text.strip().lower()
    if not text:
        return None
    # Plain integer -> seconds
    if text.isdigit():
        return int(text)
    total = 0
    number = ""
    for ch in text:
        if ch.isdigit():
            number += ch
        elif ch in _UNITS:
            if not number:
                return None
            total += int(number) * _UNITS[ch]
            number = ""
        else:
            return None
    if number:
        return None
    return total or None


def format_duration(seconds: int) -> str:
    if seconds <= 0:
        return "0s"
    parts: list[str] = []
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60), ("s", 1)):
        if seconds >= size:
            value, seconds = divmod(seconds, size)
            parts.append(f"{value}{unit}")
    return " ".join(parts)
