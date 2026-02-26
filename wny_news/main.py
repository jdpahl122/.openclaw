#!/Users/jpahl/.pyenv/versions/3.11.11/bin/python3
"""WNY News Digest CLI.

Usage:
    ./main.py digest              # run full pipeline, default 24h / top 10
    ./main.py digest --hours 12 --top 5 --topic sports
    ./main.py digest --output-dir /tmp/wny
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import click

from utils.logging_utils import setup_logging


@click.group()
def cli():
    """WNY local news digest tool."""
    pass


@cli.command()
@click.option("--hours", default=24, show_default=True, help="Look-back window in hours")
@click.option("--top", "top_n", default=10, show_default=True, help="Number of top stories")
@click.option("--topic", default=None, help="Filter by topic (news/sports/civic/weather/traffic)")
@click.option("--output-dir", default=None, help="Override output directory")
@click.option("--json-only", is_flag=True, help="Print compact JSON to stdout and exit")
@click.option("--log-level", default=None, help="Override log level (DEBUG/INFO/WARNING)")
def digest(hours: int, top_n: int, topic: str | None, output_dir: str | None,
           json_only: bool, log_level: str | None):
    """Run the full news digest pipeline."""
    setup_logging(log_level)

    from pipeline import run_wny_digest

    result = run_wny_digest(hours=hours, top_n=top_n, topic=topic, output_dir=output_dir)

    if json_only:
        click.echo(json.dumps(result, indent=2, default=str))
    else:
        click.echo(f"\n✓ Digest complete: {result['story_count']} stories")
        click.echo(f"  Digest:  {result['digest_path']}")
        click.echo(f"  Report:  {result['report_path']}")
        click.echo(f"\n{result['summary']}")

    sys.exit(0 if result.get("status") == "ok" else 1)


@cli.command()
@click.option("--hours", default=24, show_default=True)
@click.option("--top", "top_n", default=10, show_default=True)
@click.option("--topic", default=None)
def summary(hours: int, top_n: int, topic: str | None):
    """Print a quick one-line summary of top headlines."""
    setup_logging("WARNING")

    from pipeline import run_wny_digest

    result = run_wny_digest(hours=hours, top_n=top_n, topic=topic)
    click.echo(result["summary"])


@cli.command()
def sources():
    """List configured news sources and their feed URLs."""
    from config import HTML_SOURCES, RSS_FEEDS, SOURCE_PRIORITIES

    click.echo("RSS Sources:")
    for name, feeds in RSS_FEEDS.items():
        pri = SOURCE_PRIORITIES.get(name, 0.5)
        click.echo(f"  {name} (priority: {pri})")
        for section, url in feeds.items():
            click.echo(f"    {section}: {url}")

    click.echo("\nHTML Sources:")
    for name, pages in HTML_SOURCES.items():
        pri = SOURCE_PRIORITIES.get(name, 0.5)
        click.echo(f"  {name} (priority: {pri})")
        for section, url in pages.items():
            click.echo(f"    {section}: {url}")


if __name__ == "__main__":
    cli()
