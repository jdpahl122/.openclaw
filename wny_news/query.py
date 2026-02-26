#!/Users/jpahl/.pyenv/versions/3.11.11/bin/python3
"""OpenClaw query interface for the WNY news digest.

Provides simple CLI sub-commands that the OpenClaw agent can invoke via
the ``exec`` tool.  Each command produces plain-text or JSON output
suitable for agent consumption.

Usage (via OpenClaw exec tool):
    /Users/jpahl/.openclaw/wny_news/query.py digest
    /Users/jpahl/.openclaw/wny_news/query.py digest --hours 12 --top 5
    /Users/jpahl/.openclaw/wny_news/query.py sports
    /Users/jpahl/.openclaw/wny_news/query.py headlines
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import click

from utils.logging_utils import setup_logging


@click.group()
def cli():
    """WNY News – OpenClaw query interface."""
    pass


@cli.command()
@click.option("--hours", default=24, show_default=True)
@click.option("--top", "top_n", default=10, show_default=True)
def digest(hours: int, top_n: int):
    """Full digest with summaries (default command)."""
    setup_logging("WARNING")
    from pipeline import run_wny_digest

    result = run_wny_digest(hours=hours, top_n=top_n)
    # Read the generated markdown
    md_path = Path(result["digest_path"])
    if md_path.exists():
        click.echo(md_path.read_text())
    else:
        click.echo(result["summary"])


@cli.command()
@click.option("--hours", default=24, show_default=True)
@click.option("--top", "top_n", default=10, show_default=True)
def headlines(hours: int, top_n: int):
    """Quick headline list."""
    setup_logging("WARNING")
    from pipeline import run_wny_digest

    result = run_wny_digest(hours=hours, top_n=top_n)
    for i, s in enumerate(result["stories"], 1):
        topic_tag = f"[{s['topic']}]" if s.get("topic") else ""
        click.echo(f"{i:2d}. {topic_tag} {s['headline']}  ({s['age']})")


@cli.command()
@click.option("--hours", default=24, show_default=True)
@click.option("--top", "top_n", default=10, show_default=True)
def sports(hours: int, top_n: int):
    """Sports-only digest."""
    setup_logging("WARNING")
    from pipeline import run_wny_digest

    result = run_wny_digest(hours=hours, top_n=top_n, topic="sports")
    for i, s in enumerate(result["stories"], 1):
        sub = f" [{s['subtopic']}]" if s.get("subtopic") else ""
        click.echo(f"{i:2d}.{sub} {s['headline']}  ({s['age']})")
    if not result["stories"]:
        click.echo("No sports stories in the last {hours}h.")


@cli.command()
@click.option("--hours", default=24, show_default=True)
@click.option("--top", "top_n", default=10, show_default=True)
def civic(hours: int, top_n: int):
    """Civic / government news only."""
    setup_logging("WARNING")
    from pipeline import run_wny_digest

    result = run_wny_digest(hours=hours, top_n=top_n, topic="civic")
    for i, s in enumerate(result["stories"], 1):
        click.echo(f"{i:2d}. {s['headline']}  ({s['age']})")
    if not result["stories"]:
        click.echo(f"No civic stories in the last {hours}h.")


@cli.command(name="json")
@click.option("--hours", default=24, show_default=True)
@click.option("--top", "top_n", default=10, show_default=True)
@click.option("--topic", default=None)
def json_output(hours: int, top_n: int, topic: str | None):
    """Full JSON output for programmatic use."""
    setup_logging("WARNING")
    from pipeline import run_wny_digest

    result = run_wny_digest(hours=hours, top_n=top_n, topic=topic)
    click.echo(json.dumps(result, indent=2, default=str))


@cli.command()
def status():
    """Show last run report if available."""
    report_path = Path(__file__).resolve().parent / "output" / "run_report.json"
    if not report_path.exists():
        click.echo("No previous run found. Run `digest` first.")
        return

    data = json.loads(report_path.read_text())
    click.echo("Last WNY News Run")
    click.echo("=" * 40)
    click.echo(f"  Time:     {data.get('start_time', '?')} → {data.get('end_time', '?')}")
    click.echo(f"  Duration: {data.get('duration_seconds', 0):.1f}s")
    click.echo(f"  Sources:  {data.get('sources_succeeded', 0)}/{data.get('sources_attempted', 0)} OK")
    click.echo(f"  Stories:  {data.get('raw_count', 0)} raw → {data.get('final_count', 0)} final")
    if data.get("errors"):
        click.echo(f"  Errors:   {len(data['errors'])}")
        for e in data["errors"]:
            click.echo(f"    - {e.get('source', '?')}: {e.get('error', '?')[:80]}")


if __name__ == "__main__":
    cli()
