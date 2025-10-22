"\"\"\"Salary expectation evaluation.\"\"\""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...schemas import CandidateProfile, JobDescription


@dataclass
class SalaryConfig:
    """Configuration for salary matching."""

    tolerance_ratio: float = 0.10


class SalaryEvaluator:
    """Compare candidate desired salary with job range."""

    method = "salary"

    def __init__(self, *, config: SalaryConfig | None = None) -> None:
        self._config = config or SalaryConfig()

    def evaluate(self, candidate: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        profile = CandidateProfile.model_validate(candidate)
        job = JobDescription.model_validate(context["job"])
        desired_range = self._candidate_range(profile)
        job_range = self._job_range(job)

        if desired_range is None or job_range is None:
            return self._build_response(
                passes=True,
                desired_range=desired_range,
                job_range=job_range,
                message="insufficient_data",
            )

        expanded_job_min = (
            job_range[0] * (1 - self._config.tolerance_ratio)
            if job_range[0] is not None
            else None
        )
        expanded_job_max = (
            job_range[1] * (1 + self._config.tolerance_ratio)
            if job_range[1] is not None
            else None
        )

        passes = self._ranges_overlap(
            desired_range,
            (expanded_job_min, expanded_job_max),
        )

        overlap_span = self._overlap_span(
            desired_range,
            (expanded_job_min, expanded_job_max),
        )

        return self._build_response(
            passes=passes,
            desired_range=desired_range,
            job_range=job_range,
            expanded_job_range=(expanded_job_min, expanded_job_max),
            overlap_span=overlap_span,
        )

    @staticmethod
    def _candidate_range(profile: CandidateProfile) -> tuple[int | None, int | None] | None:
        minimum = profile.desired_salary_min_jpy
        maximum = profile.desired_salary_max_jpy
        if minimum is None and maximum is None:
            return None
        if minimum is None:
            minimum = maximum
        if maximum is None:
            maximum = minimum
        if minimum is None or maximum is None:
            return None
        if minimum > maximum:
            minimum, maximum = maximum, minimum
        return minimum, maximum

    @staticmethod
    def _job_range(job: JobDescription) -> tuple[int | None, int | None] | None:
        if job.constraints.salary_range is None:
            return None
        return (
            job.constraints.salary_range.min_jpy,
            job.constraints.salary_range.max_jpy,
        )

    @staticmethod
    def _ranges_overlap(
        candidate_range: tuple[int | None, int | None],
        job_range: tuple[int | None, int | None],
    ) -> bool:
        cand_min, cand_max = candidate_range
        job_min, job_max = job_range

        lower_bound = job_min if job_min is not None else cand_min
        upper_bound = job_max if job_max is not None else cand_max

        if lower_bound is None or upper_bound is None:
            return True

        return cand_max >= lower_bound and cand_min <= upper_bound

    @staticmethod
    def _overlap_span(
        candidate_range: tuple[int | None, int | None],
        job_range: tuple[int | None, int | None],
    ) -> float | None:
        cand_min, cand_max = candidate_range
        job_min, job_max = job_range
        if cand_min is None or cand_max is None:
            return None
        low = max(cand_min if cand_min is not None else float("-inf"), job_min or cand_min)
        high = min(cand_max if cand_max is not None else float("inf"), job_max or cand_max)
        if high < low:
            return None
        return float(high - low)

    def _build_response(
        self,
        *,
        passes: bool,
        desired_range: tuple[int | None, int | None] | None,
        job_range: tuple[int | None, int | None] | None,
        expanded_job_range: tuple[float | None, float | None] | None = None,
        overlap_span: float | None = None,
        message: str | None = None,
    ) -> dict[str, Any]:
        return {
            "method": self.method,
            "scores": {
                "salary_pass": 1.0 if passes else 0.0,
                "salary_overlap_span": overlap_span or 0.0,
            },
            "metadata": {
                "desired_range": desired_range,
                "job_range": job_range,
                "expanded_job_range": expanded_job_range,
                "overlap_span": overlap_span,
                "tolerance_ratio": self._config.tolerance_ratio,
                "message": message,
            },
        }

