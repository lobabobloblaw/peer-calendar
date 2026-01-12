#!/usr/bin/env python3
"""
Audit Check Script for Portland Metro Resources

This script analyzes sources.yaml and reports:
- Entries due for audit this month
- Entries with verification flags
- Statistics by category
- Data quality issues

Usage:
    python audit_check.py                    # Full report
    python audit_check.py --weekly-summary   # Quick view for weekly check-ins
    python audit_check.py --overdue          # Show overdue entries
    python audit_check.py --due-this-week    # Show entries due in next 7 days
    python audit_check.py --due-this-month   # Only show entries due now
    python audit_check.py --unverified       # Only show unverified entries
    python audit_check.py --category peer_support  # Filter by category
"""

import argparse
from collections import Counter
from datetime import datetime, date, timedelta
from pathlib import Path

import yaml


def load_sources(sources_path: str) -> list[dict]:
    """Load and parse the sources.yaml file."""
    with open(sources_path, "r", encoding="utf-8") as f:
        content = f.read()

    documents = []
    for doc in yaml.safe_load_all(content):
        if doc and isinstance(doc, list):
            documents.extend(doc)
        elif doc and isinstance(doc, dict):
            documents.append(doc)

    return [d for d in documents if d and isinstance(d, dict) and "id" in d]


def check_data_quality(entry: dict) -> list[str]:
    """Check for data quality issues in an entry."""
    issues = []
    entry_id = entry.get("id", "unknown")

    # Check for missing critical fields
    if not entry.get("name"):
        issues.append(f"{entry_id}: Missing name")

    if not entry.get("category"):
        issues.append(f"{entry_id}: Missing category")

    if not entry.get("last_verified"):
        issues.append(f"{entry_id}: Missing last_verified date")

    # Skip next_audit check for closed entries
    if not entry.get("next_audit") and entry.get("status") != "CLOSED":
        issues.append(f"{entry_id}: Missing next_audit date")

    # Check for empty source_urls
    source_urls = entry.get("source_urls", [])
    if not source_urls or (isinstance(source_urls, list) and len(source_urls) == 0):
        issues.append(f"{entry_id}: No source URLs")

    # Check for unverified flags
    flags = entry.get("flags", [])
    for flag in flags:
        if "UNVERIFIED" in flag:
            issues.append(f"{entry_id}: Flagged as unverified")
            break

    return issues


def format_date(date_val) -> str:
    """Format a date value for display."""
    if isinstance(date_val, datetime):
        return date_val.strftime("%Y-%m-%d")
    elif isinstance(date_val, date):
        return date_val.strftime("%Y-%m-%d")
    elif isinstance(date_val, str):
        return date_val
    return str(date_val) if date_val else "N/A"


