"""Generic helpers: duration parsing, string formatting utilities."""

from __future__ import annotations

import re

_DURATION_PATTERN = re.compile(r"(\d+)([smhdw])")

_UNIT_SECONDS = {
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
    "w": 604800,
}


class InvalidDuration(ValueError):
    pass


def parse_duration(value: str) -> int:
    """
    Parse strings like '10s', '10m', '2h', '3d', '1w', '1w2d' into a
    total number of seconds. Raises InvalidDuration on bad input.
    """
    value = value.strip().lower()
    if not value:
        raise InvalidDuration("Duration cannot be empty.")

    matches = _DURATION_PATTERN.findall(value)
    if not matches:
        raise InvalidDuration(
            f"Could not parse duration '{value}'. Use formats like 10m, 2h, 3d, 1w2d."
        )

    # Make sure the whole string was consumed by valid tokens (catches typos like '10x').
    reconstructed = "".join(f"{amount}{unit}" for amount, unit in matches)
    if reconstructed != value:
        raise InvalidDuration(
            f"Could not parse duration '{value}'. Use formats like 10m, 2h, 3d, 1w2d."
        )

    total_seconds = 0
    for amount, unit in matches:
        total_seconds += int(amount) * _UNIT_SECONDS[unit]

    return total_seconds


def format_duration(total_seconds: int) -> str:
    """Turn a second count back into a compact human string, e.g. 90000 -> '1d1h'."""
    if total_seconds <= 0:
        return "0s"

    parts = []
    remaining = total_seconds
    for unit, seconds in (("w", 604800), ("d", 86400), ("h", 3600), ("m", 60), ("s", 1)):
        if remaining >= seconds:
            amount, remaining = divmod(remaining, seconds)
            parts.append(f"{amount}{unit}")

    return "".join(parts)


def truncate(text: str, limit: int = 1024) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"
