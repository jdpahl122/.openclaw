# Gmail Email Monitor

An OpenClaw skill that monitors Gmail for unread emails, classifies them by priority, and lets you triage, draft, review, and send replies -- all from Telegram.

## What it does

- **Scans** your Gmail inbox for unread messages every 30 minutes (via OpenClaw cron)
- **Classifies** each email into one of five categories: `needs_response`, `informational`, `newsletter`, `sales`, `automated`
- **Assigns priority** (HIGH / MEDIUM / LOW) based on urgency signals and heuristic scoring
- **Summarizes** the email body so you can understand context without opening it
- **Sends a Telegram digest** only when there are actionable emails (silent when inbox is clean)
- **Drafts replies** with your Gmail signature automatically attached
- **Sends drafts** on command and marks the original thread as read

## Architecture

```
main.py          CLI entrypoint for cron (prints digest to stdout)
query.py         OpenClaw skill interface (agent calls via exec tool)
scanner.py       Fetches unread emails via gog CLI
classifier.py    Heuristic scoring + priority assignment + body summarization
formatter.py     Produces Telegram-friendly digest with priority badges
drafter.py       Creates/reads/sends Gmail drafts, fetches Gmail signature
state.py         JSON-based tracking of processed messages and pending drafts
config.py        All configuration (scoring weights, keywords, thresholds)
```

## Setup

### Prerequisites

- Python 3.11+
- [gog](https://github.com/rubiojr/gog) CLI installed and authenticated for Gmail
- OpenClaw gateway running

### 1. Install dependencies

```bash
cd ~/.openclaw/email_monitor
pip install -r requirements.txt
```

### 2. Authenticate gog for Gmail

```bash
gog auth login --scopes gmail --account you@gmail.com
```

Verify it works:

```bash
gog gmail messages search "is:unread" --max 5 --account you@gmail.com --json
```

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

```
GOG_ACCOUNT=you@gmail.com
GOG_BIN=/path/to/gog        # or just "gog" if it's on PATH
INITIAL_LOOKBACK_HOURS=24
EMAIL_MONITOR_LOG_LEVEL=INFO
```

### 4. Verify scripts are executable

```bash
chmod +x main.py query.py
```

Both have shebangs pointing to Python 3.11. If your Python is elsewhere, update line 1 of each file.

### 5. Test it

```bash
./query.py status   # should show config
./query.py check    # should scan and print digest
```

### 6. OpenClaw integration

The skill is registered at `~/.openclaw/skills/email_monitor/SKILL.md` and `~/.openclaw/workspace/skills/email_monitor/SKILL.md`. The cron job is configured in `~/.openclaw/cron/jobs.json` as `email-monitor`, running every 30 minutes.

To manually trigger from the CLI:

```bash
openclaw cron run email-monitor
```

## Usage (via Telegram)

Once set up, the cron job delivers digests to Telegram automatically. You can also interact directly:

| Ask the agent | What happens |
|---------------|-------------|
| "Check my email" | Scans inbox, classifies, returns digest |
| "Show me the email from John" | Fetches full email by message ID |
| "Draft a reply to John -- tell him yes" | Creates a Gmail draft with your signature |
| "Show me the draft" | Displays the draft body for review |
| "Send it" | Sends the draft and marks the thread as read |
| "Dismiss that email" | Marks it so it won't appear in future digests |

## Classification

Emails are scored using heuristic signals:

**Negative signals** (bulk / skip):
- Known bulk sender domains (Mailchimp, SendGrid, HubSpot, etc.)
- `noreply` / `no-reply` sender patterns
- `List-Unsubscribe` header present
- Sales keywords (discount, promo, webinar, etc.)
- Newsletter keywords (digest, roundup, recap, etc.)

**Positive signals** (needs response):
- Question marks, action words (please, could you, let me know)
- Business keywords (invoice, proposal, quote, meeting)
- Reply/forward threading (`Re:`, `In-Reply-To` header)
- Short body (personal emails tend to be brief)
- Directly addressed to the user (not BCC / mailing list)

**Priority assignment:**
- HIGH: score >= 0.40 or contains urgency words (urgent, asap, critical)
- MEDIUM: score >= 0.10
- LOW: everything else

Thresholds and keyword lists are configurable in `config.py`.

## Digest format

```
📬 Inbox Summary (3 new since last check)

⚡ NEEDS RESPONSE (2):

1. 🔴 [HIGH] John Smith <john@example.com>
   Subject: Urgent: Contract renewal deadline
   Received: 1h ago
   Summary: The renewal deadline is this Friday and we need your signature...
   https://mail.google.com/mail/u/0/#inbox/abc123

2. 🟡 [MEDIUM] Jane Doe <jane@example.com>
   Subject: Re: Project timeline
   Received: 3h ago
   Summary: Can you send over the updated timeline by end of week?
   https://mail.google.com/mail/u/0/#inbox/def456

🗑 SKIPPED (1 sales):
  - Marketing Co <promo@marketing.co> — "50% off this weekend only"

Reply with context to draft a response, e.g.:
"Draft a reply to John Smith -- tell him we'll have the timeline by Friday"
```

## File structure

```
email_monitor/
├── .env                 # Local config (gitignored)
├── .env.example         # Template
├── requirements.txt     # Python dependencies
├── main.py              # Cron entrypoint
├── query.py             # OpenClaw skill interface
├── config.py            # Configuration
├── scanner.py           # Gmail fetch via gog
├── classifier.py        # Heuristic classifier
├── formatter.py         # Telegram digest formatter
├── drafter.py           # Draft create/read/send
├── state.py             # Processed message tracking
└── data/
    └── state.json       # Runtime state (gitignored)
```
