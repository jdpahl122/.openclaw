---
name: email_monitor
description: Monitor Gmail inbox, classify emails, draft/review/send replies using exec tool with shell commands
tools: [exec]
---

# Gmail Email Monitor

Monitors Gmail for unread emails, classifies them by priority (HIGH/MEDIUM/LOW) with body summaries, and can draft, review, and send reply emails. Uses the `gog` CLI for all Gmail operations. To answer email questions, call the `exec` tool with the `command` parameter set to one of the commands below.

Example tool call:
```json
{ "command": "/Users/jpahl/.openclaw/email_monitor/query.py check" }
```

## Commands

| User asks | exec command |
|-----------|-------------|
| Check inbox / new emails | `/Users/jpahl/.openclaw/email_monitor/query.py check` |
| Show last digest | `/Users/jpahl/.openclaw/email_monitor/query.py last` |
| Read a specific email | `/Users/jpahl/.openclaw/email_monitor/query.py show --msg-id MSG_ID` |
| Draft a reply | `/Users/jpahl/.openclaw/email_monitor/query.py draft --to "email@example.com" --context "reply text" --subject "Re: Subject" --msg-id MSG_ID --thread-id THREAD_ID` |
| Review a draft | `/Users/jpahl/.openclaw/email_monitor/query.py show-draft --draft-id DRAFT_ID` |
| Send a draft | `/Users/jpahl/.openclaw/email_monitor/query.py send --draft-id DRAFT_ID` |
| Dismiss an email | `/Users/jpahl/.openclaw/email_monitor/query.py dismiss --msg-id MSG_ID` |
| Monitor status | `/Users/jpahl/.openclaw/email_monitor/query.py status` |

## Draft workflow

1. User asks to draft a reply → use `draft` command (include `--msg-id` and `--thread-id` so send can mark as read)
2. User asks to review → use `show-draft` command with the draft ID from step 1
3. User says to send → use `send` command (automatically marks original thread as read)

Drafts include the default email signature automatically.

Do NOT use web search for email operations. Always use the `exec` tool with the full script path (no `python` prefix -- scripts have shebangs).
