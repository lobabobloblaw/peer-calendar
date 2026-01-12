#!/usr/bin/env python3
"""
Mark an entry as audited and auto-update dates.

This script updates an entry's last_verified and next_audit dates,
and logs the audit to audit-log.yaml.

Usage:
    python audit_complete.py --id nami-multnomah              # Mark as verified (no changes)
    python audit_complete.py --id nami-multnomah --changes "Updated hours"  # Mark as updated
    python audit_complete.py --id nami-multnomah --preview    # Preview changes without writing
"""

import argparse
import re
from datetime import date, datetime, timedelta
from pathlib import Path

try:
    from dateutil.relativedelta import relativedelta
    HAS_DATEUTIL = True
except ImportError:
    HAS_DATEUTIL = False


def calculate_next_audit(frequency: str, from_date: date = None) -> date:
    """Calculate the next audit date based on frequency."""
    from_date = from_date or date.today()

    if HAS_DATEUTIL:
        if frequency == "weekly":
            return from_date + relativedelta(weeks=1)
        elif frequency == "monthly":
            return from_date + relativedelta(months=1)
        elif frequency == "quarterly":
            return from_date + relativedelta(months=3)
        elif frequency == "annually":
            return from_date + relativedelta(years=1)
        else:
            return from_date + relativedelta(months=3)  # default to quarterly
    else:
        # Fallback without dateutil (less accurate for month boundaries)
        if frequency == "weekly":
            return from_date + timedelta(days=7)
        elif frequency == "monthly":
            return from_date + timedelta(days=30)
        elif frequency == "quarterly":
            return from_date + timedelta(days=91)
        elif frequency == "annually":
            return from_date + timedelta(days=365)
        else:
            return from_date + timedelta(days=91)


def find_entry_info(content: str, entry_id: str) -> dict | None:
    """Find entry in sources.yaml and extract current info."""
    lines = content.split('\n')
    in_entry = False
    entry_info = {'id': entry_id}
    current_indent = 0

    for i, line in enumerate(lines):
        # Look for entry start
        id_match = re.match(r'^- id: (.+)$', line)
        if id_match:
            if id_match.group(1).strip() == entry_id:
                in_entry = True
                entry_info['start_line'] = i
                continue
            elif in_entry:
                # Found next entry, we're done
                entry_info['end_line'] = i
                break

        if in_entry:
            # Extract fields
            if line.strip().startswith('name:'):
                entry_info['name'] = line.split(':', 1)[1].strip()
            elif line.strip().startswith('audit_frequency:'):
                entry_info['audit_frequency'] = line.split(':', 1)[1].strip()
            elif line.strip().startswith('last_verified:'):
                entry_info['last_verified_line'] = i
                entry_info['last_verified'] = line.split(':', 1)[1].strip()
            elif line.strip().startswith('next_audit:'):
                entry_info['next_audit_line'] = i
                entry_info['next_audit'] = line.split(':', 1)[1].strip()

    if in_entry and 'end_line' not in entry_info:
        entry_info['end_line'] = len(lines)

    return entry_info if in_entry else None


def update_sources_yaml(sources_path: Path, entry_id: str, new_last_verified: str,
                        new_next_audit: str, preview: bool = False) -> bool:
    """Update the entry's dates in sources.yaml."""
    with open(sources_path, 'r', encoding='utf-8') as f:
        content = f.read()

    lines = content.split('\n')
    entry_info = find_entry_info(content, entry_id)

    if not entry_info:
        print(f"Error: Entry '{entry_id}' not found in sources.yaml")
        return False

    # Update last_verified line
    if 'last_verified_line' in entry_info:
        old_line = lines[entry_info['last_verified_line']]
        # Preserve indentation
        indent = len(old_line) - len(old_line.lstrip())
        lines[entry_info['last_verified_line']] = ' ' * indent + f'last_verified: {new_last_verified}'

    # Update next_audit line
    if 'next_audit_line' in entry_info:
        old_line = lines[entry_info['next_audit_line']]
        indent = len(old_line) - len(old_line.lstrip())
        lines[entry_info['next_audit_line']] = ' ' * indent + f'next_audit: {new_next_audit}'

    new_content = '\n'.join(lines)

    if preview:
        print(f"\n[PREVIEW] Would update sources.yaml:")
        print(f"  last_verified: {entry_info.get('last_verified', 'N/A')} -> {new_last_verified}")
        print(f"  next_audit: {entry_info.get('next_audit', 'N/A')} -> {new_next_audit}")
        return True

    with open(sources_path, 'w', encoding='utf-8') as f:
        f.write(new_content)

    return True


def append_audit_log(log_path: Path, entry_id: str, entry_name: str,
                     status: str, changes: str | None, preview: bool = False) -> bool:
    """Append an entry to audit-log.yaml."""
    today = date.today().strftime('%Y-%m-%d')

    log_entry = f"""
---
- date: {today}
  type: audit
  auditor: user
  summary: "Audit completed - {entry_name}"
  entries_audited: 1
  entries:
    - id: {entry_id}
      status: {status}"""

    if changes:
        log_entry += f'\n      changes: "{changes}"'

    if preview:
        print(f"\n[PREVIEW] Would append to audit-log.yaml:")
        print(log_entry)
        return True

    with open(log_path, 'a', encoding='utf-8') as f:
        f.write(log_entry + '\n')

    return True


def main():
    parser = argparse.ArgumentParser(description="Mark an entry as audited")
    parser.add_argument("--id", required=True, help="Entry ID to mark as audited")
    parser.add_argument("--changes", help="Description of changes made (implies 'updated' status)")
    parser.add_argument("--preview", action="store_true", help="Preview changes without writing")
    parser.add_argument("--sources", default="../data/sources.yaml", help="Path to sources.yaml")
    parser.add_argument("--log", default="../data/audit-log.yaml", help="Path to audit-log.yaml")

    args = parser.parse_args()

    script_dir = Path(__file__).parent
    sources_path = (script_dir / args.sources).resolve()
    log_path = (script_dir / args.log).resolve()

    if not sources_path.exists():
        print(f"Error: sources.yaml not found at {sources_path}")
        return 1

    # Read current entry info
    with open(sources_path, 'r', encoding='utf-8') as f:
        content = f.read()

    entry_info = find_entry_info(content, args.id)
    if not entry_info:
        print(f"Error: Entry '{args.id}' not found")
        return 1

    entry_name = entry_info.get('name', args.id)
    frequency = entry_info.get('audit_frequency', 'quarterly')

    # Calculate new dates
    today = date.today()
    new_last_verified = today.strftime('%Y-%m-%d')
    new_next_audit = calculate_next_audit(frequency, today).strftime('%Y-%m-%d')

    # Determine status
    status = "updated" if args.changes else "verified"

    print(f"Entry: {entry_name}")
    print(f"  ID: {args.id}")
    print(f"  Frequency: {frequency}")
    print(f"  Status: {status}")
    if args.changes:
        print(f"  Changes: {args.changes}")

    if not HAS_DATEUTIL:
        print("\nNote: python-dateutil not installed, using approximate date calculation")

    # Update sources.yaml
    if not update_sources_yaml(sources_path, args.id, new_last_verified, new_next_audit, args.preview):
        return 1

    # Append to audit log
    if not append_audit_log(log_path, args.id, entry_name, status, args.changes, args.preview):
        return 1

    if not args.preview:
        print(f"\n✓ Updated {args.id}")
        print(f"  last_verified: {new_last_verified}")
        print(f"  next_audit: {new_next_audit}")
        print(f"  Logged to audit-log.yaml")

    return 0


if __name__ == "__main__":
    exit(main())
