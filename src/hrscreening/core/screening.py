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
        "bm25_prox": 0.45,
        "embed_sim": 0.40,
        "sim_title": 0.10,
        "title_bonus": 0.05,
    }

    DEFAULT_THRESHOLDS: dict[DecisionType, float] = {
        "pass": 0.80,
        "borderline": 0.65,
        "reject": 0.0,
    }

    _HARD_GATE_LABELS: dict[str, str] = {
        "language_ok": "language",
        "location_ok": "location",
        "visa_ok": "visa",
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

        hard_gate_flags = self._evaluate_hard_gates(candidate, job)
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
    ) -> dict[str, bool]:
        constraints = job.constraints
        candidate_constraints = candidate.constraints

        return {
            "language_ok": self._language_ok(candidate, constraints.language),
            "location_ok": self._location_ok(candidate, constraints.location),
            "visa_ok": self._visa_ok(candidate_constraints, constraints.visa),
            "salary_ok": self._salary_ok(candidate, constraints.salary_range),
        }

    @staticmethod
    def _language_ok(
        candidate: CandidateProfile,
        required_languages: list[str],
    ) -> bool:
        if not required_languages:
            return True
        candidate_langs = {
            ScreeningCore._normalize_language(lang.language)
            for lang in candidate.languages or []
        }
        if not candidate_langs:
            return False

        required = {
            ScreeningCore._normalize_language(lang) for lang in required_languages
        }
        return bool(candidate_langs & required)

    @staticmethod
    def _location_ok(candidate: CandidateProfile, required_locations: list[str]) -> bool:
        if not required_locations:
            return True
        if not candidate.location:
            return False
        candidate_location = candidate.location.strip().lower()
        normalized_required = {loc.strip().lower() for loc in required_locations}
        return candidate_location in normalized_required

    @staticmethod
    def _visa_ok(
        candidate_constraints: Any,
        required_visa: str | None,
    ) -> bool:
        if not required_visa:
            return True
        candidate_visa = None
        if candidate_constraints and candidate_constraints.visa:
            candidate_visa = candidate_constraints.visa.strip().lower()

        if candidate_visa is None:
            return False
        if candidate_visa in {"ok", "valid", "yes"}:
            return True
        return candidate_visa == required_visa.strip().lower()

    @staticmethod
    def _salary_ok(candidate: CandidateProfile, salary_range: Any) -> bool:
        if salary_range is None:
            return True
        min_required = salary_range.min_jpy
        max_required = salary_range.max_jpy
        if min_required is None and max_required is None:
            return True

        desired_min = candidate.desired_salary_min_jpy
        desired_max = candidate.desired_salary_max_jpy

        if desired_min is None and desired_max is None:
            return True

        if desired_min is not None and max_required is not None:
            if desired_min > max_required:
                return False

        if desired_max is not None and min_required is not None:
            if desired_max < min_required:
                return False

        return True

    @staticmethod
    def _normalize_language(language: str) -> str:
        if not language:
            return ""
        normalized = language.strip().lower()
        aliases = {
            "日本語": "ja",
            "にほんご": "ja",
            "japanese": "ja",
            "jp": "ja",
            "ja": "ja",
            "英語": "en",
            "えいご": "en",
            "english": "en",
            "en": "en",
        }
        return aliases.get(normalized, normalized)
