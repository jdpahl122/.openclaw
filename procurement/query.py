#!/Users/jpahl/.pyenv/versions/3.11.11/bin/python3
"""Simple query interface for the procurement RFQ database.

Usage:
    python query.py top [N]           -- Top N RFQs to focus on (default 10)
    python query.py mwbe              -- MWBE/SDVOB opportunities
    python query.py due [DAYS]        -- RFQs due within N days (default 7)
    python query.py detail CRNUM      -- Full details for a specific CR#
    python query.py summary           -- Pipeline summary counts
    python query.py all               -- All RFQs sorted by due date
"""

import json
import sqlite3
import sys
from datetime import date

DB = "/Users/jpahl/.openclaw/procurement/data/rfqs.db"


def _connect():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def top(n=10):
    """Top RFQs ranked by priority (MWBE/SDVOB first, then score, then due date)."""
    conn = _connect()
    rows = conn.execute(
        """
        SELECT cr_number, title, agency, due_date, relevance_score,
               is_mwbe_sdvob, procurement_type, sdvob_goal, mbe_goal, wbe_goal,
               status, gdrive_folder_url, detail_url
        FROM rfqs
        WHERE relevance_score >= 0.80
          AND (due_date IS NULL OR due_date >= date('now'))
        ORDER BY is_mwbe_sdvob DESC, relevance_score DESC, due_date ASC
        LIMIT ?
        """,
        (n,),
    ).fetchall()

    if not rows:
        print("No qualifying RFQs found.")
        return

    print(f"Top {len(rows)} RFQs to focus on:\n")
    for i, r in enumerate(rows, 1):
        d = dict(r)
        tag = " [MWBE/SDVOB]" if d["is_mwbe_sdvob"] else ""
        due = d["due_date"] or "TBD"
        drive = f"\n   Drive: {d['gdrive_folder_url']}" if d["gdrive_folder_url"] else ""
        print(
            f"{i:2d}. CR# {d['cr_number']} | Score: {d['relevance_score']:.2f}{tag}\n"
            f"    {d['title']}\n"
            f"    Agency: {d['agency']} | Due: {due} | Status: {d['status']}"
            f"{drive}\n"
        )


def mwbe():
    """MWBE/SDVOB discretionary and set-aside opportunities."""
    conn = _connect()
    rows = conn.execute(
        """
        SELECT cr_number, title, agency, due_date, relevance_score,
               procurement_type, sdvob_goal, mbe_goal, wbe_goal,
               status, gdrive_folder_url
        FROM rfqs
        WHERE is_mwbe_sdvob = 1
          AND (due_date IS NULL OR due_date >= date('now'))
        ORDER BY due_date ASC
        """
    ).fetchall()

    if not rows:
        print("No open MWBE/SDVOB opportunities found.")
        return

    print(f"MWBE/SDVOB Opportunities ({len(rows)}):\n")
    for r in rows:
        d = dict(r)
        goals = []
        if d["sdvob_goal"]:
            goals.append(f"SDVOB={d['sdvob_goal']}%")
        if d["mbe_goal"]:
            goals.append(f"MBE={d['mbe_goal']}%")
        if d["wbe_goal"]:
            goals.append(f"WBE={d['wbe_goal']}%")
        goals_str = " | ".join(goals) if goals else "goals not specified"
        due = d["due_date"] or "TBD"
        drive = f"\n   Drive: {d['gdrive_folder_url']}" if d["gdrive_folder_url"] else ""
        print(
            f"CR# {d['cr_number']} | {d['procurement_type']}\n"
            f"  {d['title']}\n"
            f"  Agency: {d['agency']} | Due: {due} | {goals_str}"
            f"{drive}\n"
        )


def due(days=7):
    """RFQs due within N days."""
    conn = _connect()
    rows = conn.execute(
        """
        SELECT cr_number, title, agency, due_date, relevance_score,
               is_mwbe_sdvob, status, gdrive_folder_url
        FROM rfqs
        WHERE due_date >= date('now')
          AND due_date <= date('now', '+' || ? || ' days')
        ORDER BY due_date ASC
        """,
        (days,),
    ).fetchall()

    if not rows:
        print(f"No RFQs due in the next {days} days.")
        return

    print(f"RFQs due in the next {days} days ({len(rows)}):\n")
    for r in rows:
        d = dict(r)
        tag = " [MWBE/SDVOB]" if d["is_mwbe_sdvob"] else ""
        days_left = (date.fromisoformat(d["due_date"]) - date.today()).days
        print(
            f"CR# {d['cr_number']} | Due: {d['due_date']} ({days_left}d left){tag}\n"
            f"  {d['title']}\n"
            f"  Agency: {d['agency']} | Score: {d['relevance_score']:.2f} | Status: {d['status']}\n"
        )


