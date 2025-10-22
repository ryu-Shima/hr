from __future__ import annotations

import json
from pathlib import Path

from hrscreening.container import create_container
from hrscreening.pipeline import AuditLogger


class DummyLLMClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def rerank(self, payload: dict) -> dict:
        self.calls.append(payload)
        return {"decision": "pass", "final_score_hint": 0.9}


def test_pipeline_writes_audit_log_and_calls_llm(tmp_path: Path) -> None:
    candidates_path = tmp_path / "candidates.jsonl"
    job_path = tmp_path / "job.json"
    output_path = tmp_path / "results.json"
    audit_path = tmp_path / "audit.jsonl"

    candidate_record = {
        "provider": "bizreach",
        "payload": {
            "candidate_id": "C-LLM",
            "experiences": [
                {
                    "company": "Acme",
                    "title": "SRE",
                    "start": "2020-01",
                    "end": "2024-01",
                    "bullets": ["TerraformでAWS環境をIaC化"],
                }
            ],
            "skills": ["Terraform", "AWS"],
            "languages": [{"language": "日本語", "level": "ネイティブ"}],
        },
    }

    job_record = {
        "job_id": "JD-LLM",
        "requirements_text": ["Terraformを用いたIaC構築経験"],
        "key_phrases": ["Terraform", "IaC"],
        "constraints": {"language": ["ja"], "salary_range": {"min_jpy": 5000000, "max_jpy": 9000000}},
    }

    candidates_path.write_text(json.dumps(candidate_record, ensure_ascii=False), encoding="utf-8")
    job_path.write_text(json.dumps(job_record, ensure_ascii=False), encoding="utf-8")

    container = create_container()
    pipeline = container.pipeline()
    audit_logger = AuditLogger(audit_path)
    dummy_llm = DummyLLMClient()

    results = pipeline.run(
        candidates_path=candidates_path,
        job_path=job_path,
        output_path=output_path,
        audit_logger=audit_logger,
        llm_client=dummy_llm,
    )

    assert dummy_llm.calls, "LLM client should be invoked"
    assert output_path.exists()
    assert audit_path.exists()

    audit_lines = audit_path.read_text(encoding="utf-8").strip().splitlines()
    assert audit_lines
    audit_entry = json.loads(audit_lines[0])
    assert audit_entry["candidate_id"] == "C-LLM"
    assert "llm_response" in audit_entry

    first_result = results[0]
    assert "llm_payload" in first_result
    assert first_result["llm_response"] == {"decision": "pass", "final_score_hint": 0.9}
