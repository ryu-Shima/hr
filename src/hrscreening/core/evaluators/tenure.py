"\"\"\"Employment tenure evaluation.\"\"\""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import pendulum

from ...schemas import CandidateProfile, ExperienceEntry


@dataclass
class TenureConfig:
    """Configuration thresholds for tenure evaluation."""

    average_threshold_months: float = 18.0
    recent_short_threshold_months: float = 12.0
    contract_average_threshold_months: float = 12.0
    recent_window: int = 3
    contract_types: tuple[str, ...] = ("contract", "freelance", "業務委託")


class TenureEvaluator:
    """Evaluate candidate stability based on tenure length."""

    method = "tenure"

    def __init__(
        self,
        *,
        config: TenureConfig | None = None,
        now_provider: Any | None = None,
    ) -> None:
        self._config = config or TenureConfig()
        self._now_provider = now_provider or pendulum.now

    def evaluate(self, candidate: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        profile = CandidateProfile.model_validate(candidate)
        as_of = self._resolve_as_of(context)
        per_experience = self._compute_per_experience(profile.experiences, as_of)

        average_months = self._average_months(per_experience)
        recent_short_count = self._count_recent_short(per_experience)
        is_job_hopper = bool(
            per_experience
            and average_months < self._config.average_threshold_months
            and recent_short_count >= 2
        )

        is_contract_profile = self._is_contract_profile(per_experience)
        contract_avg_months = self._average_months(
            [exp for exp in per_experience if exp["is_contract"]]
        )

        passes_contract_rule = (
            is_contract_profile
            and contract_avg_months >= self._config.contract_average_threshold_months
        )

        passes = not is_job_hopper or passes_contract_rule

        return {
            "method": self.method,
            "scores": {
                "tenure_pass": 1.0 if passes else 0.0,
                "tenure_avg_months": average_months,
            },
            "metadata": {
                "average_months": average_months,
                "per_experience": per_experience,
                "recent_short_tenures": recent_short_count,
                "is_job_hopper": is_job_hopper,
                "is_contract_profile": is_contract_profile,
                "contract_average_months": contract_avg_months,
                "passes_contract_rule": passes_contract_rule,
            },
        }

    def _compute_per_experience(
        self,
        experiences: Iterable[ExperienceEntry],
        as_of: pendulum.DateTime,
    ) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for experience in experiences:
            months = self._months_for_experience(experience, as_of)
            if months is None:
                continue
            end_date = self._parse_date(experience.end, default=as_of)
            normalized.append(
                {
                    "company": experience.company,
                    "title": experience.title,
                    "months": months,
                    "employment_type": experience.employment_type,
                    "end_date": end_date,
                    "is_contract": self._is_contract(experience.employment_type),
                }
            )

        normalized.sort(key=lambda item: item["end_date"] or as_of, reverse=True)
        return normalized

    def _months_for_experience(
        self,
        experience: ExperienceEntry,
        as_of: pendulum.DateTime,
    ) -> float | None:
        start_date = self._parse_date(experience.start)
        if start_date is None:
            return None
        end_date = self._parse_date(experience.end, default=as_of)
        if end_date < start_date:
            return None

        return end_date.diff(start_date).in_months()

    @staticmethod
    def _parse_date(value: str | None, *, default: pendulum.DateTime | None = None) -> pendulum.DateTime | None:
        if not value:
            return default
        try:
            if len(value) == 7 and value[4] == "-":
                return pendulum.datetime(int(value[:4]), int(value[5:7]), 1)
            return pendulum.parse(value)
        except (ValueError, pendulum.parsing.exceptions.ParserError):
            return default

    def _count_recent_short(self, experiences: list[dict[str, Any]]) -> int:
        window = experiences[: self._config.recent_window]
        return sum(
            1 for item in window if item["months"] < self._config.recent_short_threshold_months
        )

    @staticmethod
    def _average_months(experiences: Iterable[dict[str, Any]]) -> float:
        durations = [float(item["months"]) for item in experiences if item["months"] is not None]
        if not durations:
            return 0.0
        return sum(durations) / len(durations)

    def _is_contract_profile(self, experiences: list[dict[str, Any]]) -> bool:
        if not experiences:
            return False
        total = len(experiences)
        contract_count = sum(1 for item in experiences if item["is_contract"])
        return contract_count == total

    def _is_contract(self, employment_type: str | None) -> bool:
        if employment_type is None:
            return False
        normalized = employment_type.strip().lower()
        return normalized in {etype.lower() for etype in self._config.contract_types}

    def _resolve_as_of(self, context: dict[str, Any]) -> pendulum.DateTime:
        as_of = context.get("as_of")
        default_now = self._now_provider()
        if as_of is None:
            return default_now
        if isinstance(as_of, pendulum.DateTime):
            return as_of
        parsed = self._parse_date(str(as_of), default=default_now)
        return parsed or default_now