def detail(cr_number):
    """Full details for a specific RFQ."""
    conn = _connect()
    row = conn.execute("SELECT * FROM rfqs WHERE cr_number = ?", (cr_number,)).fetchone()

    if not row:
        print(f"RFQ CR# {cr_number} not found.")
        return

    d = dict(row)
    items = json.loads(d.get("line_items_json", "[]"))

    tag = " [MWBE/SDVOB]" if d["is_mwbe_sdvob"] else ""
    print(f"CR# {d['cr_number']}: {d['title']}{tag}")
    print(f"{'=' * 70}")
    print(f"Agency:      {d['agency']}")
    print(f"Division:    {d['division']}")
    print(f"Category:    {d['category']}")
    print(f"Ad Type:     {d['ad_type']}")
    print(f"Proc. Type:  {d['procurement_type']}")
    print(f"Issue Date:  {d['issue_date']}")
    print(f"Due Date:    {d['due_date']}")
    print(f"Score:       {d['relevance_score']:.2f}")
    print(f"Status:      {d['status']}")

    if d["is_mwbe_sdvob"]:
        print(f"SDVOB Goal:  {d['sdvob_goal'] or 0}%")
        print(f"MBE Goal:    {d['mbe_goal'] or 0}%")
        print(f"WBE Goal:    {d['wbe_goal'] or 0}%")

    if d["gdrive_folder_url"]:
        print(f"Drive:       {d['gdrive_folder_url']}")
    if d["detail_url"]:
        print(f"NYSCR:       {d['detail_url']}")

    if items:
        print(f"\nLine Items ({len(items)}):")
        for i, item in enumerate(items[:25], 1):
            desc = item.get("description", "")[:60]
            qty = item.get("quantity", "")
            vendor = item.get("vendor", "")
            parts = [f"  {i}. {desc}"]
            if qty:
                parts.append(f"Qty: {qty}")
            if vendor:
                parts.append(f"Vendor: {vendor}")
            print(" | ".join(parts))
        if len(items) > 25:
            print(f"  ... and {len(items) - 25} more items")

    if d.get("note"):
        print(f"\nNote: {d['note']}")


def summary():
    """Pipeline summary with counts by status."""
    conn = _connect()

    total = conn.execute("SELECT COUNT(*) FROM rfqs").fetchone()[0]
    by_status = conn.execute(
        "SELECT status, COUNT(*) as cnt FROM rfqs GROUP BY status ORDER BY cnt DESC"
    ).fetchall()
    mwbe_count = conn.execute(
        "SELECT COUNT(*) FROM rfqs WHERE is_mwbe_sdvob = 1"
    ).fetchone()[0]
    upcoming = conn.execute(
        "SELECT COUNT(*) FROM rfqs WHERE due_date >= date('now') AND due_date <= date('now', '+14 days')"
    ).fetchone()[0]
    high_score = conn.execute(
        "SELECT COUNT(*) FROM rfqs WHERE relevance_score >= 0.90"
    ).fetchone()[0]

    print(f"Procurement Pipeline Summary")
    print(f"{'=' * 40}")
    print(f"Total RFQs tracked:     {total}")
    print(f"MWBE/SDVOB:             {mwbe_count}")
    print(f"High relevance (>=0.9): {high_score}")
    print(f"Due in next 14 days:    {upcoming}")
    print()
    print("By status:")
    for r in by_status:
        print(f"  {r['status']:12s} {r['cnt']}")


def show_all():
    """All RFQs sorted by due date."""
    conn = _connect()
    rows = conn.execute(
        """
        SELECT cr_number, title, due_date, relevance_score,
               is_mwbe_sdvob, status
        FROM rfqs
        WHERE due_date >= date('now')
        ORDER BY due_date ASC
        """
    ).fetchall()

    for r in rows:
        d = dict(r)
        tag = " *" if d["is_mwbe_sdvob"] else ""
        print(
            f"CR# {d['cr_number']} | {d['due_date']} | "
            f"{d['relevance_score']:.2f}{tag} | {d['status']:10s} | {d['title'][:50]}"
        )


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(0)

    cmd = args[0].lower()
    if cmd == "top":
        top(int(args[1]) if len(args) > 1 else 10)
    elif cmd == "mwbe":
        mwbe()
    elif cmd == "due":
        due(int(args[1]) if len(args) > 1 else 7)
    elif cmd == "detail":
        if len(args) < 2:
            print("Usage: query.py detail CRNUM")
            sys.exit(1)
        detail(args[1])
    elif cmd == "summary":
        summary()
    elif cmd == "all":
        show_all()
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)
