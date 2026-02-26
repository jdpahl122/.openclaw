"""Summarisation layer – two modes.

Mode A (default):  Simple extractive summariser using title + snippet.
Mode B (opt-in):   LLM-ready prompt builder – returns a prompt string you can
                   send to any OpenAI-compatible API.  No API keys are
                   hardcoded; the caller is responsible for the LLM call.
"""

from __future__ import annotations

import logging
from datetime import datetime

from models import GroupedSection, NormalizedStory
from utils.text import first_sentences, truncate
from utils.time import now_utc, relative_age

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Mode A – extractive (no LLM)
# ---------------------------------------------------------------------------

def summarise_story_extractive(story: NormalizedStory) -> str:
    """Return a 1-3 sentence extractive summary for a single story."""
    parts: list[str] = []
    parts.append(story.title)
    if story.snippet:
        parts.append(first_sentences(story.snippet, 2))
    elif story.content:
        parts.append(first_sentences(story.content, 2))
    return " — ".join(parts)


def build_digest_markdown(
    stories: list[NormalizedStory],
    *,
    hours: int = 24,
) -> str:
    """Build a human-readable Markdown digest of the top stories."""
    lines: list[str] = []
    now = now_utc()
    lines.append(f"# WNY News Digest")
    lines.append(f"Generated: {now:%Y-%m-%d %H:%M UTC}  |  Window: last {hours}h\n")
    lines.append("---\n")

    grouped = _group_by_topic(stories)
    for section in grouped:
        lines.append(f"## {section.topic.replace('_', ' ').title()}\n")
        for i, s in enumerate(section.stories, 1):
            age = relative_age(s.published_at)
            summary = summarise_story_extractive(s)
            sources_note = f" ({s.cross_source_count} sources)" if s.cross_source_count > 1 else ""
            tag = ""
            if s.is_official_source:
                tag = " `[OFFICIAL]`"
            lines.append(f"**{i}. [{s.title}]({s.url})**{tag}{sources_note}")
            lines.append(f"   {truncate(summary, 280)}  _{age}_\n")
        lines.append("")

    lines.append("---")
    lines.append(f"_Total stories: {len(stories)}_\n")
    return "\n".join(lines)


def build_digest_summary(stories: list[NormalizedStory], *, top_n: int = 5) -> str:
    """One-paragraph top-level summary for quick consumption."""
    if not stories:
        return "No stories found in this time window."
    headlines = [s.title for s in stories[:top_n]]
    return "Top WNY stories: " + " • ".join(headlines)


# ---------------------------------------------------------------------------
# Mode B – LLM-ready prompt builder
# ---------------------------------------------------------------------------

def build_llm_prompt(
    stories: list[NormalizedStory],
    *,
    max_stories: int = 15,
    persona: str = "a concise, factual local-news editor for Western New York",
) -> str:
    """Return a prompt string suitable for an OpenAI ChatCompletion call.

    The caller is responsible for sending this to the LLM and handling the
    response.  No API keys are touched here.
    """
    items: list[str] = []
    for i, s in enumerate(stories[:max_stories], 1):
        age = relative_age(s.published_at)
        items.append(
            f"{i}. [{s.source}] {s.title}\n"
            f"   URL: {s.url}\n"
            f"   Published: {age}\n"
            f"   Snippet: {truncate(s.snippet or s.content or 'N/A', 200)}"
        )

    story_block = "\n\n".join(items)

    return f"""You are {persona}.

Below are the top {len(stories[:max_stories])} local stories from the Buffalo / Western New York area gathered in the last 24 hours.

STORIES:
{story_block}

INSTRUCTIONS:
1. Write a concise daily digest (5-8 bullet points) covering the most important stories.
2. Group by topic where natural (General News, Sports, Civic/Government, Weather).
3. For each bullet: one headline sentence + one context sentence. Cite the source in brackets.
4. If multiple outlets cover the same story, note that briefly.
5. End with a 1-sentence overall takeaway.
6. Tone: concise, factual, local-news style. No fluff. Mention uncertainty when details conflict.
7. Tag any story that appears breaking or developing.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _group_by_topic(stories: list[NormalizedStory]) -> list[GroupedSection]:
    """Group stories by topic, preserving score order within each group."""
    buckets: dict[str, list[NormalizedStory]] = {}
    # Desired display order
    order = ["news", "sports", "civic", "weather", "traffic", "education", "other"]
    for s in stories:
        buckets.setdefault(s.topic.value, []).append(s)

    sections: list[GroupedSection] = []
    for topic in order:
        if topic in buckets:
            sections.append(GroupedSection(topic=topic, stories=buckets[topic]))
    return sections


def compact_payload(stories: list[NormalizedStory]) -> list[dict]:
    """Return a lightweight list of dicts suitable for downstream agent use."""
    return [
        {
            "headline": s.title,
            "summary": summarise_story_extractive(s),
            "source_urls": [s.url],
            "topic": s.topic.value,
            "subtopic": s.subtopic,
            "score": s.score,
            "age": relative_age(s.published_at),
            "cross_sources": s.cross_source_count,
        }
        for s in stories
    ]
