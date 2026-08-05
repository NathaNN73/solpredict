"""Tests for the rate range validator."""

import math

from lib.validators import validate_rate


class TestValidRate:
    def test_typical_rate_accepted(self):
        assert validate_rate(3.72) is True

    def test_near_min_boundary(self):
        assert validate_rate(2.01) is True

    def test_near_max_boundary(self):
        assert validate_rate(4.99) is True

    def test_integer_rate_accepted(self):
        assert validate_rate(3) is True


class TestTooLow:
    def test_zero_rejected(self):
        assert validate_rate(0.0) is False

    def test_malformed_rejected(self):
        assert validate_rate(0.01) is False

    def test_negative_rejected(self):
        assert validate_rate(-1.5) is False

    def test_exact_min_rejected(self):
        assert validate_rate(2.0) is False


class TestTooHigh:
    def test_above_max_rejected(self):
        assert validate_rate(6.0) is False

    def test_exact_max_rejected(self):
        assert validate_rate(5.0) is False


class TestEdgeCases:
    def test_nan_rejected(self):
        assert validate_rate(math.nan) is False

    def test_infinity_rejected(self):
        assert validate_rate(math.inf) is False

    def test_boolean_rejected(self):
        # bool is a subclass of int but is not a valid rate value
        assert validate_rate(True) is False
        assert validate_rate(False) is False

    def test_string_rejected(self):
        assert validate_rate("3.72") is False  # type: ignore[arg-type]