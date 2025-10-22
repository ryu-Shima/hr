"\"\"\"Site-specific resume adapters.\"\"\""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .bizreach import BizReachAdapter


@runtime_checkable
class ResumeAdapter(Protocol):
    """Site-specific resume adapter contract.

    Implementations transform provider-native resume blobs into provider-neutral
    candidate dictionaries that conform to the shared schema.
    """

    provider: str

    def can_handle(self, blob: bytes | str, metadata: dict) -> bool:
        """Return True when the adapter can parse the given resume payload."""

    def split_candidates(self, text: str) -> list[str]:
        """Split a multi-candidate payload into per-candidate text chunks."""

    def parse_candidate(self, section: str) -> dict:
        """Parse a candidate section and return a provider-neutral dictionary."""


__all__ = ["ResumeAdapter", "BizReachAdapter"]
