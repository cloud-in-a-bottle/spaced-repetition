import math

# Same ranges as py-fsrs. The fuzz itself is deterministic (seeded by the review id) rather than random, so that
# replaying a card's reviews always gives the same schedule, on the server and in the browser (static/js/fsrs.js).
_FUZZ_RANGES = ((2.5, 7.0, 0.15), (7.0, 20.0, 0.1), (20.0, math.inf, 0.05))


def seeded_unit_float(seed: str) -> float:
    """FNV-1a 32-bit hash of `seed`, scaled to [0, 1)."""
    h = 0x811C9DC5
    for byte in seed.encode("utf-8"):
        h ^= byte
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h / 2**32


def _round_half_even(x: float) -> int:
    return round(x)


def fuzzed_interval_days(interval_days: int, maximum_interval_days: int, seed: str) -> int:
    if interval_days < 2.5:
        return interval_days
    delta = 1.0
    for start, end, factor in _FUZZ_RANGES:
        delta += factor * max(min(float(interval_days), end) - start, 0.0)
    min_ivl = max(2, _round_half_even(interval_days - delta))
    max_ivl = min(_round_half_even(interval_days + delta), maximum_interval_days)
    min_ivl = min(min_ivl, max_ivl)
    fuzzed = math.floor(seeded_unit_float(seed) * (max_ivl - min_ivl + 1)) + min_ivl
    return min(fuzzed, maximum_interval_days)
