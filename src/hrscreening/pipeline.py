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


class CandidateLoader:
    """Load candidate profiles through adapters."""

    def __init__(self, registry: AdapterRegistry):
        self._registry = registry

    def load(self, path: Path) -> list[CandidateProfile]:
        candidates: list[CandidateProfile] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                record = json.loads(line)
                provider = record.get("provider")
                if not provider:
                    raise ValueError("Candidate record missing provider.")
                adapter = self._registry.get(provider)
                payload = record.get("payload", record)
                candidate_dict = adapter.parse_candidate(
                    json.dumps(payload, ensure_ascii=False)
                )
                candidates.append(
                    CandidateProfile.model_validate(candidate_dict)
                )
        return candidates


class JobLoader:
    """Load job description documents."""

    def load(self, path: Path) -> JobDescription:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return JobDescription.model_validate(data)


class OutputWriter:
    """Persist screening outcomes."""

    def write(self, path: Path, payload: list[dict]) -> None:
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
        llm_client: "LLMClientProtocol | None" = None,
    ) -> list[dict]:
        job = self._jobs.load(job_path)
        candidates = self._candidates.load(candidates_path)

        serialized_results: list[dict] = []

        for candidate in candidates:
            outcome = self._core.evaluate(
                candidate=candidate,
                job=job,
                context={"as_of": as_of} if as_of else None,
            )
            llm_payload = build_llm_payload(job=job, candidate=candidate, outcome=outcome)
            llm_response = None
            if llm_client:
                llm_response = llm_client.rerank(llm_payload)

            outcome_dict = asdict(outcome)
            outcome_dict["llm_payload"] = llm_payload
            outcome_dict["llm_response"] = llm_response

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
                        "llm_payload": llm_payload,
                        "llm_response": llm_response,
                    }
                )

            self._logger.info(
                "screening.result",
                candidate_id=candidate.candidate_id,
                job_id=job.job_id,
                decision=outcome.decision.decision,
                pre_llm_score=outcome.aggregate.pre_llm_score,
                llm_response=llm_response,
            )

        self._writer.write(output_path, serialized_results)
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


class LLMClientProtocol:
    """Protocol for LLM rerank clients."""

    def rerank(self, payload: dict) -> dict | None:  # pragma: no cover - interface
        raise NotImplementedError
