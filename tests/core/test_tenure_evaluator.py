from __future__ import annotations

import pendulum
import pytest

from hrscreening.core.evaluators import TenureEvaluator
from hrscreening.schemas import CandidateProfile, ExperienceEntry


def build_candidate(experiences: list[dict]) -> dict:
    profile = CandidateProfile(
        provider="test",
        candidate_id="C-100",
        experiences=[ExperienceEntry(**exp) for exp in experiences],
    )
    return profile.model_dump(mode="python")


def test_tenure_evaluator_passes_stable_history():
    candidate = build_candidate(
        [
            {"company": "A", "title": "Eng", "start": "2020-01", "end": "2023-01"},
            {"company": "B", "title": "Eng", "start": "2017-01", "end": "2019-12"},
            {"company": "C", "title": "Eng", "start": "2014-01", "end": "2016-12"},
        ]
    )
    evaluator = TenureEvaluator()

    result = evaluator.evaluate(candidate, {"as_of": "2025-01"})

    assert result["method"] == "tenure"
    assert result["metadata"]["average_months"] >= 30.0
    assert result["scores"]["tenure_pass"] == pytest.approx(1.0)
    assert result["metadata"]["is_job_hopper"] is False
    assert result["metadata"]["risk_level"] == "low"


def test_tenure_evaluator_flags_job_hopper():
    candidate = build_candidate(
        [
            {"company": "A", "title": "Eng", "start": "2024-01", "end": "2024-08"},
            {"company": "B", "title": "Eng", "start": "2022-10", "end": "2023-06"},
            {"company": "C", "title": "Eng", "start": "2021-01", "end": "2022-03"},
        ]
    )
    evaluator = TenureEvaluator()

    outcome = evaluator.evaluate(candidate, {"as_of": "2024-12"})

    assert outcome["scores"]["tenure_pass"] == pytest.approx(0.0)
    assert outcome["metadata"]["is_job_hopper"] is True
    assert outcome["metadata"]["recent_short_tenures"] >= 2
    assert outcome["metadata"]["risk_level"] == "high"
    assert "RECENT_SHORT_TENURE" in outcome["metadata"]["reasons"]


def test_tenure_contract_profile_relaxed_threshold():
    candidate = build_candidate(
        [
            {
                "company": "ContractA",
                "title": "SWE",
                "start": "2023-01",
                "end": "2024-02",
                "employment_type": "contract",
            },
            {
                "company": "ContractB",
                "title": "SWE",
                "start": "2021-09",
                "end": "2022-09",
                "employment_type": "freelance",
            },
        ]
    )
    evaluator = TenureEvaluator()

    result = evaluator.evaluate(candidate, {"as_of": pendulum.datetime(2024, 10, 1)})

    assert result["metadata"]["is_contract_profile"] is True
    assert pytest.approx(12.5, rel=1e-2) == result["metadata"]["contract_average_months"]
    assert result["scores"]["tenure_pass"] == pytest.approx(1.0)
    assert result["metadata"]["passes_contract_rule"] is True
    assert result["metadata"]["risk_level"] in {"low", "medium"}
