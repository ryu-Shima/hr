"\"\"\"Screening core orchestration.\"\"\""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Literal

from ..schemas import CandidateProfile, JobDescription, LanguageProficiency

DecisionType = Literal["pass", "borderline", "reject"]


@dataclass(slots=True)
class EvaluationResult:
    """Normalized evaluator output."""

    method: str
    scores: dict[str, float]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AggregateScores:
    """Aggregated score view."""

    scores: dict[str, float]
    pre_llm_score: float


@dataclass(slots=True)
class DecisionSummary:
    """Final decision with hard gate flags."""

    decision: DecisionType
    pre_llm_score: float
    hard_gate_flags: dict[str, bool]
    hard_gate_details: dict[str, Any]
    hard_failures: list[str]


@dataclass(slots=True)
class ScreeningOutcome:
    """Complete evaluation payload for downstream consumers."""

    candidate_id: str
    job_id: str
    evaluations: list[EvaluationResult]
    aggregate: AggregateScores
    decision: DecisionSummary


class ScreeningCore:
    """Coordinates evaluators and aggregates scoring decisions."""

    DEFAULT_WEIGHTS: dict[str, float] = {
        "bm25_prox": 0.40,
        "embed_sim": 0.35,
        "sim_title": 0.08,
        "title_bonus": 0.07,
        "tenure_pass": 0.04,
        "salary_pass": 0.04,
        "jd_pass": 0.02,
    }

    DEFAULT_THRESHOLDS: dict[DecisionType, float] = {
        "pass": 0.80,
        "borderline": 0.65,
        "reject": 0.0,
    }

    _HARD_GATE_LABELS: dict[str, str] = {
        "location_ok": "location",
        "salary_ok": "salary",
    }

    def __init__(
        self,
        evaluators: Iterable[Any],
        *,
        score_weights: dict[str, float] | None = None,
        thresholds: dict[DecisionType, float] | None = None,
    ) -> None:
        self._evaluators = list(evaluators)
        self._score_weights = score_weights or self.DEFAULT_WEIGHTS.copy()
        self._thresholds = thresholds or self.DEFAULT_THRESHOLDS.copy()

    def evaluate(
        self,
        *,
        candidate: CandidateProfile,
        job: JobDescription,
        context: dict[str, Any] | None = None,
    ) -> ScreeningOutcome:
        serialized_candidate = candidate.model_dump(mode="python")
        evaluation_context = {"job": job.model_dump(mode="python")}
        if context:
            evaluation_context.update(context)

        evaluations: list[EvaluationResult] = []
        aggregated_scores: dict[str, float] = {}

        for evaluator in self._evaluators:
            raw_result = evaluator.evaluate(serialized_candidate, evaluation_context)
            normalized = self._normalize_evaluation_result(raw_result)
            evaluations.append(normalized)
            for key, value in normalized.scores.items():
                aggregated_scores[key] = aggregated_scores.get(key, 0.0) + float(value)

        pre_llm_score = self._compute_weighted_score(aggregated_scores)
        aggregate = AggregateScores(
            scores=aggregated_scores,
            pre_llm_score=pre_llm_score,
        )

        hard_gate_flags, hard_gate_details = self._evaluate_hard_gates(candidate, job)
        hard_failures = [
            self._HARD_GATE_LABELS.get(k, k)
            for k, ok in hard_gate_flags.items()
            if not ok
        ]
        final_decision = self._decide(pre_llm_score, hard_failures)

        decision = DecisionSummary(
            decision=final_decision,
            pre_llm_score=pre_llm_score,
            hard_gate_flags=hard_gate_flags,
            hard_gate_details=hard_gate_details,
            hard_failures=hard_failures,
        )

        return ScreeningOutcome(
            candidate_id=candidate.candidate_id,
            job_id=job.job_id,
            evaluations=evaluations,
            aggregate=aggregate,
            decision=decision,
        )

    @staticmethod
    def _normalize_evaluation_result(payload: dict[str, Any]) -> EvaluationResult:
        method = payload.get("method")
        scores = payload.get("scores") or {}
        metadata = payload.get("metadata") or {}
        if method is None:
            raise ValueError("Evaluator result must include 'method'.")
        if not isinstance(scores, dict):
            raise ValueError("Evaluator result 'scores' must be a mapping.")
        return EvaluationResult(
            method=str(method),
            scores={k: float(v) for k, v in scores.items()},
            metadata=dict(metadata),
        )

    def _compute_weighted_score(self, scores: dict[str, float]) -> float:
        return sum(
            scores.get(metric, 0.0) * weight
            for metric, weight in self._score_weights.items()
        )

    def _decide(self, score: float, hard_failures: list[str]) -> DecisionType:
        if hard_failures:
            return "reject"

        if score >= self._thresholds["pass"]:
            return "pass"
        if score >= self._thresholds["borderline"]:
            return "borderline"
        return "reject"

    def _evaluate_hard_gates(
        self,
        candidate: CandidateProfile,
        job: JobDescription,
    ) -> tuple[dict[str, bool], dict[str, Any]]:
        constraints = job.constraints

        salary_ok, salary_detail = self._salary_gate(candidate, constraints.salary_range)

        flags = {
            "location_ok": True,
            "salary_ok": salary_ok,
        }
        details = {
            "location": {
                "status": "not_checked",
                "required_locations": constraints.location,
                "candidate_locations": [],
                "matched_locations": [],
            },
            "salary": salary_detail,
        }
        return flags, details
    @staticmethod
    def _salary_gate(
        candidate: CandidateProfile,
        salary_range: Any,
    ) -> tuple[bool, dict[str, Any]]:
        min_required = getattr(salary_range, "min_jpy", None) if salary_range else None
        max_required = getattr(salary_range, "max_jpy", None) if salary_range else None

        desired_min = candidate.desired_salary_min_jpy
        desired_max = candidate.desired_salary_max_jpy

        detail = {
            "required_range": {"min": min_required, "max": max_required},
            "candidate_desired": {"min": desired_min, "max": desired_max},
        }

        if min_required is None and max_required is None:
            detail["status"] = "not_specified"
            return True, detail

        if desired_min is None and desired_max is None:
            detail["status"] = "insufficient_candidate_data"
            return True, detail

        if desired_min is not None and max_required is not None and desired_min > max_required:
            detail["status"] = "above_required_max"
            return False, detail

        if desired_max is not None and min_required is not None and desired_max < min_required:
            detail["status"] = "below_required_min"
            return False, detail

        detail["status"] = "ok"
        return True, detail
