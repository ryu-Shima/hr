"\"\"\"Typer CLI entrypoint for the screening pipeline.\"\"\""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from .container import create_container

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
) -> None:
    """Run the screening pipeline."""
    container = create_container()
    pipeline = container.pipeline()
    results = pipeline.run(
        candidates_path=candidates,
        job_path=job,
        output_path=output,
        as_of=as_of,
    )
    typer.echo(f"Processed {len(results)} candidates. Results saved to {output}.")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
