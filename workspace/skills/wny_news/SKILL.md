---
name: wny_news
description: Get WNY local news and sports digests using exec tool with shell commands
tools: [exec]
---

# WNY News Digest

All news data is fetched LIVE from local WNY sources (WGRZ, WIVB, WKBW, UB, etc.) and processed locally. To answer news questions, call the `exec` tool with the `command` parameter set to one of the commands below.

Example tool call:
```json
{ "command": "/Users/jpahl/.openclaw/wny_news/query.py digest" }
```

## Commands

| User asks | exec command |
|-----------|-------------|
| WNY news digest / top stories | `/Users/jpahl/.openclaw/wny_news/query.py digest` |
| Quick headlines | `/Users/jpahl/.openclaw/wny_news/query.py headlines` |
| Sports news only | `/Users/jpahl/.openclaw/wny_news/query.py sports` |
| Civic / government news | `/Users/jpahl/.openclaw/wny_news/query.py civic` |
| Last 12 hours, top 5 | `/Users/jpahl/.openclaw/wny_news/query.py digest --hours 12 --top 5` |
| Full JSON output | `/Users/jpahl/.openclaw/wny_news/query.py json` |
| Last run status | `/Users/jpahl/.openclaw/wny_news/query.py status` |
| List configured sources | `/Users/jpahl/.openclaw/wny_news/main.py sources` |

Do NOT use web search for WNY news. Always use the `exec` tool with the full script path (no `python` prefix -- scripts have shebangs).
