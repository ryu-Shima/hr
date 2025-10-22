"""Helpers for constructing LLM rerank payloads and clients."""

from __future__ import annotations

import json
from typing import Any
from urllib import error, request

import structlog

from .core.screening import ScreeningOutcome
from .schemas import CandidateProfile, JobDescription


def build_llm_payload(
    *,
    job: JobDescription,
    candidate: CandidateProfile,
    outcome: ScreeningOutcome,
) -> dict[str, Any]:
    """Construct payload expected by external LLM reranker."""

    bm25 = _find_evaluation(outcome, "bm25_proximity")
    embed = _find_evaluation(outcome, "embed_similarity")

    return {
        "job_id": job.job_id,
        "candidate_id": candidate.candidate_id,
        "jd": {
            "role_titles": job.role_titles,
            "requirements_top": (job.requirements_text or [])[:5],
            "constraints": job.constraints.model_dump() if job.constraints else {},
        },
        "candidate_summary": {
            "titles": [exp.title for exp in candidate.experiences or [] if exp.title],
            "skills_agg_top": [
                {"name": name, "years": data.years, "last_used": data.last_used}
                for name, data in (candidate.skills_agg or {}).items()
            ][:5],
        },
        "method1_bm25": _extract_bm25_metadata(bm25),
        "method2_embed": _extract_embed_metadata(embed),
        "pre_llm_score": outcome.aggregate.pre_llm_score,
        "penalties": outcome.decision.hard_gate_flags,
    }


class HTTPLLMClient:
    """Simple HTTP client for LLM rerank API."""

    def __init__(self, endpoint: str | None, api_key: str | None = None, *, timeout: float = 10.0):
        self._endpoint = endpoint
        self._api_key = api_key
        self._timeout = timeout
        self._logger = structlog.get_logger(__name__)

    def rerank(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        if not self._endpoint:
            return None
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        req = request.Request(self._endpoint, data=data, headers=headers, method="POST")
        try:
            with request.urlopen(req, timeout=self._timeout) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body) if body else {}
        except error.URLError as exc:  # pragma: no cover - error path
            self._logger.warning("llm.request_failed", error=str(exc))
            return None



def _find_evaluation(outcome: ScreeningOutcome, method: str) -> dict[str, Any] | None:
    for evaluation in outcome.evaluations:
        if evaluation.method == method:
            return {
                "method": evaluation.method,
                "scores": evaluation.scores,
                "metadata": evaluation.metadata,
            }
    return None


def _extract_bm25_metadata(bm25: dict[str, Any] | None) -> dict[str, Any]:
    if not bm25:
        return {}
    metadata = bm25.get("metadata", {})
    hits = metadata.get("hits", [])
    return {
        "bm25_prox": bm25["scores"].get("bm25_prox", 0.0),
        "title_bonus": bm25["scores"].get("title_bonus", 0.0),
        "hits_top": hits[:3],
    }


def _extract_embed_metadata(embed: dict[str, Any] | None) -> dict[str, Any]:
    if not embed:
        return {}
    metadata = embed.get("metadata", {})
    evidence = metadata.get("evidence_pairs", [])
    return {
        "embed_sim": embed["scores"].get("embed_sim", 0.0),
        "sim_title": embed["scores"].get("sim_title", 0.0),
        "evidence_pairs_top": evidence[:3],
    }
