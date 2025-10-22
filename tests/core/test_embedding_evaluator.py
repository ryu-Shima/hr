from __future__ import annotations

import pytest

from hrscreening.core.evaluators.embedding_similarity import EmbeddingSimilarityEvaluator
from hrscreening.schemas import CandidateProfile, ExperienceEntry, JobDescription


def build_candidate() -> dict:
    profile = CandidateProfile(
        provider="bizreach",
        candidate_id="C-200",
        experiences=[
            ExperienceEntry(
                company="Acme",
                title="SRE",
                start="2021-01",
                end="2024-06",
                bullets=[
                    "IaCとしてTerraformを活用しEKSクラスターを構築",
                    "オンコールでAWSインフラを監視",
                ],
            )
        ],
    )
    return profile.model_dump(mode="python")


def build_job() -> dict:
    job = JobDescription(
        job_id="JD-200",
        requirements_text=[
            "TerraformでEKS環境を構築し運用した経験",
            "AWSインフラの監視運用経験",
        ],
    )
    return job.model_dump(mode="python")


def test_embedding_evaluator_returns_similarity_scores():
    evaluator = EmbeddingSimilarityEvaluator()
    candidate = build_candidate()
    job = build_job()

    result = evaluator.evaluate(candidate, {"job": job})

    assert result["method"] == "embed_similarity"
    scores = result["scores"]
    assert 0 <= scores["embed_sim"] <= 1
    assert 0 <= scores["sim_title"] <= 1
    assert result["metadata"]["model"] == "tfidf-cosine-lite"
    evidence = result["metadata"]["evidence_pairs"]
    assert evidence, "evidence_pairs should not be empty"
    top = evidence[0]
    assert "jd_text" in top and "resume_text" in top
    assert 0 <= top["similarity"] <= 1


def test_embedding_evaluator_handles_empty_inputs():
    evaluator = EmbeddingSimilarityEvaluator()
    candidate = CandidateProfile(provider="bizreach", candidate_id="C-201").model_dump(mode="python")
    job = JobDescription(job_id="JD-201").model_dump(mode="python")

    outcome = evaluator.evaluate(candidate, {"job": job})

    assert outcome["scores"]["embed_sim"] == pytest.approx(0.0)
    assert outcome["metadata"]["evidence_pairs"] == []
