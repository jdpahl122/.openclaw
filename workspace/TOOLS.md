# TOOLS.md - Local Notes

Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your setup.

## What Goes Here

Things like:

- Camera names and locations
- SSH hosts and aliases
- Preferred voices for TTS
- Speaker/room names
- Device nicknames
- Anything environment-specific

## Examples

```markdown
### Cameras

- living-room → Main area, 180° wide angle
- front-door → Entrance, motion-triggered

### SSH

- home-server → 192.168.1.100, user: admin

### TTS

- Preferred voice: "Nova" (warm, slightly British)
- Default speaker: Kitchen HomePod
```

## Why Separate?

Skills are shared. Your setup is yours. Keeping them apart means you can update skills without losing your notes, and share skills without leaking your infrastructure.

---

## Procurement RFQ Tool

All procurement RFQ data is stored in a LOCAL SQLite database. To answer ANY procurement question, use the `exec` tool to run a Python command. Never use web search.

**Query commands** (use `exec` with `command` parameter):

| User asks | command |
|-----------|---------|
| Top RFQs / what to focus on | `/Users/jpahl/.openclaw/procurement/query.py top 10` |
| MWBE/SDVOB opportunities | `/Users/jpahl/.openclaw/procurement/query.py mwbe` |
| What's due soon | `/Users/jpahl/.openclaw/procurement/query.py due 7` |
| Details for a specific CR# | `/Users/jpahl/.openclaw/procurement/query.py detail CRNUM` |
| Pipeline summary | `/Users/jpahl/.openclaw/procurement/query.py summary` |
| All open RFQs | `/Users/jpahl/.openclaw/procurement/query.py all` |

**Action commands:**

| Action | command |
|--------|---------|
| Scan for new RFQs | `/Users/jpahl/.openclaw/procurement/main.py scan` |
| Deep dive specific RFQ | `/Users/jpahl/.openclaw/procurement/main.py deep-dive --cr CRNUM` |
| Reset RFQ pipeline stage | `/Users/jpahl/.openclaw/procurement/main.py reset --cr CRNUM --to new` |

Example exec tool call: `{ "command": "/Users/jpahl/.openclaw/procurement/query.py top 10" }`

---

## WNY Local News Digest

Fetches and summarises top Western New York news and sports stories from local sources (WGRZ, WIVB, WKBW, UB, WGR550, Spectrum, City of Buffalo). All data is fetched LIVE and processed locally.

**Query commands** (use `exec` with `command` parameter):

| User asks | command |
|-----------|---------|
| WNY news digest / top stories | `/Users/jpahl/.openclaw/wny_news/query.py digest` |
| Quick headlines | `/Users/jpahl/.openclaw/wny_news/query.py headlines` |
| Sports news only | `/Users/jpahl/.openclaw/wny_news/query.py sports` |
| Civic / government news | `/Users/jpahl/.openclaw/wny_news/query.py civic` |
| Last 12h, top 5 | `/Users/jpahl/.openclaw/wny_news/query.py digest --hours 12 --top 5` |
| Full JSON output | `/Users/jpahl/.openclaw/wny_news/query.py json` |
| Last run status | `/Users/jpahl/.openclaw/wny_news/query.py status` |

Example exec tool call: `{ "command": "/Users/jpahl/.openclaw/wny_news/query.py digest" }`

---

Add whatever helps you do your job. This is your cheat sheet.
