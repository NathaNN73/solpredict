"""Rate range validation.

USD/PEN rates from public APIs are expected to fall within a sane band.
Anything outside [2.0, 5.0) indicates a malformed response (zero, negative,
inverted quote) and must be rejected before it pollutes the local store.
"""

from config import RATE_MAX, RATE_MIN


def validate_rate(rate: float) -> bool:
    """Return True when ``rate`` is a positive number strictly inside bounds.

    The bounds are open (2.0 < rate < 5.0): the exact edges are treated as
    suspicious rather than valid, which matches the spec scenario that
    rejects a malformed 0.01 rate and accepts a 3.72 rate.
    """
    if not isinstance(rate, (int, float)) or isinstance(rate, bool):
        return False
    if rate != rate:  # NaN check (NaN != NaN is the only float != itself)
        return False
    return RATE_MIN < rate < RATE_MAX