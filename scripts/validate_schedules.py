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
from pathlib import Path

from utils import load_sources
from generate_calendar import parse_schedule


def validate_schedules(sources_path: str) -> int:
    """Validate all schedule strings and report issues."""
    entries = load_sources(sources_path)
    issues = 0
    checked = 0

    for entry in entries:
        entry_id = entry.get("id", "unknown")
        entry_name = entry.get("name", "unknown")

        # Check entry-level schedule
        schedule = entry.get("schedule")
        if schedule:
            checked += 1
            result = parse_schedule(schedule)
            problems = []
            if not result.get("day"):
                problems.append("no day detected")
            if not result.get("start_time"):
                problems.append("no time detected")
            if problems:
                print(f"  {entry_id}: {', '.join(problems)}")
                print(f"    Schedule: \"{schedule}\"")
                print(f"    Parsed: {result}")
                issues += 1

        # Check program-level schedules
        for prog in entry.get("programs", []):
            if not isinstance(prog, dict):
                continue
            prog_schedule = prog.get("schedule")
            if prog_schedule:
                checked += 1
                result = parse_schedule(prog_schedule)
                problems = []
                if not result.get("day"):
                    problems.append("no day detected")
                if not result.get("start_time"):
                    problems.append("no time detected")
                if problems:
                    prog_name = prog.get("name", "unnamed program")
                    print(f"  {entry_id} > {prog_name}: {', '.join(problems)}")
                    print(f"    Schedule: \"{prog_schedule}\"")
                    print(f"    Parsed: {result}")
                    issues += 1

    print(f"\nSchedule validation: {checked} schedules checked, {issues} issues found")
    return issues


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