def parse_date(date_val) -> date | None:
    """Parse a date value to a date object."""
    if isinstance(date_val, date) and not isinstance(date_val, datetime):
        return date_val
    if isinstance(date_val, datetime):
        return date_val.date()
    if isinstance(date_val, str):
        try:
            return datetime.strptime(date_val, "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def print_entry_details(entry: dict, show_source_urls: bool = True):
    """Print formatted details for an entry."""
    print(f"  [{entry.get('category', 'N/A')}] {entry.get('name', 'Unknown')}")
    print(f"    ID: {entry.get('id')}")
    freq = entry.get('audit_frequency', 'unknown')
    print(f"    Frequency: {freq}")
    print(f"    Due: {format_date(entry.get('next_audit'))}")
    print(f"    Last verified: {format_date(entry.get('last_verified'))}")
    if entry.get("website"):
        print(f"    Website: {entry.get('website')}")
    if show_source_urls:
        source_urls = entry.get("source_urls", [])
        if source_urls:
            print(f"    Source URLs:")
            for url in source_urls[:3]:  # Limit to first 3
                print(f"      - {url}")
            if len(source_urls) > 3:
                print(f"      ... and {len(source_urls) - 3} more")
    print()


def main():
    parser = argparse.ArgumentParser(description="Audit check for sources.yaml")
    parser.add_argument("--sources", default="../data/sources.yaml", help="Path to sources.yaml")
    parser.add_argument("--weekly-summary", action="store_true", help="Quick summary for weekly check-ins")
    parser.add_argument("--overdue", action="store_true", help="Show overdue entries (past next_audit date)")
    parser.add_argument("--due-this-week", action="store_true", help="Show entries due in next 7 days")
    parser.add_argument("--due-this-month", action="store_true", help="Show only entries due this month")
    parser.add_argument("--due-next-month", action="store_true", help="Show entries due next month")
    parser.add_argument("--unverified", action="store_true", help="Show only unverified entries")
    parser.add_argument("--category", help="Filter by category")
    parser.add_argument("--quality", action="store_true", help="Run data quality check")

    args = parser.parse_args()

    script_dir = Path(__file__).parent
    sources_path = (script_dir / args.sources).resolve()

    if not sources_path.exists():
        print(f"Error: sources.yaml not found at {sources_path}")
        return

    entries = load_sources(sources_path)
    print(f"Loaded {len(entries)} entries from sources.yaml\n")

    today_dt = datetime.now()
    today_date = today_dt.date()
    current_month = today_dt.strftime("%Y-%m")
    next_month = (today_dt.replace(day=28) + timedelta(days=4)).strftime("%Y-%m")
    week_from_now = today_date + timedelta(days=7)

    # Filter by category if specified
    if args.category:
        entries = [e for e in entries if e.get("category") == args.category]
        print(f"Filtered to {len(entries)} entries in category '{args.category}'\n")

    # Check if a focused view is requested
    focused_view = (args.weekly_summary or args.overdue or args.due_this_week or
                   args.due_this_month or args.unverified or args.quality)

    # Category statistics (only in full report mode)
    if not focused_view:
        print("=" * 60)
        print("CATEGORY STATISTICS")
        print("=" * 60)
        categories = Counter(e.get("category", "unknown") for e in entries)
        for cat, count in sorted(categories.items()):
            print(f"  {cat}: {count}")
        print()

    # Categorize entries by audit status
    overdue = []
    due_this_week = []
    due_this_month = []
    due_next_month = []
    unverified = []

    for entry in entries:
        # Skip closed entries for audit tracking
        if entry.get("status") == "CLOSED":
            continue

        next_audit = entry.get("next_audit")
        if next_audit:
            audit_date = parse_date(next_audit)
            audit_str = format_date(next_audit)

            if audit_date:
                # Check if overdue
                if audit_date < today_date:
                    days_overdue = (today_date - audit_date).days
                    entry["_days_overdue"] = days_overdue
                    overdue.append(entry)
                # Check if due this week
                elif audit_date <= week_from_now:
                    due_this_week.append(entry)
                # Check if due this month
                elif audit_str.startswith(current_month):
                    due_this_month.append(entry)
                # Check if due next month
                elif audit_str.startswith(next_month):
                    due_next_month.append(entry)

        flags = entry.get("flags", [])
        for flag in flags:
            if "UNVERIFIED" in flag or "VERIFY" in flag:
                unverified.append(entry)
                break

    # === WEEKLY SUMMARY VIEW ===
    if args.weekly_summary:
        print("=" * 60)
        print(f"WEEKLY AUDIT SUMMARY - {today_date.strftime('%B %d, %Y')}")
        print("=" * 60)

        # Overdue section (highest priority)
        if overdue:
            print(f"\n⚠️  OVERDUE ({len(overdue)} entries) - Address first!")
            print("-" * 40)
            for entry in sorted(overdue, key=lambda x: -x.get("_days_overdue", 0)):
                days = entry.get("_days_overdue", 0)
                print(f"  [{days} days overdue] {entry.get('name', 'Unknown')}")
                print(f"    ID: {entry.get('id')}")
                print(f"    Frequency: {entry.get('audit_frequency', 'unknown')}")
                source_urls = entry.get("source_urls", [])
                if source_urls:
                    print(f"    Source: {source_urls[0]}")
                print()
        else:
            print("\n✓ No overdue entries")

        # Due this week section
        if due_this_week:
            print(f"\n📅 DUE THIS WEEK ({len(due_this_week)} entries)")
            print("-" * 40)
            for entry in sorted(due_this_week, key=lambda x: str(x.get("next_audit", ""))):
                print_entry_details(entry)
        else:
            print("\n✓ No entries due this week")

        # Summary counts
        print(f"\n📊 Coming up:")
        print(f"    Due this month (after this week): {len(due_this_month)}")
        print(f"    Due next month: {len(due_next_month)}")
        if unverified:
            print(f"    ⚠️  Unverified entries: {len(unverified)}")
        print()
        return  # Exit after weekly summary

    # === OVERDUE VIEW ===
    if args.overdue:
        print("=" * 60)
        print(f"OVERDUE ENTRIES (past next_audit date)")
        print("=" * 60)
        if overdue:
            for entry in sorted(overdue, key=lambda x: -x.get("_days_overdue", 0)):
                days = entry.get("_days_overdue", 0)
                print(f"  ⚠️  [{days} days overdue] {entry.get('name', 'Unknown')}")
                print_entry_details(entry)
            print(f"Total overdue: {len(overdue)}")
        else:
            print("  No overdue entries!\n")
        return  # Exit after overdue view

    # === DUE THIS WEEK VIEW ===
    if args.due_this_week:
        print("=" * 60)
        print(f"ENTRIES DUE THIS WEEK ({today_date} to {week_from_now})")
        print("=" * 60)
        if due_this_week:
            for entry in sorted(due_this_week, key=lambda x: str(x.get("next_audit", ""))):
                print_entry_details(entry)
            print(f"Total due this week: {len(due_this_week)}")
        else:
            print("  No entries due this week.\n")
        # Also show overdue count if any
        if overdue:
            print(f"\n⚠️  Note: {len(overdue)} overdue entries also need attention (run --overdue)")
        return  # Exit after due-this-week view

    # === DUE THIS MONTH VIEW ===
    if args.due_this_month:
        print("=" * 60)
        print(f"ENTRIES DUE FOR AUDIT THIS MONTH ({current_month})")
        print("=" * 60)
        # Include overdue + this week + rest of month
        all_due_this_month = overdue + due_this_week + due_this_month
        if all_due_this_month:
            for entry in sorted(all_due_this_month, key=lambda x: str(x.get("next_audit", ""))):
                prefix = ""
                if entry.get("_days_overdue"):
                    prefix = f"[OVERDUE {entry.get('_days_overdue')}d] "
                print(f"  {prefix}[{entry.get('category', 'N/A')}] {entry.get('name', 'Unknown')}")
                print_entry_details(entry)
            print(f"Total due this month: {len(all_due_this_month)}")
        else:
            print("  No entries due this month.\n")
        return

    # === DUE NEXT MONTH VIEW ===
    if args.due_next_month:
        print("=" * 60)
        print(f"ENTRIES DUE NEXT MONTH ({next_month})")
        print("=" * 60)
        if due_next_month:
            for entry in sorted(due_next_month, key=lambda x: str(x.get("next_audit", ""))):
                print_entry_details(entry, show_source_urls=False)
            print(f"Total due next month: {len(due_next_month)}")
        else:
            print("  No entries due next month.\n")
        return

    # === UNVERIFIED VIEW ===
    if args.unverified:
        print("=" * 60)
        print("UNVERIFIED ENTRIES (need official source)")
        print("=" * 60)
        if unverified:
            for entry in sorted(unverified, key=lambda x: x.get("category", "")):
                print(f"  [{entry.get('category', 'N/A')}] {entry.get('name', 'Unknown')}")
                print(f"    ID: {entry.get('id')}")
                flags = entry.get("flags", [])
                for flag in flags:
                    print(f"    Flag: {flag}")
                print()
            print(f"Total unverified: {len(unverified)}")
        else:
            print("  All entries verified!\n")
        return

    # === DATA QUALITY VIEW ===
    if args.quality:
        print("=" * 60)
        print("DATA QUALITY ISSUES")
        print("=" * 60)
        all_issues = []
        for entry in entries:
            issues = check_data_quality(entry)
            all_issues.extend(issues)

        if all_issues:
            for issue in sorted(all_issues):
                print(f"  {issue}")
            print(f"\nTotal issues: {len(all_issues)}")
        else:
            print("  No data quality issues found!\n")
        return

    # === FULL REPORT (default) ===

    # Overdue entries (always show if any)
    if overdue:
        print("=" * 60)
        print(f"⚠️  OVERDUE ENTRIES ({len(overdue)})")
        print("=" * 60)
        for entry in sorted(overdue, key=lambda x: -x.get("_days_overdue", 0)):
            days = entry.get("_days_overdue", 0)
            print(f"  [{days} days overdue] {entry.get('name', 'Unknown')}")
            print(f"    ID: {entry.get('id')}")
            print(f"    Due: {format_date(entry.get('next_audit'))}")
            print()

    # Due this month
    print("=" * 60)
    print(f"ENTRIES DUE FOR AUDIT THIS MONTH ({current_month})")
    print("=" * 60)
    if due_this_week or due_this_month:
        all_this_month = due_this_week + due_this_month
        for entry in sorted(all_this_month, key=lambda x: str(x.get("next_audit", ""))):
            print(f"  [{entry.get('category', 'N/A')}] {entry.get('name', 'Unknown')}")
            print(f"    ID: {entry.get('id')}")
            print(f"    Due: {format_date(entry.get('next_audit'))}")
            print(f"    Last verified: {format_date(entry.get('last_verified'))}")
            if entry.get("website"):
                print(f"    URL: {entry.get('website')}")
            print()
    else:
        print("  No entries due this month.\n")

    # Due next month
    print("=" * 60)
    print(f"ENTRIES DUE NEXT MONTH ({next_month})")
    print("=" * 60)
    if due_next_month:
        for entry in sorted(due_next_month, key=lambda x: str(x.get("next_audit", ""))):
            print(f"  [{entry.get('category', 'N/A')}] {entry.get('name', 'Unknown')}")
            print(f"    ID: {entry.get('id')}")
            print(f"    Due: {format_date(entry.get('next_audit'))}")
            print()
    else:
        print("  No entries due next month.\n")

    # Unverified
    print("=" * 60)
    print("UNVERIFIED ENTRIES (need official source)")
    print("=" * 60)
    if unverified:
        for entry in sorted(unverified, key=lambda x: x.get("category", "")):
            print(f"  [{entry.get('category', 'N/A')}] {entry.get('name', 'Unknown')}")
            print(f"    ID: {entry.get('id')}")
            flags = entry.get("flags", [])
            for flag in flags:
                print(f"    Flag: {flag}")
            print()
        print(f"Total unverified: {len(unverified)}")
    else:
        print("  All entries verified!\n")

    # Summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Total entries: {len(entries)}")
    print(f"  Overdue: {len(overdue)}")
    print(f"  Due this week: {len(due_this_week)}")
    print(f"  Due this month: {len(due_this_month)}")
    print(f"  Due next month: {len(due_next_month)}")
    print(f"  Unverified: {len(unverified)}")

    # Count by audit frequency (show "closed" for entries with CLOSED status)
    def get_frequency_label(entry):
        if entry.get("status") == "CLOSED":
            return "closed (no audit needed)"
        return entry.get("audit_frequency") or "unknown"

    frequencies = Counter(get_frequency_label(e) for e in entries)
    print("\n  By audit frequency:")
    for freq, count in sorted(frequencies.items()):
        print(f"    {freq}: {count}")

    # Count by location_type
    location_types = Counter(e.get("location_type") or "unset" for e in entries)
    print("\n  By location_type:")
    for loc_type, count in sorted(location_types.items()):
        print(f"    {loc_type}: {count}")

    # Count by resource_type
    resource_types = Counter(e.get("resource_type") or "unset" for e in entries)
    print("\n  By resource_type:")
    for res_type, count in sorted(resource_types.items()):
        print(f"    {res_type}: {count}")


if __name__ == "__main__":
    main()
