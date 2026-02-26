#!/Users/jpahl/.pyenv/versions/3.11.11/bin/python3
"""Procurement assistant CLI -- orchestrates the full RFQ pipeline.

Usage:
    python main.py scan        # Scrape NYSCR, parse attachments, filter
    python main.py process     # Create Odoo leads + Drive folders
    python main.py quote       # Match line items to distributors, create Gmail drafts
    python main.py analyze     # Run bid analysis on processed RFQs
    python main.py propose     # Generate proposal documents
    python main.py run-all     # Full pipeline end-to-end
    python main.py status      # Show current RFQ pipeline status
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import click

# Ensure the project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
from data.db import RFQDatabase

logger = logging.getLogger("procurement")


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(name)-20s | %(levelname)-7s | %(message)s",
        datefmt="%H:%M:%S",
    )


def _get_db() -> RFQDatabase:
    return RFQDatabase(config.RFQS_DB)


# ============================================================================
# CLI
# ============================================================================

@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging")
def cli(verbose: bool) -> None:
    """Procurement assistant for A Aye Aye LLC."""
    _setup_logging(verbose)


# -------------------------------------------------------------------------- scan

@cli.command()
@click.option("--source", default="nyscr", help="Scraper source to use")
def scan(source: str) -> None:
    """Scrape procurement sites, parse attachments, filter for relevance."""
    from scrapers.nyscr import NYSCRScraper
    from parser.rfq_parser import filter_and_enrich

    db = _get_db()

    if source == "nyscr":
        scraper = NYSCRScraper()
    else:
        click.echo(f"Unknown source: {source}", err=True)
        raise SystemExit(1)

    click.echo(f"Scanning {source}...")
    raw_rfqs = scraper.scrape()
    click.echo(f"Found {len(raw_rfqs)} total listings")

    new_rfqs = filter_and_enrich(raw_rfqs, db)
    click.echo(f"New relevant RFQs: {len(new_rfqs)}")

    for rfq in new_rfqs:
        urgency = "URGENT " if rfq.is_urgent else ""
        items = f" ({len(rfq.line_items)} line items)" if rfq.line_items else ""
        click.echo(
            f"  {urgency}CR# {rfq.cr_number} | {rfq.title[:60]} | "
            f"Due: {rfq.due_date or 'TBD'} | Score: {rfq.relevance_score:.2f}{items}"
        )

    db.close()


# ----------------------------------------------------------------------- process

@cli.command()
@click.option("--cr", default=None, help="Process a specific CR# only")
def process(cr: str | None) -> None:
    """Create Odoo CRM leads and Google Drive folders for new RFQs."""
    from integrations.odoo_client import OdooClient
    from integrations.gdrive_client import create_rfq_folder, upload_rfq_attachments

    db = _get_db()
    odoo = OdooClient()
    odoo_ok = odoo.is_configured
    if not odoo_ok:
        click.echo("Odoo not configured -- skipping CRM lead creation (set credentials in .env later)")

    if cr:
        rfq = db.get(cr)
        if not rfq:
            click.echo(f"RFQ CR# {cr} not found.", err=True)
            raise SystemExit(1)
        new_rfqs = [rfq]
    else:
        new_rfqs = db.get_by_status("new")

    if not new_rfqs:
        click.echo("No new RFQs to process.")
        db.close()
        return

    click.echo(f"Processing {len(new_rfqs)} RFQs...")

    for rfq in new_rfqs:
        click.echo(f"\n--- CR# {rfq.cr_number}: {rfq.title[:50]} ---")

        # Create Odoo lead (skip if not configured)
        if odoo_ok:
            try:
                existing = odoo.find_lead_by_cr(rfq.cr_number)
                if existing:
                    rfq.odoo_lead_id = existing
                    click.echo(f"  Odoo lead already exists: {existing}")
                else:
                    lead_id = odoo.create_lead(rfq)
                    rfq.odoo_lead_id = lead_id
                    click.echo(f"  Created Odoo lead: {lead_id}")
            except Exception as exc:
                click.echo(f"  Odoo error: {exc}", err=True)

        # Create Drive folder
        try:
            folder_id, folder_url = create_rfq_folder(rfq)
            rfq.gdrive_folder_id = folder_id
            rfq.gdrive_folder_url = folder_url
            click.echo(f"  Drive folder: {folder_url}")

            # Upload attachments
            uploaded = upload_rfq_attachments(rfq)
            click.echo(f"  Uploaded {uploaded} attachment(s)")
        except Exception as exc:
            click.echo(f"  Drive error: {exc}", err=True)

        # Update Odoo lead with Drive link
        if odoo_ok and rfq.odoo_lead_id and rfq.gdrive_folder_url:
            try:
                odoo.update_lead(
                    rfq.odoo_lead_id,
                    {"description": f"Google Drive: {rfq.gdrive_folder_url}"},
                )
            except Exception:
                pass

        rfq.status = "processed"
        db.upsert(rfq)

    click.echo(f"\nProcessed {len(new_rfqs)} RFQs.")
    db.close()


# ------------------------------------------------------------------------ quote

@cli.command()
@click.option("--cr", default=None, help="Process a specific CR# only")
def quote(cr: str | None) -> None:
    """Match RFQ line items to distributors and create Gmail draft quote requests."""
    from analysis.line_card_matcher import load_line_cards, match_line_items
    from integrations.gmail_client import create_draft_quote_requests

    db = _get_db()

    if cr:
        rfq = db.get(cr)
        if not rfq:
            click.echo(f"RFQ CR# {cr} not found.", err=True)
            raise SystemExit(1)
        rfqs = [rfq]
    else:
        rfqs = db.get_by_status("processed")

    if not rfqs:
        click.echo("No processed RFQs to create quotes for.")
        db.close()
        return

    contacts = load_line_cards()
    if not contacts:
        click.echo(
            "No distributor contacts loaded. "
            "Populate data/line_cards.csv first.",
            err=True,
        )
        db.close()
        return

    click.echo(f"Creating quote requests for {len(rfqs)} RFQ(s)...")

    for rfq in rfqs:
        click.echo(f"\n--- CR# {rfq.cr_number}: {rfq.title[:50]} ---")

        if not rfq.line_items:
            click.echo("  No line items -- skipping quote generation")
            continue

        quote_requests = match_line_items(rfq.line_items, contacts)
        if not quote_requests:
            click.echo("  No distributor matches found")
            continue

        click.echo(f"  Matched {len(quote_requests)} distributor(s)")

        drafts = create_draft_quote_requests(rfq, quote_requests)
        for d in drafts:
            click.echo(
                f"  Draft created: {d['rep_name']} ({d['distributor']}) "
                f"-- {d['item_count']} item(s)"
            )

        rfq.status = "quoted"
        db.upsert(rfq)

    db.close()


# ---------------------------------------------------------------------- analyze

@cli.command()
@click.option("--cr", default=None, help="Analyze a specific CR# only")
def analyze(cr: str | None) -> None:
    """Run bid analysis on RFQs using historical Odoo data."""
    from analysis.bid_analyzer import analyze_bid
    from integrations.odoo_client import OdooClient

    db = _get_db()
    odoo = OdooClient()
    odoo_ok = odoo.is_configured
    if not odoo_ok:
        click.echo("Odoo not configured -- bid analysis will use line-item costs only (no historical data)")

    if cr:
        rfq = db.get(cr)
        if not rfq:
            click.echo(f"RFQ CR# {cr} not found.", err=True)
            raise SystemExit(1)
        rfqs = [rfq]
    else:
        rfqs = db.get_by_status("quoted") + db.get_by_status("processed")

    if not rfqs:
        click.echo("No RFQs ready for analysis.")
        db.close()
        return

    click.echo(f"Analyzing {len(rfqs)} RFQ(s)...")

    for rfq in rfqs:
        click.echo(f"\n--- CR# {rfq.cr_number}: {rfq.title[:50]} ---")

        bid = analyze_bid(rfq, odoo if odoo_ok else None)
        click.echo(f"  {bid.summary}")

        if bid.comparable_deals:
            click.echo("  Comparable deals:")
            for deal in bid.comparable_deals:
                click.echo(
                    f"    - {deal['name'][:50]} | "
                    f"${deal['revenue']:,.2f} | sim={deal['similarity']}"
                )

        # Update Odoo with suggested revenue (skip if not configured)
        if odoo_ok and rfq.odoo_lead_id and bid.mid > 0:
            try:
                odoo.set_expected_revenue(rfq.odoo_lead_id, bid.mid)
                click.echo(f"  Updated Odoo expected revenue: ${bid.mid:,.2f}")
            except Exception as exc:
                click.echo(f"  Odoo update error: {exc}", err=True)

        rfq.status = "analyzed"
        db.upsert(rfq)

    db.close()


# --------------------------------------------------------------------- propose

@cli.command()
@click.option("--cr", default=None, help="Generate proposal for a specific CR#")
def propose(cr: str | None) -> None:
    """Generate Google Docs proposal drafts for analyzed RFQs."""
    from analysis.bid_analyzer import analyze_bid, BidSuggestion
    from integrations.gdocs_client import create_proposal
    from integrations.odoo_client import OdooClient

    db = _get_db()

    if cr:
        rfq = db.get(cr)
        if not rfq:
            click.echo(f"RFQ CR# {cr} not found.", err=True)
            raise SystemExit(1)
        rfqs = [rfq]
    else:
        rfqs = db.get_by_status("analyzed")

    if not rfqs:
        click.echo("No analyzed RFQs ready for proposals.")
        db.close()
        return

    click.echo(f"Generating proposals for {len(rfqs)} RFQ(s)...")

    odoo = OdooClient()
    odoo_ok = odoo.is_configured
    for rfq in rfqs:
        click.echo(f"\n--- CR# {rfq.cr_number}: {rfq.title[:50]} ---")

        # Re-run bid analysis for the proposal content
        try:
            bid = analyze_bid(rfq, odoo if odoo_ok else None)
        except Exception:
            bid = None

        try:
            doc_id, doc_url = create_proposal(rfq, bid)
            click.echo(f"  Proposal: {doc_url}")
        except Exception as exc:
            click.echo(f"  Proposal error: {exc}", err=True)
            continue

        rfq.status = "proposed"
        db.upsert(rfq)

    db.close()


# --------------------------------------------------------------------- run-all

@cli.command("run-all")
def run_all() -> None:
    """Execute the full pipeline: scan -> process -> quote -> analyze -> propose."""
    ctx = click.get_current_context()

    click.echo("=" * 60)
    click.echo("STEP 1: SCAN")
    click.echo("=" * 60)
    ctx.invoke(scan)

    click.echo("\n" + "=" * 60)
    click.echo("STEP 2: PROCESS")
    click.echo("=" * 60)
    ctx.invoke(process)

    click.echo("\n" + "=" * 60)
    click.echo("STEP 3: QUOTE")
    click.echo("=" * 60)
    ctx.invoke(quote)

    click.echo("\n" + "=" * 60)
    click.echo("STEP 4: ANALYZE")
    click.echo("=" * 60)
    ctx.invoke(analyze)

    click.echo("\n" + "=" * 60)
    click.echo("STEP 5: PROPOSE")
    click.echo("=" * 60)
    ctx.invoke(propose)

    click.echo("\n" + "=" * 60)
    click.echo("PIPELINE COMPLETE")
    click.echo("=" * 60)


# -------------------------------------------------------------------- backfill

@cli.command()
def backfill() -> None:
    """Re-classify procurement type and parse MWBE/SDVOB goals for all existing RFQs.

    Uses the already-stored ad_type field for classification and re-parses
    saved detail HTML files for goal percentages.  No re-scraping needed.
    """
    from bs4 import BeautifulSoup
    from parser.rfq_parser import classify_procurement_type
    from scrapers.nyscr import parse_mwbe_sdvob_goals

    db = _get_db()
    all_rfqs = db.get_all()

    if not all_rfqs:
        click.echo("No RFQs in the database.")
        db.close()
        return

    updated = 0
    for rfq in all_rfqs:
        changed = False

        # Classify from ad_type
        ptype, is_ms = classify_procurement_type(rfq.ad_type)
        if rfq.procurement_type != ptype or rfq.is_mwbe_sdvob != is_ms:
            rfq.procurement_type = ptype
            rfq.is_mwbe_sdvob = is_ms
            changed = True

        # Parse goals from saved detail HTML
        detail_html = config.DATA_DIR / "raw" / f"detail_{rfq.cr_number}.html"
        if detail_html.exists():
            soup = BeautifulSoup(detail_html.read_text(encoding="utf-8"), "html.parser")
            goals = parse_mwbe_sdvob_goals(soup)
            for field in ("sdvob_goal", "mbe_goal", "wbe_goal"):
                if goals[field] is not None and getattr(rfq, field) != goals[field]:
                    setattr(rfq, field, goals[field])
                    changed = True

        if changed:
            db.upsert(rfq)
            updated += 1
            tag = " [MWBE/SDVOB]" if rfq.is_mwbe_sdvob else ""
            goals_str = ""
            if rfq.sdvob_goal is not None or rfq.mbe_goal is not None:
                goals_str = (
                    f" | SDVOB={rfq.sdvob_goal or 0}% "
                    f"MBE={rfq.mbe_goal or 0}% WBE={rfq.wbe_goal or 0}%"
                )
            click.echo(
                f"  CR# {rfq.cr_number} | {rfq.procurement_type}{tag}{goals_str}"
            )

    click.echo(f"\nBackfilled {updated} / {len(all_rfqs)} RFQs.")
    db.close()


# ----------------------------------------------------------------------- reset

@cli.command()
@click.option("--cr", required=True, help="CR# of the RFQ to reset")
@click.option(
    "--to",
    "target_status",
    default="new",
    type=click.Choice(["new", "processed", "quoted", "analyzed"]),
    help="Stage to reset the RFQ back to (default: new)",
)
def reset(cr: str, target_status: str) -> None:
    """Reset an RFQ's status so it can be re-processed through later pipeline stages."""
    db = _get_db()
    rfq = db.get(cr)
    if not rfq:
        click.echo(f"RFQ CR# {cr} not found.", err=True)
        db.close()
        raise SystemExit(1)

    old_status = rfq.status
    db.update_status(cr, target_status)
    click.echo(f"CR# {cr}: {old_status} -> {target_status}")
    db.close()


