from __future__ import annotations

import pytest

from hrscreening.core.evaluators.bm25_proximity import BM25ProximityEvaluator
from hrscreening.schemas import CandidateProfile, ExperienceEntry, JobDescription


def build_candidate() -> dict:
    profile = CandidateProfile(
        provider="bizreach",
        candidate_id="C-100",
        experiences=[
            ExperienceEntry(
                company="Acme",
                title="Site Reliability Engineer",
                start="2020-01",
                end="2024-12",
                bullets=[
                    "TerraformでAWS基盤をIaC化し、EKSを構築",
                    "PrometheusとGrafanaで可観測性を改善",
                ],
            )
        ],
        skills=["Terraform", "AWS", "Prometheus"],
    )
    return profile.model_dump(mode="python")


def build_job() -> dict:
    job = JobDescription(
        job_id="JD-100",
        role_titles=["Site Reliability Engineer"],
        requirements_text=[
            "Terraformを用いたIaC構築経験",
            "AWS上での運用・監視経験",
        ],
        key_phrases=["Terraform", "AWS", "IaC", "監視"],
    )
    return job.model_dump(mode="python")


def test_bm25_evaluator_returns_hits_and_scores():
    evaluator = BM25ProximityEvaluator()
    candidate = build_candidate()
    job = build_job()

    result = evaluator.evaluate(candidate, {"job": job})

    assert result["method"] == "bm25_proximity"
    scores = result["scores"]
    assert scores["bm25_prox"] > 0
    assert scores["title_bonus"] >= 0
    hits = result["metadata"]["hits"]
    assert hits, "hits should not be empty"
    top_hit = hits[0]
    assert "jd_text" in top_hit and "resume_text" in top_hit
    assert top_hit["bm25"] > 0


def test_bm25_evaluator_handles_missing_sections_gracefully():
    profile = CandidateProfile(
        provider="bizreach",
        candidate_id="C-101",
        experiences=[],
        skills=[],
    ).model_dump(mode="python")
    job = build_job()

    evaluator = BM25ProximityEvaluator()
    outcome = evaluator.evaluate(profile, {"job": job})

    assert outcome["scores"]["bm25_prox"] == pytest.approx(0.0)
    assert outcome["metadata"]["hits"] == []

