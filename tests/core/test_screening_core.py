from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from hrscreening.core import ScreeningCore
from hrscreening.schemas import (
    CandidateProfile,
    JobDescription,
    LanguageProficiency,
)


@dataclass
class StubEvaluatorResult:
    method: str
    scores: dict[str, float]
    metadata: dict[str, Any] | None = None


class StubEvaluator:
    def __init__(self, result: StubEvaluatorResult):
        self._result = result
        self.calls: list[tuple[CandidateProfile, dict[str, Any]]] = []

    def evaluate(self, candidate: dict, context: dict) -> dict[str, Any]:
        self.calls.append((candidate, context))
        payload = {
            "method": self._result.method,
            "scores": self._result.scores,
        }
        if self._result.metadata is not None:
            payload["metadata"] = self._result.metadata
        return payload


def build_candidate(**kwargs: Any) -> CandidateProfile:
    defaults: dict[str, Any] = {
        "provider": "test",
        "candidate_id": "C-001",
    }
    defaults.update(kwargs)
    return CandidateProfile(**defaults)


def build_job(**kwargs: Any) -> JobDescription:
    defaults: dict[str, Any] = {
        "job_id": "JD-001",
    }
    defaults.update(kwargs)
    return JobDescription(**defaults)


def test_screening_core_aggregates_scores_and_weighs():
    evaluator_a = StubEvaluator(
        StubEvaluatorResult(
            method="bm25_proximity",
            scores={"bm25_prox": 1.2, "title_bonus": 0.1},
        )
    )
    evaluator_b = StubEvaluator(
        StubEvaluatorResult(
            method="embed_similarity",
            scores={"embed_sim": 0.8, "sim_title": 0.7},
        )
    )
    core = ScreeningCore(evaluators=[evaluator_a, evaluator_b])
    candidate = build_candidate(
        languages=[LanguageProficiency(language="日本語", level="ネイティブ")]
    )
    job = build_job(
        constraints={"language": ["ja"], "location": [], "visa": None}
    )

    result = core.evaluate(candidate=candidate, job=job)

    assert evaluator_a.calls and evaluator_b.calls
    assert result.aggregate.scores == {
        "bm25_prox": 1.2,
        "title_bonus": 0.1,
        "embed_sim": 0.8,
        "sim_title": 0.7,
    }
    expected = (
        0.45 * 1.2 + 0.05 * 0.1 + 0.40 * 0.8 + 0.10 * 0.7
    )
    assert pytest.approx(expected, rel=1e-6) == result.aggregate.pre_llm_score
    assert result.decision.decision == "pass"
    assert not result.decision.hard_failures


def test_screening_core_applies_hard_gates_language():
    evaluator = StubEvaluator(
        StubEvaluatorResult(
            method="bm25_proximity",
            scores={"bm25_prox": 0.5},
        )
    )
    core = ScreeningCore(evaluators=[evaluator])
    candidate = build_candidate(
        languages=[LanguageProficiency(language="英語", level="ビジネス")],
    )
    job = build_job(constraints={"language": ["ja"]})

    outcome = core.evaluate(candidate=candidate, job=job)

    assert outcome.decision.decision == "reject"
    assert "language" in outcome.decision.hard_failures
    assert outcome.decision.hard_gate_flags["language_ok"] is False
    assert outcome.decision.pre_llm_score == pytest.approx(0.225)

