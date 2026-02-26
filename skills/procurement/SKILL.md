---
name: procurement
description: Query LOCAL procurement RFQ database using exec tool with shell commands
tools: [exec]
---

# Procurement RFQ Queries

All RFQ data is in a LOCAL database. To answer procurement questions, call the `exec` tool with the `command` parameter set to one of the Python commands below.

Example tool call:
```json
{ "command": "/Users/jpahl/.openclaw/procurement/query.py top 10" }
```

## Commands

| User asks | exec command |
|-----------|-------------|
| Top RFQs / what to focus on | `/Users/jpahl/.openclaw/procurement/query.py top 10` |
| MWBE/SDVOB opportunities | `/Users/jpahl/.openclaw/procurement/query.py mwbe` |
| What's due soon | `/Users/jpahl/.openclaw/procurement/query.py due 7` |
| Tell me about CR# 2131706 | `/Users/jpahl/.openclaw/procurement/query.py detail 2131706` |
| Pipeline summary | `/Users/jpahl/.openclaw/procurement/query.py summary` |
| All open RFQs | `/Users/jpahl/.openclaw/procurement/query.py all` |
| Scan for new RFQs | `/Users/jpahl/.openclaw/procurement/main.py scan` |
| Deep dive CR# 2131706 | `/Users/jpahl/.openclaw/procurement/main.py deep-dive --cr 2131706` |
| Reset CR# 2131706 | `/Users/jpahl/.openclaw/procurement/main.py reset --cr 2131706 --to new` |

Do NOT use web search. Do NOT run `skills` as a command. Always use the `exec` tool with the full script path (no `python` prefix -- scripts have shebangs).