# ------------------------------------------------------------------- deep-dive

@cli.command("deep-dive")
@click.option("--cr", required=True, multiple=True, help="CR#(s) to deep-dive (can specify multiple)")
@click.option("--rescan", is_flag=True, help="Re-download and re-parse detail page and attachments")
def deep_dive(cr: tuple[str, ...], rescan: bool) -> None:
    """Re-run the full pipeline for specific RFQs.

    Resets the target RFQ(s) back to 'new' and runs process -> quote ->
    analyze -> propose for just those CRs.  Use --rescan to also revisit
    the NYSCR detail page for fresh data.
    """
    db = _get_db()

    rfqs_to_dive: list = []
    for cr_num in cr:
        rfq = db.get(cr_num)
        if not rfq:
            click.echo(f"RFQ CR# {cr_num} not found -- skipping.", err=True)
            continue
        rfqs_to_dive.append(rfq)

    if not rfqs_to_dive:
        click.echo("No valid RFQs to deep-dive.")
        db.close()
        return

    # Optionally re-scrape detail pages
    if rescan:
        from scrapers.nyscr import NYSCRScraper
        from parser.rfq_parser import process_attachments, compute_relevance, classify_procurement_type

        click.echo("Re-scanning detail pages...")
        scraper = NYSCRScraper()
        scraper._start_browser(headless=True)
        try:
            scraper._ensure_authenticated()
            for rfq in rfqs_to_dive:
                click.echo(f"  Re-fetching CR# {rfq.cr_number}...")
                detail = scraper._fetch_detail({"detail_url": rfq.detail_url, "cr_number": rfq.cr_number})
                if detail:
                    attachments = scraper._download_attachments(
                        detail.get("attachment_urls", []), rfq.cr_number
                    )
                    rfq.raw_text = detail.get("raw_text", rfq.raw_text)
                    rfq.attachment_paths = attachments or rfq.attachment_paths
                    rfq.sdvob_goal = detail.get("sdvob_goal")
                    rfq.mbe_goal = detail.get("mbe_goal")
                    rfq.wbe_goal = detail.get("wbe_goal")
                    rfq = process_attachments(rfq)
                    rfq.relevance_score = compute_relevance(rfq)
                    rfq.procurement_type, rfq.is_mwbe_sdvob = classify_procurement_type(rfq.ad_type)
                    if rfq.is_mwbe_sdvob:
                        rfq.relevance_score = min(rfq.relevance_score + 0.10, 1.0)
                    db.upsert(rfq)
        finally:
            scraper._stop_browser()

    # Reset all to 'new' so the pipeline picks them up
    for rfq in rfqs_to_dive:
        db.update_status(rfq.cr_number, "new")

    db.close()

    click.echo(f"\nRunning pipeline for {len(rfqs_to_dive)} RFQ(s)...")

    ctx = click.get_current_context()
    for cr_num in cr:
        click.echo(f"\n{'='*60}")
        click.echo(f"DEEP-DIVE: CR# {cr_num}")
        click.echo("=" * 60)
        ctx.invoke(process, cr=cr_num)
        ctx.invoke(quote, cr=cr_num)
        ctx.invoke(analyze, cr=cr_num)
        ctx.invoke(propose, cr=cr_num)

    click.echo(f"\nDeep-dive complete for {len(rfqs_to_dive)} RFQ(s).")


