#!/usr/bin/env python3
"""
Validate all schedule strings in sources.yaml.

Parses every schedule field and reports any that fail to produce
a valid day or time. Run before calendar generation to catch issues.

Usage:
    python validate_schedules.py
    python validate_schedules.py --sources /path/to/sources.yaml
"""

import argparse
import re
from pathlib import Path

from utils import load_sources
from generate_calendar import parse_schedule

# Schedules matching these patterns are intentionally vague and should not
# block CI. They represent entries where the exact schedule is unknown or
# varies (e.g., "Contact for current schedule", "Various", "Weekly").
VAGUE_PATTERNS = [
    r"^various",
    r"^weekly",                  # "Weekly", "Weekly - varies by location", "Weekly, drop-in"
    r"^seasonal",
    r"^monthly",                 # "Monthly", "Monthly at 10:30am"
    r"^annual",
    r"^ongoing",
    r"^by appointment",
    r"contact\b.*\b(schedule|dates?|time)",
    r"check\b.*\b(website|calendar|facebook|meetup|eventbrite|library)",
    r"dates?\s+vary",
    r"times?\s+vary",
    r"various\s+(dates|times|events|workshops)",
    r"^\d+\+?\s+meetings",        # "900+ meetings per week"
    r"^multiple\b.*\b(meetings|groups)",
    r"^once\s+(weekly|monthly)",
    r"^twice\s+monthly",
    r"^periodic",
    r"summer\s+(evenings?|mornings?)",  # "Summer evenings (various dates)"
    r"\(was seasonal\)",
    r"^weekend\s+mornings?\s+during",  # "Weekend mornings during planting season"
    r"year-round\b.*\bcleanups",
    r"exhibitions?\s+per\s+year",
    r"^24/7",
    r"^365 days",
    r"done-in-a-day",
    # Date ranges, bare months, and season ranges
    r"^(january|february|march|april|may|june|july|august|september|october|november|december)(\s+\d+)?(\s*-\s*.+)?$",
    r"^\w+\s*-\s*(january|february|march|april|may|june|july|august|september|october|november|december)(\s|$)",
]
_vague_re = re.compile("|".join(VAGUE_PATTERNS), re.IGNORECASE)


def is_vague_schedule(schedule: str) -> bool:
    """Return True if this schedule is intentionally vague / unparseable."""
    return bool(_vague_re.search(schedule.strip()))


def validate_schedules(sources_path: str) -> int:
    """Validate all schedule strings and report issues.

    Returns the number of unexpected (non-vague) issues found.
    Vague schedules are reported as info but don't count as failures.
    """
    entries = load_sources(sources_path)
    hard_issues = 0
    vague_count = 0
    incomplete_count = 0
    checked = 0

    def check_schedule(schedule_str, label):
        nonlocal hard_issues, vague_count, incomplete_count
        result = parse_schedule(schedule_str)
        problems = []
        has_day = bool(result.get("day"))
        has_time = bool(result.get("start_time"))
        if not has_day:
            problems.append("no day detected")
        if not has_time:
            problems.append("no time detected")
        if not problems:
            return

        if is_vague_schedule(schedule_str):
            tag = "[vague]"
            vague_count += 1
        elif has_day and not has_time:
            # Has day but no time — incomplete data, not a parser bug
            tag = "[incomplete]"
            incomplete_count += 1
        else:
            tag = "[FAIL]"
            hard_issues += 1

        print(f"  {tag} {label}: {', '.join(problems)}")
        print(f"    Schedule: \"{schedule_str}\"")
        print(f"    Parsed: {result}")

    for entry in entries:
        entry_id = entry.get("id", "unknown")

        schedule = entry.get("schedule")
        if schedule:
            checked += 1
            check_schedule(schedule, entry_id)

        for prog in entry.get("programs", []):
            if not isinstance(prog, dict):
                continue
            prog_schedule = prog.get("schedule")
            if prog_schedule:
                checked += 1
                prog_name = prog.get("name", "unnamed program")
                check_schedule(prog_schedule, f"{entry_id} > {prog_name}")

    print(f"\nSchedule validation: {checked} checked, {hard_issues} failures, "
          f"{incomplete_count} incomplete, {vague_count} vague")
    if hard_issues:
        print(f"  {hard_issues} schedule(s) could not be parsed — fix data or update vague patterns")
    return hard_issues


def main():
    parser = argparse.ArgumentParser(description="Validate schedule strings in sources.yaml")
    parser.add_argument("--sources", default="../data/sources.yaml", help="Path to sources.yaml")
    args = parser.parse_args()

    script_dir = Path(__file__).parent
    sources_path = str((script_dir / args.sources).resolve())

    issues = validate_schedules(sources_path)
    return 1 if issues > 0 else 0


if __name__ == "__main__":
    exit(main())
