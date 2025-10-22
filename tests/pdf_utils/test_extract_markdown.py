from __future__ import annotations

from pathlib import Path
from typing import Callable

import pytest

import hrscreening.pdf_utils as pdf_utils


class DummyPDF:
    def __init__(self, text: str) -> None:
        self._text = text

    def to_markdown(self, _: str) -> str:
        return self._text


@pytest.fixture(autouse=True)
def stub_pymupdf4llm(monkeypatch: pytest.MonkeyPatch) -> Callable[[str], str]:
    dummy = DummyPDF(
        text=(
            "sample header\n"
            "職務経歴書の取り扱いには十分注意をし、コピー・転載行為は厳禁のこと、関係者のみ、閲覧可能とします。また、採用活動目的以外での使用は不可とし、使用後は必ず責任を持って破棄していただくよう、お願いします。 1 / 63\n"
            "本文\n"
            "アカウント名 : Lazuli株式会社 / Shimasaki Ryu\n"
            "footer"
        )
    )

    def fake_to_markdown(path: str) -> str:  # pragma: no cover - simple passthrough
        return dummy._text

    monkeypatch.setattr(pdf_utils.pymupdf4llm, "to_markdown", fake_to_markdown)
    return fake_to_markdown


def test_extract_markdown_excludes_boilerplate(tmp_path: Path) -> None:
    pdf_file = tmp_path / "dummy.pdf"
    pdf_file.write_bytes(b"%PDF-1.4\n% Dummy")  # Presence is enough, content not used.

    result = pdf_utils.extract_markdown(pdf_file)

    assert "職務経歴書の取り扱い" not in result
    assert "アカウント名 : Lazuli株式会社 / Shimasaki Ryu" not in result
    assert "sample header" in result
    assert "本文" in result