# ---------------------------------------------------------------------- status

@cli.command()
def status() -> None:
    """Show the current state of the RFQ pipeline."""
    db = _get_db()
    all_rfqs = db.get_all()

    if not all_rfqs:
        click.echo("No RFQs in the database.")
        db.close()
        return

    # Group by status
    by_status: dict[str, list] = {}
    for rfq in all_rfqs:
        by_status.setdefault(rfq.status, []).append(rfq)

    click.echo(f"Total RFQs tracked: {len(all_rfqs)}\n")

    # Summary counts
    mwbe_count = sum(1 for r in all_rfqs if r.is_mwbe_sdvob)
    if mwbe_count:
        click.echo(f"  MWBE/SDVOB opportunities: {mwbe_count}\n")

    status_order = ["new", "processed", "quoted", "analyzed", "proposed"]
    for st in status_order:
        rfqs = by_status.get(st, [])
        if not rfqs:
            continue
        click.echo(f"[{st.upper()}] ({len(rfqs)})")
        for rfq in rfqs:
            urgency = " URGENT" if rfq.is_urgent else ""
            items = f" | {len(rfq.line_items)} items" if rfq.line_items else ""
            mwbe_tag = f" [MWBE/SDVOB]" if rfq.is_mwbe_sdvob else ""
            goals = ""
            if rfq.is_mwbe_sdvob and (rfq.sdvob_goal or rfq.mbe_goal or rfq.wbe_goal):
                parts = []
                if rfq.sdvob_goal:
                    parts.append(f"SDVOB={rfq.sdvob_goal}%")
                if rfq.mbe_goal:
                    parts.append(f"MBE={rfq.mbe_goal}%")
                if rfq.wbe_goal:
                    parts.append(f"WBE={rfq.wbe_goal}%")
                goals = f" | {' '.join(parts)}"
            click.echo(
                f"  CR# {rfq.cr_number} | {rfq.title[:45]} | "
                f"Due: {rfq.due_date or 'TBD'}{urgency}{mwbe_tag}{goals}{items}"
            )
        click.echo()

    db.close()


if __name__ == "__main__":
    cli()
