"""Backward-compatible validator entry point.

The real adaptive validation implementation lives in adaptive_validator.py.
Keeping FastValidator here means existing code/imports continue to work.
"""

from adaptive_validator import AdaptiveValidator


class FastValidator(AdaptiveValidator):
    """Compatibility name for the existing automation pipeline."""

    pass
