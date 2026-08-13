#!/usr/bin/env python3
"""Preview or apply the reviewed issue #5 quarterly-to-annual migration."""

from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path

from audit_policy import cadence_deadline
from utils import parse_date, parse_sources, validate_all_entries


MIGRATION_IDS = {
    "academy-theater", "adaptive-sports-northwest", "artichoke-music",
    "arts-for-all", "avalon-theatre", "charles-jordan-cc", "clackamas-adrc",
    "fat-girls-hiking-portland", "first-thursday",
    "free-geek",
    "gresham-music-parks", "gresham-splash-pads",
    "hidden-creek-community-center", "hollywood-farmers-market",
    "hollywood-theatre", "irco", "jade-night-market", "juanita-pohl-center",
    "lake-oswego-acc", "lake-oswego-lorac",
    "lake-oswego-parks-scholarship", "laurelhurst-theater",
    "living-room-theaters", "lynwood-community-farm",
    "matt-dishman-cc", "mhcc-senior-tuition", "multnomah-arts-center",
    "multnomah-days", "ncprd-aquatic-park", "ncprd-scholarship",
    "ops-fest-shakespeare", "oregon-food-bank-volunteer",
    "oregon-historical-society", "oregon-jewish-museum", "oregon-rail-heritage",
    "outgrowing-hunger", "peoples-yoga", "pier-park-disc-golf",
    "portland-memory-garden", "portland-saturday-market", "portland-sunday-parkways",
    "ppr-access-discount", "ppr-community-gardens",
    "rockwood-disc-golf", "snowcap-garden", "teenforce-portland",
    "thprd-financial-aid", "tigard-senior-center",
    "ttad-pools", "tualatin-recreation-scholarship", "write-around-portland",
    "ymca-columbia-willamette", "yoga-on-yamhill",
}

# These entries already carry a deliberately early date-sensitive or VERIFY
# checkpoint. Retiering must not hide that known work behind a later annual date.
PRESERVE_DUE_IDS = {
    "thprd-financial-aid", "gresham-music-parks", "jade-night-market",
    "portland-sunday-parkways", "portland-memory-garden",
    "ops-fest-shakespeare", "multnomah-days", "first-thursday",
    "hollywood-farmers-market", "lynwood-community-farm",
    "portland-saturday-market",
}


def _replace_entry_fields(content: str, entry_id: str, next_audit: date) -> str:
    pattern = re.compile(rf"(?ms)^- id: {re.escape(entry_id)}\n.*?(?=^---$|^- id: |\Z)")
    match = pattern.search(content)
    if not match:
        raise ValueError(f"entry not found: {entry_id}")
    block = match.group(0)
    if not re.search(r"(?m)^  audit_frequency: quarterly$", block):
        raise ValueError(f"{entry_id}: expected quarterly cadence")
    block = re.sub(r"(?m)^  audit_frequency: quarterly$", "  audit_frequency: annually", block, count=1)
    block = re.sub(r"(?m)^  next_audit: .*?$", f"  next_audit: {next_audit.isoformat()}", block, count=1)
    return content[:match.start()] + block + content[match.end():]


def migrate(
    content: str,
    migration_ids: set[str] | None = None,
    preserve_due_ids: set[str] | None = None,
) -> tuple[str, list[dict]]:
    migration_ids = MIGRATION_IDS if migration_ids is None else migration_ids
    preserve_due_ids = PRESERVE_DUE_IDS if preserve_due_ids is None else preserve_due_ids
    entries = {entry["id"]: entry for entry in parse_sources(content)}
    if set(migration_ids) - entries.keys():
        raise ValueError(f"missing migration IDs: {sorted(set(migration_ids) - entries.keys())}")

    last_verified_before = {key: parse_date(value.get("last_verified")) for key, value in entries.items()}
    changes = []
    output = content
    for entry_id in sorted(migration_ids):
        entry = entries[entry_id]
        if entry.get("audit_frequency") == "annually":
            continue
        if entry.get("audit_frequency") != "quarterly":
            raise ValueError(f"{entry_id}: expected quarterly or annually cadence")
        verified = parse_date(entry.get("last_verified"))
        current_due = parse_date(entry.get("next_audit"))
        if not verified or not current_due:
            raise ValueError(f"{entry_id}: invalid audit dates")
        new_deadline = cadence_deadline("annually", verified)
        new_due = current_due if entry_id in preserve_due_ids else new_deadline
        output = _replace_entry_fields(output, entry_id, new_due)
        changes.append({
            "id": entry_id,
            "from": "quarterly",
            "to": "annually",
            "old_next_audit": current_due.isoformat(),
            "new_next_audit": new_due.isoformat(),
        })

    migrated = parse_sources(output)
    warnings = validate_all_entries(migrated, quiet=True)
    if warnings:
        raise ValueError("migration failed validation:\n" + "\n".join(warnings))
    last_verified_after = {value["id"]: parse_date(value.get("last_verified")) for value in migrated}
    if last_verified_after != last_verified_before:
        raise ValueError("migration changed last_verified metadata")
    return output, changes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", default="../data/sources.yaml")
    parser.add_argument("--apply", action="store_true", help="Write the reviewed migration")
    parser.add_argument("--report", help="Write the migration inventory as JSON")
    args = parser.parse_args(argv)
    script_dir = Path(__file__).resolve().parent
    path = Path(args.sources)
    if not path.is_absolute():
        path = (script_dir / path).resolve()
    original = path.read_text(encoding="utf-8")
    updated, changes = migrate(original)
    if args.report:
        Path(args.report).write_text(json.dumps({"changes": changes}, indent=2) + "\n", encoding="utf-8")
    if args.apply:
        path.write_text(updated, encoding="utf-8")
        action = "Updated"
    else:
        action = "Would update"
    print(f"{action} {len(changes)} entries from quarterly to annually; last_verified unchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
