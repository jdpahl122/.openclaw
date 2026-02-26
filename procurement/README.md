# Procurement Assistant -- A Aye Aye LLC

Automated procurement pipeline for identifying, analyzing, and bidding on government RFQs for software licenses and IT services.

## What It Does

1. **Scans** NYS Contract Reporter for new IT/software RFQs
2. **Parses** PDF attachments and Excel pricing sheets to extract line items
3. **Creates** CRM opportunities in Odoo Cloud with all RFQ details
4. **Creates** Google Drive folders per RFQ with source documents and proposals
5. **Generates** Gmail draft quote request emails to distributors (matched via line cards)
6. **Analyzes** historical winning bids from Odoo to suggest competitive pricing
7. **Produces** Google Docs proposal drafts ready for review

## Quick Start

```bash
cd /Users/jpahl/.openclaw/procurement

# Install dependencies
pip install -r requirements.txt

# Copy and fill in your credentials
cp .env.template .env
# Edit .env with your actual credentials (see Setup sections below)

# Run the full pipeline
python main.py run-all

# Or run individual steps
python main.py scan       # Scrape + filter
python main.py process    # Odoo leads + Drive folders
python main.py quote      # Gmail draft quote requests
python main.py analyze    # Bid pricing analysis
python main.py propose    # Generate proposals
python main.py status     # View pipeline status
```

## Setup

### 1. NYS Contract Reporter

1. Create an account at https://www.nyscr.ny.gov if you don't have one
2. Add to `.env`:
   ```
   NYSCR_USERNAME=your-email@example.com
   NYSCR_PASSWORD=your-password
   ```

### 2. Odoo Cloud CRM (API Key)

1. Log in to your Odoo Cloud instance
2. Go to **Settings** > **Users & Companies** > **Users**
3. Select your user
4. Go to the **Preferences** tab
5. Under **Account Security**, click **New API Key**
6. Name it (e.g., "procurement-assistant") and copy the key
7. Add to `.env`:
   ```
   ODOO_URL=https://your-instance.odoo.com
   ODOO_DB=your-database-name
   ODOO_USER=your-email@example.com
   ODOO_API_KEY=the-api-key-you-just-created
   ```

**Finding your database name:** Go to `https://your-instance.odoo.com/web/database/manager` or check the URL when logged in.

### 3. Google Drive (Service Account)

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project (or select an existing one)
3. Enable the **Google Drive API** and **Google Docs API**
4. Go to **IAM & Admin** > **Service Accounts**
5. Create a service account
6. Click the service account > **Keys** tab > **Add Key** > **Create new key** > **JSON**
7. Save the downloaded JSON file to:
   ```
   credentials/gdrive-service-account.json
   ```
8. In Google Drive, create a root folder for all RFQ folders
9. **Share that folder** with the service account email (found in the JSON file, looks like `name@project.iam.gserviceaccount.com`)
10. Copy the folder ID from the URL (the part after `/folders/`) and add to `.env`:
    ```
    GDRIVE_PARENT_FOLDER_ID=1ABC123...
    GDRIVE_SHARE_EMAIL=your-personal@gmail.com
    ```

### 4. Gmail OAuth2 (for Quote Request Drafts)

1. In the same Google Cloud project, enable the **Gmail API**
2. Go to **APIs & Services** > **Credentials**
3. Click **Create Credentials** > **OAuth client ID**
4. Application type: **Desktop app**
5. Copy the Client ID and Secret to `.env`:
   ```
   GMAIL_CLIENT_ID=your-client-id.apps.googleusercontent.com
   GMAIL_CLIENT_SECRET=your-client-secret
   ```
6. On first run of `python main.py quote`, a browser window will open for OAuth consent
7. The refresh token is saved to `credentials/gmail-token.json` for subsequent runs

**Note:** You may need to add your email as a test user in **OAuth consent screen** if the app is in testing mode.

### 5. Distributor Line Cards

Populate `data/line_cards.csv` with your distributor contacts:

```csv
distributor_name,rep_name,rep_email,vendor,product_line,notes
SHI International,Jane Smith,jane.smith@shi.com,Microsoft,M365/Azure,Preferred for enterprise
CDW,Bob Jones,bjones@cdw.com,Adobe,Creative Cloud/Acrobat,
Insight Direct,Maria Garcia,mgarcia@insight.com,VMware,vSphere/NSX,Also does Broadcom
```

Each row maps a distributor rep to the vendor/product line they cover. When the system extracts line items from an RFQ, it fuzzy-matches them against this file to determine which distributor(s) to contact.

### 6. Playwright (for JS-rendered sites)

If NYSCR requires JavaScript rendering (fallback mode):

```bash
pip install playwright
playwright install chromium
```

## Automated Scanning (Cron)

A cron job is configured in OpenClaw to run the scanner daily at 8 AM. When new relevant RFQs are found, a summary is sent to your Telegram. See `cron/jobs.json`.

To adjust the schedule, edit the `schedule` field (standard cron syntax).

## CLI Reference

| Command | Description |
|---------|-------------|
| `scan` | Scrape NYSCR, download/parse attachments, filter for relevance |
| `process` | Create Odoo CRM leads and Google Drive folders for new RFQs |
| `quote` | Match line items to distributors, create Gmail draft quote requests |
| `analyze` | Run bid analysis using historical Odoo win data |
| `propose` | Generate Google Docs proposal drafts |
| `run-all` | Execute the full pipeline end-to-end |
| `status` | Show all tracked RFQs grouped by pipeline stage |

**Options:**
- `-v` / `--verbose` -- Enable debug logging
- `--cr CR_NUMBER` -- Target a specific RFQ (for `quote`, `analyze`, `propose`)
- `--source SOURCE` -- Scraper to use (default: `nyscr`)

## Adding New Procurement Sites

1. Create a new file in `scrapers/` (e.g., `sam_gov.py`)
2. Implement the `BaseScraper` interface (see `scrapers/base.py`)
3. Register it in `main.py`'s `scan` command
4. Run with `python main.py scan --source sam_gov`

## Project Structure

```
procurement/
├── main.py                 # CLI entry point
├── notify.py               # Cron/notification script
├── config.py               # Central configuration
├── requirements.txt
├── .env.template
├── scrapers/
│   ├── base.py             # Abstract scraper interface
│   └── nyscr.py            # NYS Contract Reporter
├── parser/
│   ├── rfq_parser.py       # Keyword filter + dedup + urgency
│   ├── doc_parser.py       # PDF extraction (pdfplumber)
│   └── excel_parser.py     # Excel/CSV line-item parsing
├── integrations/
│   ├── odoo_client.py      # Odoo CRM via XML-RPC
│   ├── gdrive_client.py    # Google Drive folders + uploads
│   ├── gdocs_client.py     # Google Docs proposal creation
│   └── gmail_client.py     # Gmail draft quote requests
├── analysis/
│   ├── bid_analyzer.py     # Historical bid analysis
│   └── line_card_matcher.py # Distributor matching
├── templates/
│   ├── proposal_template.md
│   └── quote_request.txt
├── data/
│   ├── line_cards.csv      # Your distributor contacts
│   ├── rfqs.db             # SQLite tracking database
│   └── raw/                # Downloaded attachments + HTML snapshots
├── models/
│   ├── rfq.py              # RFQ dataclass
│   └── line_item.py        # LineItem dataclass
└── credentials/
    ├── gdrive-service-account.json  # (you provide)
    └── gmail-token.json             # (auto-generated on first OAuth)
```
