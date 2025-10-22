from __future__ import annotations

import json
from pathlib import Path

import pytest

from hrscreening.adapters import BizReachAdapter
from hrscreening.pipeline import (
    AdapterRegistry,
    CandidateLoadError,
    CandidateLoader,
    JobLoader,
)


def test_candidate_loader_raises_on_invalid_json(tmp_path: Path):
    registry = AdapterRegistry([BizReachAdapter()])
    loader = CandidateLoader(registry)
    path = tmp_path / "candidates.jsonl"
    path.write_text('{"provider": "bizreach"}\n{invalid}', encoding="utf-8")

    with pytest.raises(CandidateLoadError) as exc:
        loader.load(path)
    assert "invalid JSON" in str(exc.value)


def test_candidate_loader_skips_invalid_and_reports(tmp_path: Path):
    registry = AdapterRegistry([BizReachAdapter()])
    loader = CandidateLoader(registry)
    path = tmp_path / "candidates.jsonl"
    valid_payload = {
        "provider": "bizreach",
        "payload": {
            "candidate_id": "C-001",
            "experiences": [],
        },
    }
    invalid_payload = {"provider": "unknown"}
    path.write_text(
        json.dumps(valid_payload, ensure_ascii=False)
        + "\n"
        + json.dumps(invalid_payload, ensure_ascii=False),
        encoding="utf-8",
    )

    with pytest.raises(CandidateLoadError) as exc:
        loader.load(path)
    error = exc.value
    assert "unsupported provider" in error.errors[0]
    assert len(error.partial) == 1


def test_job_loader_invalid_json(tmp_path: Path):
    job_loader = JobLoader()
    path = tmp_path / "job.json"
    path.write_text("{invalid", encoding="utf-8")

    with pytest.raises(ValueError):
        job_loader.load(path)
