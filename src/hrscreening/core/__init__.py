"\"\"\"Core screening engine components.\"\"\""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Evaluator(Protocol):
    """Evaluator contract for computing screening scores."""

    def evaluate(self, candidate: dict, context: dict) -> dict:
        """Return evaluation results for a candidate under the given context."""


__all__ = ["Evaluator"]

