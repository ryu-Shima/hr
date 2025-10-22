"""Utilities for extracting markdown from PDF resumes."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Sequence

import pymupdf4llm

_DEFAULT_EXCLUDES: tuple[str, ...] = (
    "職務経歴書の取り扱いには十分注意をし、コピー・転載行為は厳禁のこと、関係者のみ、閲覧可能とします。また、採用活動目的以外での使用は不可とし、使用後は必ず責任を持って破棄していただくよう、お願いします。",
    "アカウント名 : Lazuli株式会社 / Shimasaki Ryu",
)


def extract_markdown(
    pdf_path: str | Path,
    *,
    exclude_patterns: Sequence[str] | None = None,
) -> str:
    """Return markdown text extracted from a PDF, removing boilerplate lines.

    Parameters
    ----------
    pdf_path:
        Path to the source PDF file.
    exclude_patterns:
        Optional list of string patterns to remove entirely from the output lines.
        Each pattern will be matched as a substring (case-sensitive) and any line
        containing it will be dropped. Default removes BizReach boilerplate notices.
    """

    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(pdf_path)

    markdown = pymupdf4llm.to_markdown(str(pdf_path))
    excludes = list(exclude_patterns) if exclude_patterns is not None else list(_DEFAULT_EXCLUDES)

    # Add pattern variations for page counters "1 / 63" appended to the boilerplate line.
    expanded_patterns = _build_patterns(excludes)

    cleaned_lines: list[str] = []
    for line in markdown.splitlines():
        if not line.strip():
            cleaned_lines.append(line)
            continue
        if any(pattern.search(line) for pattern in expanded_patterns):
            continue
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines)


def _build_patterns(excludes: Iterable[str]) -> list[re.Pattern[str]]:
    patterns: list[re.Pattern[str]] = []
    for text in excludes:
        escaped = re.escape(text)
        # Allow optional whitespace and page counter suffix like " 1 / 63".
        pattern = re.compile(rf"{escaped}(?:\s+\d+\s*/\s*\d+)?")
        patterns.append(pattern)
    return patterns


__all__ = ["extract_markdown"]

