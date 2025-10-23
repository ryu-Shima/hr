"\"\"\"Screening pipeline assembly and execution.\"\"\""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Iterable, List

import pendulum
import structlog

from .adapters import BizReachAdapter, ResumeAdapter
from .core import ScreeningCore
from .llm import build_llm_payload
from .schemas import CandidateProfile, JobDescription
from . import __version__


class AdapterRegistry:
    """Registry mapping providers to resume adapters."""

    def __init__(self, adapters: Iterable[ResumeAdapter]):
        self._adapters = {adapter.provider: adapter for adapter in adapters}

    def get(self, provider: str) -> ResumeAdapter:
        try:
            return self._adapters[provider]
        except KeyError as exc:
            raise KeyError(f"Unsupported provider: {provider!r}") from exc

    def providers(self) -> List[str]:
        return list(self._adapters.keys())


class CandidateLoadError(ValueError):
    """Raised when candidate loading encounters invalid records."""

    def __init__(self, errors: list[str], partial: list[CandidateProfile]):
        super().__init__("Candidate loading failed")
        self.errors = errors
        self.partial = partial

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"Candidate loading failed: {self.errors}"


class CandidateLoader:
    """Load candidate profiles through adapters."""

    def __init__(self, registry: AdapterRegistry):
        self._registry = registry

    def load(self, path: Path) -> list[CandidateProfile]:
        candidates: list[CandidateProfile] = []
        errors: list[str] = []
        with path.open("r", encoding="utf-8") as handle:
            for idx, line in enumerate(handle, start=1):
                raw = line.strip()
                if not raw:
                    continue
                try:
                    record = json.loads(raw)
                except json.JSONDecodeError as exc:
                    errors.append(f"line {idx}: invalid JSON ({exc})")
                    continue
                provider = record.get("provider")
                if not provider:
                    errors.append(f"line {idx}: missing provider field")
                    continue
                try:
                    adapter = self._registry.get(provider)
                except KeyError:
                    errors.append(f"line {idx}: unsupported provider '{provider}'")
                    continue
                payload = record.get("payload", record)
                try:
                    candidate_dict = adapter.parse_candidate(
                        json.dumps(payload, ensure_ascii=False)
                    )
                    candidate = CandidateProfile.model_validate(candidate_dict)
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"line {idx}: {exc}")
                    continue
                candidates.append(candidate)
        if errors:
            raise CandidateLoadError(errors, candidates)
        return candidates


class JobLoader:
    """Load job description documents."""

    def load(self, path: Path) -> JobDescription:
        with path.open("r", encoding="utf-8") as handle:
            try:
                data = json.load(handle)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid job JSON: {exc}") from exc
        return JobDescription.model_validate(data)


class OutputWriter:
    """Persist screening outcomes."""

    def write(self, path: Path, payload: dict | list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


class ScreeningPipeline:
    """End-to-end screening orchestrator."""

    def __init__(
        self,
        *,
        core: ScreeningCore,
        registry: AdapterRegistry,
        candidate_loader: CandidateLoader | None = None,
        job_loader: JobLoader | None = None,
        writer: OutputWriter | None = None,
    ) -> None:
        self._core = core
        self._registry = registry
        self._candidates = candidate_loader or CandidateLoader(registry)
        self._jobs = job_loader or JobLoader()
        self._writer = writer or OutputWriter()
        self._logger = structlog.get_logger(__name__)

    def run(
        self,
        *,
        candidates_path: Path,
        job_path: Path,
        output_path: Path,
        as_of: str | None = None,
        audit_logger: "AuditLogger | None" = None,
    ) -> list[dict]:
        job = self._jobs.load(job_path)
        load_errors: list[str] = []
        try:
            candidates = self._candidates.load(candidates_path)
        except CandidateLoadError as exc:
            candidates = exc.partial
            load_errors.extend(exc.errors)
            self._logger.warning("candidates.partial_load", errors=exc.errors)

        serialized_results: list[dict] = []

        for candidate in candidates:
            outcome = self._core.evaluate(
                candidate=candidate,
                job=job,
                context={"as_of": as_of} if as_of else None,
            )
            llm_payload = build_llm_payload(job=job, candidate=candidate, outcome=outcome)

            outcome_dict = asdict(outcome)
            outcome_dict["llm_payload"] = llm_payload

            serialized_entry = json.loads(
                json.dumps(outcome_dict, default=_json_default, ensure_ascii=False)
            )
            serialized_results.append(serialized_entry)

            if audit_logger:
                audit_logger.append(
                    {
                        "candidate_id": candidate.candidate_id,
                        "job_id": job.job_id,
                        "pre_llm_score": outcome.aggregate.pre_llm_score,
                        "decision": outcome.decision.decision,
                        "hard_gate_flags": outcome.decision.hard_gate_flags,
                        "hard_gate_details": outcome.decision.hard_gate_details,
                        "llm_payload": llm_payload,
                    }
                )

            self._logger.info(
                "screening.result",
                candidate_id=candidate.candidate_id,
                job_id=job.job_id,
                decision=outcome.decision.decision,
                pre_llm_score=outcome.aggregate.pre_llm_score,
                hard_gate_flags=outcome.decision.hard_gate_flags,
                hard_gate_details=outcome.decision.hard_gate_details,
            )

        metadata = {
            "job_id": job.job_id,
            "candidate_count": len(candidates),
            "errors": load_errors,
            "timestamp": pendulum.now().to_iso8601_string(),
            "app_version": __version__,
        }
        payload_with_meta = {
            "metadata": metadata,
            "results": serialized_results,
        }

        self._writer.write(output_path, payload_with_meta)
        return serialized_results


def default_registry() -> AdapterRegistry:
    """Return the default adapter registry."""
    return AdapterRegistry(adapters=[BizReachAdapter()])


def _json_default(value):  # type: ignore[override]
    if isinstance(value, pendulum.DateTime):
        return value.to_iso8601_string()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


class AuditLogger:
    """Append-only audit logger writing JSON lines."""

    def __init__(self, path: Path):
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: dict) -> None:
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False))
            handle.write("\n")
