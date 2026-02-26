# WNY News Digest Tool

A production-ready OpenClaw skill/tool that pulls, deduplicates, ranks, and summarises top local Western New York (Buffalo) news and sports stories.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run the full digest (default: last 24h, top 10)
./main.py digest

# Sports only, last 12 hours
./main.py digest --hours 12 --topic sports --top 5

# JSON output to stdout
./main.py digest --json-only
```

## Project Structure

```
wny_news/
├── main.py              CLI entrypoint
├── query.py             OpenClaw skill query interface
├── config.py            All tuneable knobs (sources, weights, thresholds)
├── models.py            Pydantic data models
├── pipeline.py          End-to-end orchestrator
├── ranking.py           Configurable scoring / ranking
├── dedupe.py            Fuzzy deduplication / clustering
├── summarizer.py        Extractive + LLM-ready summarisation
├── sources/
│   ├── base.py          Abstract adapter + RSS helper
│   ├── wgrz.py          WGRZ Channel 2 (RSS)
│   ├── spectrum_buffalo.py  Spectrum News 1 Buffalo (RSS)
│   ├── city_of_buffalo.py   City of Buffalo official (RSS)
│   ├── ub.py            University at Buffalo (RSS)
│   ├── wkbw.py          WKBW 7 News (HTML scraper)
│   ├── wgr550_audacy.py WGR 550 sports radio (HTML scraper)
│   └── wivb.py          WIVB News 4 (RSS + HTML fallback)
├── utils/
│   ├── http.py          Fetch with retry / timeout / User-Agent
│   ├── time.py          Date parsing and time-window filtering
│   ├── text.py          URL normalisation, text cleanup
│   └── logging_utils.py Structured logging setup
├── output/              Generated digest files
│   ├── top_stories.json
│   ├── digest.md
│   └── run_report.json
├── tests/
│   ├── test_normalization.py
│   ├── test_dedupe.py
│   └── test_ranking.py
├── requirements.txt
├── .env.example
└── README.md
```

## Configuration

All settings live in `config.py`. Key areas:

- **SOURCE_PRIORITIES** – per-source trust weight (0–1)
- **TOPIC_PRIORITIES** – per-topic importance weight
- **SPORTS_TEAMS** – keyword lists + boost values for Bills, Sabres, Bisons, Bandits, UB
- **RANKING_WEIGHTS** – dimension weights for the scoring function
- **DEDUPE_TITLE_THRESHOLD** – rapidfuzz similarity cutoff (default 75)
- **RSS_FEEDS / HTML_SOURCES** – feed URLs per source

Override via `.env` file (copy `.env.example`):

```bash
WNY_NEWS_DEFAULT_HOURS=12
WNY_NEWS_DEFAULT_TOP_N=5
WNY_NEWS_LOG_LEVEL=DEBUG
```

## CLI Commands

### main.py (full pipeline)

```bash
./main.py digest                              # default run
./main.py digest --hours 12 --top 5           # custom window
./main.py digest --topic sports               # filter by topic
./main.py digest --json-only                  # stdout JSON
./main.py digest --output-dir /tmp/wny        # custom output dir
./main.py summary                             # one-line headline summary
./main.py sources                             # list configured sources
```

### query.py (OpenClaw agent interface)

```bash
./query.py digest                 # full markdown digest
./query.py headlines              # numbered headline list
./query.py sports                 # sports-only digest
./query.py civic                  # civic/government only
./query.py json                   # full JSON payload
./query.py status                 # last run report
```

## Adding a New Source Adapter

1. Create `sources/my_source.py`
2. Subclass `BaseAdapter` and implement `fetch() -> list[RawStory]`
3. For RSS sources, use `self.fetch_rss(url, section=...)` from the base class
4. For HTML sources, fetch with `utils.http.fetch_url()` and parse with BeautifulSoup
5. Register in `sources/__init__.py` by adding to `ALL_ADAPTERS`
6. Add feed URLs to `config.py` under `RSS_FEEDS` or `HTML_SOURCES`
7. Set a priority in `SOURCE_PRIORITIES`

## OpenClaw Integration

### As a Skill

The tool is registered as an OpenClaw skill. The agent can invoke it via:

```json
{ "command": "/Users/jpahl/.openclaw/wny_news/query.py digest" }
```

### As a Cron Job

Add to `~/.openclaw/cron/jobs.json`:

```json
{
  "id": "wny-news-digest",
  "name": "WNY Morning News Digest",
  "schedule": "0 7 * * *",
  "command": "/Users/jpahl/.openclaw/wny_news/main.py digest --json-only",
  "description": "Daily WNY news digest at 7 AM",
  "enabled": true,
  "notify": {
    "channel": "telegram",
    "onlyOnOutput": true
  }
}
```

### Programmatic Use

```python
from pipeline import run_wny_digest

result = run_wny_digest(hours=24, top_n=10)
# result["stories"]  – compact payload list
# result["summary"]  – one-line summary
# result["digest_path"] – path to markdown file
```

## Summarisation Modes

**Mode A (default):** Extractive – uses title + snippet + first paragraph. Fast, no API keys needed.

**Mode B (LLM-ready):** Call `summarizer.build_llm_prompt(stories)` to get a prompt string for OpenAI / Claude / etc. The caller handles the API call.

## Known Limitations

- **RSS feed URLs may change** – stations occasionally restructure. Check `run_report.json` for source health.
- **HTML scrapers are fragile** – site redesigns will break selectors. Each adapter logs warnings when parsing yields 0 items.
- **React-rendered sites** (WGR550, some WKBW pages) may not have content in initial HTML. Consider adding Playwright if needed.
- **Rate limits** – aggressive polling may trigger blocks. Default User-Agent identifies the tool.
- **No persistent storage** – each run is stateless. For historical tracking, pipe `top_stories.json` to a database.

## Running Tests

```bash
python -m pytest tests/ -v
```
