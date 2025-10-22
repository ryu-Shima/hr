"\"\"\"Typer CLI entrypoint for the screening pipeline.\"\"\""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import typer

import yaml

from .container import create_container
from .logging import configure_logging
from .pipeline import AuditLogger
from .llm import HTTPLLMClient

app = typer.Typer(help="Candidate resume screening CLI.")


@app.command()
def run(
    candidates: Path = typer.Option(..., exists=True, readable=True, dir_okay=False, help="Candidates JSONL path."),
    job: Path = typer.Option(..., exists=True, readable=True, dir_okay=False, help="Job description JSON path."),
    output: Path = typer.Option(
        ...,
        exists=False,
        file_okay=True,
        dir_okay=False,
        resolve_path=True,
        help="Output JSON path.",
    ),
    as_of: Optional[str] = typer.Option(None, help="Reference date (YYYY-MM or ISO) for tenure calculations."),
    config: Optional[Path] = typer.Option(None, exists=True, readable=True, dir_okay=False, help="YAML config path."),
    log_level: str = typer.Option("INFO", help="Log level for structured logging."),
    audit_log: Optional[Path] = typer.Option(None, dir_okay=False, help="Audit log output (JSONL)."),
    llm_endpoint: Optional[str] = typer.Option(None, help="LLM rerank API endpoint."),
    llm_api_key: Optional[str] = typer.Option(None, help="LLM rerank API key."),
) -> None:
    """Run the screening pipeline."""
    settings: dict[str, Any] = {}
    if config:
        with config.open("r", encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle) or {}
            if not isinstance(loaded, dict):
                raise typer.BadParameter("Config file must be a YAML object", param_name="config")
            settings = loaded

    configure_logging(log_level)

    container = create_container(settings=settings)
    pipeline = container.pipeline()
    audit_logger = AuditLogger(audit_log) if audit_log else None
    llm_client = HTTPLLMClient(llm_endpoint, llm_api_key) if llm_endpoint else None

    results = pipeline.run(
        candidates_path=candidates,
        job_path=job,
        output_path=output,
        as_of=as_of,
        audit_logger=audit_logger,
        llm_client=llm_client,
    )
    typer.echo(f"Processed {len(results)} candidates. Results saved to {output}.")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
