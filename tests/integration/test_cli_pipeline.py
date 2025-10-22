from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from hrscreening.cli import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_cli_runs_pipeline_and_writes_output(tmp_path: Path, runner: CliRunner) -> None:
    candidates_path = tmp_path / "candidates.jsonl"
    job_path = tmp_path / "job.json"
    output_path = tmp_path / "results.json"

    candidates = [
        {
            "provider": "bizreach",
            "payload": {
                "candidate_id": "C-001",
                "name": "田中 太郎",
                "desired_salary_min_jpy": 7_000_000,
                "desired_salary_max_jpy": 9_000_000,
                "experiences": [
                    {
                        "company": "Acme Corp",
                        "title": "Site Reliability Engineer",
                        "start": "2020-01",
                        "end": "2024-12",
                        "employment_type": "full-time",
                        "bullets": [
                            "TerraformでAWS基盤をIaC化",
                            "Prometheusで監視設計",
                        ],
                    }
                ],
                "skills": ["Terraform", "AWS", "Prometheus"],
                "languages": [{"language": "日本語", "level": "ネイティブ"}],
                "constraints": {"visa": "ok"},
            },
        }
    ]

    job = {
        "job_id": "JD-001",
        "locale": "ja-JP",
        "role_titles": ["Site Reliability Engineer"],
        "requirements_text": [
            "Terraformを用いたIaC構築経験",
            "AWS上での運用・監視経験",
        ],
        "key_phrases": ["Terraform", "AWS", "Prometheus"],
        "constraints": {
            "language": ["ja"],
            "location": [],
            "visa": "ok",
            "salary_range": {"min_jpy": 6_000_000, "max_jpy": 9_500_000},
        },
    }

    candidates_path.write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in candidates),
        encoding="utf-8",
    )
    write_json(job_path, job)

    result = runner.invoke(
        app,
        [
            "--candidates",
            str(candidates_path),
            "--job",
            str(job_path),
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert output_path.exists()

    rendered = json.loads(output_path.read_text(encoding="utf-8"))
    assert isinstance(rendered, list)
    assert rendered
    candidate_result = rendered[0]

    assert candidate_result["candidate_id"] == "C-001"
    assert candidate_result["decision"]["decision"] == "pass"
    assert candidate_result["aggregate"]["pre_llm_score"] >= 0.5
    assert candidate_result["evaluations"], "evaluations should not be empty"
