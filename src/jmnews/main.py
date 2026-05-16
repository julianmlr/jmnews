"""Typer CLI entrypoint for jmnews."""

from __future__ import annotations

import typer

from jmnews import __version__
from jmnews.config import get_settings
from jmnews.pipeline import run_once as _run_once
from jmnews.pipeline import setup_logging

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command("run-once")
def run_once_cmd() -> None:
    """Run the full collect → filter → briefing → deliver pipeline once."""
    settings = get_settings()
    setup_logging(settings)
    summary = _run_once(settings)
    typer.echo(
        f"run_id={summary.run_id} new={summary.new_items} "
        f"filtered={summary.filtered} briefing_items={summary.briefing_items} "
        f"ignored={summary.ignored_count} delivery={summary.delivery_status}"
    )


@app.command("run-daemon")
def run_daemon_cmd() -> None:
    """Run scheduled collection + delivery as a long-running process.

    Implemented in Stage 10.
    """
    raise typer.Exit(code=2)  # not yet implemented


@app.command("version")
def version_cmd() -> None:
    """Print package version."""
    typer.echo(__version__)


if __name__ == "__main__":
    app()
