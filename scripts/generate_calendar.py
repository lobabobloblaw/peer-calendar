#!/usr/bin/env python3
"""
Generate iCal/ICS calendar feeds from sources.yaml

This script parses the resource database and generates calendar files
optimized for different platforms: Google Calendar, Apple Calendar, and Outlook.

Usage:
    python generate_calendar.py                        # Generate all platforms
    python generate_calendar.py --platform google      # Google Calendar only
    python generate_calendar.py --platform apple       # Apple Calendar only
    python generate_calendar.py --platform outlook     # Outlook only
    python generate_calendar.py --category peer_support  # Specific category
    python generate_calendar.py --json                 # Also generate JSON feed

Output structure:
    output/
    ├── google/
    │   ├── all-events.ics
    │   ├── peer_support.ics
    │   └── ...
    ├── apple/
    │   ├── all-events.ics
    │   ├── peer_support.ics
    │   └── ...
    ├── outlook/
    │   ├── all-events.ics
    │   ├── peer_support.ics
    │   └── ...
    └── events.json
"""

import argparse
import hashlib
import html
import json
import re
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

import yaml


# Category color scheme (hex colors)
CATEGORY_COLORS = {
    "peer_support": "#7B68EE",      # Medium slate blue - calming, mental health
    "fitness_wellness": "#32CD32",   # Lime green - health, activity
    "events": "#FF6347",             # Tomato red - excitement, events
    "arts_culture": "#9370DB",       # Medium purple - creativity
    "parks_nature": "#228B22",       # Forest green - nature
    "food_farms": "#DAA520",         # Goldenrod - harvest, food
    "social_activities": "#FF69B4",  # Hot pink - social, community
    "discount_programs": "#4169E1",  # Royal blue - services, programs
    "transportation": "#708090",     # Slate gray - transit, infrastructure
}

# Human-readable category names
CATEGORY_NAMES = {
    "peer_support": "Peer Support",
    "fitness_wellness": "Fitness & Wellness",
    "events": "Events & Festivals",
    "arts_culture": "Arts & Culture",
    "parks_nature": "Parks & Nature",
    "food_farms": "Food & Farms",
    "social_activities": "Social Activities",
    "discount_programs": "Discount Programs",
    "transportation": "Transportation",
}


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


def generate_uid(entry_id: str, date_str: str = "") -> str:
    """Generate a unique identifier for calendar events."""
    unique_string = f"{entry_id}-{date_str}"
    return hashlib.md5(unique_string.encode()).hexdigest()[:16] + "@portlandresources.org"


def parse_schedule(schedule_str: str) -> dict:
    """Parse schedule strings into structured data."""
    if not schedule_str:
        return {}

    result = {}
    schedule_lower = schedule_str.lower()

    day_map = {
        "sunday": "SU", "sundays": "SU",
        "monday": "MO", "mondays": "MO",
        "tuesday": "TU", "tuesdays": "TU",
        "wednesday": "WE", "wednesdays": "WE",
        "thursday": "TH", "thursdays": "TH",
        "friday": "FR", "fridays": "FR",
        "saturday": "SA", "saturdays": "SA",
    }

    for day_name, day_code in day_map.items():
        if day_name in schedule_lower:
            result["day"] = day_code
            break

    ordinal_pattern = r"(\d+)(?:st|nd|rd|th)"
    ordinals = re.findall(ordinal_pattern, schedule_lower)
    if ordinals:
        result["week_of_month"] = [int(o) for o in ordinals]

    if "every" in schedule_lower:
        result["weekly"] = True

    time_pattern = r"(\d{1,2})(?::(\d{2}))?\s*-\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?"
    time_match = re.search(time_pattern, schedule_lower)
    if time_match:
        start_hour = int(time_match.group(1))
        start_min = int(time_match.group(2) or 0)
        end_hour = int(time_match.group(3))
        end_min = int(time_match.group(4) or 0)
        period = time_match.group(5)

        if period == "pm":
            if start_hour < 12:
                start_hour += 12
            if end_hour < 12:
                end_hour += 12
        elif period == "am":
            if start_hour == 12:
                start_hour = 0
            if end_hour == 12:
                end_hour = 0

        result["start_time"] = f"{start_hour:02d}:{start_min:02d}"
        result["end_time"] = f"{end_hour:02d}:{end_min:02d}"

    return result


def parse_date_string(date_str: str) -> tuple[datetime | None, datetime | None]:
    """Parse date strings into datetime objects."""
    if not date_str:
        return None, None

    current_year = datetime.now().year

    months = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12
    }

    date_lower = date_str.lower()

    range_pattern = r"(\w+)\s+(\d{1,2})\s*-\s*(\d{1,2}),?\s*(\d{4})?"
    single_pattern = r"(\w+)\s+(\d{1,2}),?\s*(\d{4})?"

    range_match = re.search(range_pattern, date_lower)
    if range_match:
        month_name = range_match.group(1)
        start_day = int(range_match.group(2))
        end_day = int(range_match.group(3))
        year = int(range_match.group(4)) if range_match.group(4) else current_year + 1

        if month_name in months:
            month = months[month_name]
            try:
                start_date = datetime(year, month, start_day)
                end_date = datetime(year, month, end_day)
                return start_date, end_date
            except ValueError:
                pass

    single_match = re.search(single_pattern, date_lower)
    if single_match:
        month_name = single_match.group(1)
        day = int(single_match.group(2))
        year = int(single_match.group(3)) if single_match.group(3) else current_year + 1

        if month_name in months:
            month = months[month_name]
            try:
                start_date = datetime(year, month, day)
                return start_date, None
            except ValueError:
                pass

    return None, None


def format_ical_date(dt: datetime, all_day: bool = False) -> str:
    """Format datetime for iCal."""
    if all_day:
        return dt.strftime("%Y%m%d")
    return dt.strftime("%Y%m%dT%H%M%S")


def escape_ical_text(text: str) -> str:
    r"""Escape special characters for iCal format.

    Per RFC 5545, these characters must be escaped with backslash:
    - Backslash itself: \\
    - Semicolon: \;
    - Comma: \,
    - Newline: \n (literal backslash-n in the file)
    """
    if not text:
        return ""
    # Order matters: escape backslashes first
    text = text.replace("\\", "\\\\")
    text = text.replace(";", "\\;")
    text = text.replace(",", "\\,")
    # Use raw string to get literal \n in output
    text = text.replace("\n", r"\n")
    return text


def fold_ical_line(line: str, max_length: int = 75) -> str:
    """Fold long lines according to iCal spec."""
    if len(line) <= max_length:
        return line

    result = []
    while len(line) > max_length:
        result.append(line[:max_length])
        line = " " + line[max_length:]
    result.append(line)
    return "\r\n".join(result)


def generate_event_description(entry: dict, program: dict = None) -> tuple[str, str]:
    """
    Generate event descriptions in both plain text and HTML formats.
    Returns (plain_text, html_text).
    """
    parts = []
    html_parts = []

    # Category label
    category = entry.get("category", "general")
    category_name = CATEGORY_NAMES.get(category, category.replace("_", " ").title())
    parts.append(f"Category: {category_name}")
    html_parts.append(f"<p><strong>Category:</strong> {html.escape(category_name)}</p>")

    # Pricing
    pricing = entry.get("pricing", {})
    if isinstance(pricing, dict):
        if "description" in pricing:
            parts.append(f"Cost: {pricing['description']}")
            html_parts.append(f"<p><strong>Cost:</strong> {html.escape(pricing['description'])}</p>")
        if "notes" in pricing:
            parts.append(f"Note: {pricing['notes']}")
            html_parts.append(f"<p><em>{html.escape(pricing['notes'])}</em></p>")
    elif isinstance(pricing, str):
        parts.append(f"Cost: {pricing}")
        html_parts.append(f"<p><strong>Cost:</strong> {html.escape(pricing)}</p>")

    # Program-specific info
    if program:
        if program.get("format"):
            parts.append(f"Format: {program['format']}")
            html_parts.append(f"<p><strong>Format:</strong> {html.escape(program['format'])}</p>")
        if program.get("eligibility"):
            parts.append(f"Eligibility: {program['eligibility']}")
            html_parts.append(f"<p><strong>Eligibility:</strong> {html.escape(program['eligibility'])}</p>")
        if program.get("notes"):
            parts.append(f"Info: {program['notes']}")
            html_parts.append(f"<p>{html.escape(program['notes'])}</p>")

    # Address
    if entry.get("address"):
        parts.append(f"Address: {entry['address']}")
        html_parts.append(f"<p><strong>Address:</strong> {html.escape(entry['address'])}</p>")

    # Phone
    if entry.get("phone"):
        parts.append(f"Phone: {entry['phone']}")
        html_parts.append(f"<p><strong>Phone:</strong> <a href=\"tel:{entry['phone']}\">{html.escape(entry['phone'])}</a></p>")

    # Website
    if entry.get("website"):
        parts.append(f"Website: {entry['website']}")
        html_parts.append(f"<p><strong>Website:</strong> <a href=\"{entry['website']}\">{html.escape(entry['website'])}</a></p>")

    # Eligibility (entry-level)
    if entry.get("eligibility") and not program:
        parts.append(f"Eligibility: {entry['eligibility']}")
        html_parts.append(f"<p><strong>Eligibility:</strong> {html.escape(str(entry['eligibility']))}</p>")

    # Notes
    if entry.get("notes"):
        parts.append(f"Details: {entry['notes']}")
        html_parts.append(f"<p><strong>Details:</strong> {html.escape(entry['notes'])}</p>")

    plain_text = "\n".join(parts)
    html_text = "<!DOCTYPE HTML PUBLIC \"-//W3C//DTD HTML 3.2//EN\"><HTML><BODY>" + "".join(html_parts) + "</BODY></HTML>"

    return plain_text, html_text


def create_vevent(
    uid: str,
    summary: str,
    description: str,
    location: str,
    dtstart: str,
    dtend: str,
    all_day: bool = False,
    rrule: str = None,
    url: str = None,
    category: str = None,
    platform: str = "google",
    html_description: str = None
) -> str:
    """Create a VEVENT component optimized for the target platform."""
    lines = [
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{format_ical_date(datetime.now())}Z",
    ]

    # Date/time handling
    if all_day:
        lines.append(f"DTSTART;VALUE=DATE:{dtstart}")
        if dtend:
            lines.append(f"DTEND;VALUE=DATE:{dtend}")
    else:
        lines.append(f"DTSTART:{dtstart}")
        if dtend:
            lines.append(f"DTEND:{dtend}")

    # Summary with category prefix for combined calendars
    lines.append(fold_ical_line(f"SUMMARY:{escape_ical_text(summary)}"))

    # Description - plain text for all, HTML for Outlook
    if description:
        lines.append(fold_ical_line(f"DESCRIPTION:{escape_ical_text(description)}"))

    # Outlook: Add HTML description
    if platform == "outlook" and html_description:
        # X-ALT-DESC must be properly escaped and folded
        escaped_html = escape_ical_text(html_description)
        lines.append(fold_ical_line(f"X-ALT-DESC;FMTTYPE=text/html:{escaped_html}"))
        # Set as busy by default
        lines.append("X-MICROSOFT-CDO-BUSYSTATUS:FREE")

    # Location
    if location:
        lines.append(fold_ical_line(f"LOCATION:{escape_ical_text(location)}"))

    # URL
    if url:
        lines.append(f"URL:{url}")

    # Recurrence rule
    if rrule:
        lines.append(f"RRULE:{rrule}")

    # Categories - included for all platforms (some may ignore)
    if category:
        category_name = CATEGORY_NAMES.get(category, category.replace("_", " ").title())
        lines.append(f"CATEGORIES:{category_name}")

    # Transparency (show as free/busy)
    lines.append("TRANSP:TRANSPARENT")

    lines.append("END:VEVENT")

    return "\r\n".join(lines)


def entry_to_events(entry: dict, platform: str = "google") -> list[str]:
    """Convert a source entry to one or more VEVENT strings."""
    events = []
    entry_id = entry.get("id", "unknown")
    name = entry.get("name", "Unnamed Event")
    category = entry.get("category", "general")
    address = entry.get("address", "")
    website = entry.get("website", "")

    # Handle entries with specific dates (events)
    dates = entry.get("dates")
    if dates:
        description, html_desc = generate_event_description(entry)
        if isinstance(dates, str):
            start_date, end_date = parse_date_string(dates)
            if start_date:
                uid = generate_uid(entry_id, start_date.strftime("%Y%m%d"))
                dtstart = format_ical_date(start_date, all_day=True)
                dtend = format_ical_date(end_date + timedelta(days=1), all_day=True) if end_date else format_ical_date(start_date + timedelta(days=1), all_day=True)
                events.append(create_vevent(
                    uid=uid,
                    summary=name,
                    description=description,
                    location=address,
                    dtstart=dtstart,
                    dtend=dtend,
                    all_day=True,
                    url=website,
                    category=category,
                    platform=platform,
                    html_description=html_desc
                ))
        elif isinstance(dates, list):
            for date_item in dates:
                if isinstance(date_item, str):
                    start_date, end_date = parse_date_string(date_item)
                    if start_date:
                        uid = generate_uid(entry_id, start_date.strftime("%Y%m%d"))
                        dtstart = format_ical_date(start_date, all_day=True)
                        dtend = format_ical_date(end_date + timedelta(days=1), all_day=True) if end_date else format_ical_date(start_date + timedelta(days=1), all_day=True)
                        events.append(create_vevent(
                            uid=uid,
                            summary=name,
                            description=description,
                            location=address,
                            dtstart=dtstart,
                            dtend=dtend,
                            all_day=True,
                            url=website,
                            category=category,
                            platform=platform,
                            html_description=html_desc
                        ))

    # Handle recurring programs
    programs = entry.get("programs", [])
    if isinstance(programs, list):
        for program in programs:
            if isinstance(program, dict) and "schedule" in program:
                program_name = program.get("name", name)
                full_name = f"{name}: {program_name}" if program_name != name else name
                schedule = parse_schedule(program.get("schedule", ""))

                if schedule.get("day") and schedule.get("start_time"):
                    description, html_desc = generate_event_description(entry, program)

                    rrule_parts = [f"FREQ=WEEKLY;BYDAY={schedule['day']}"]
                    if schedule.get("week_of_month"):
                        weeks = schedule["week_of_month"]
                        rrule_parts = [f"FREQ=MONTHLY;BYDAY={schedule['day']};BYSETPOS={','.join(map(str, weeks))}"]

                    rrule = ";".join(rrule_parts)

                    # Use schedule_start_date if specified, otherwise use today
                    schedule_start = entry.get("schedule_start_date")
                    if schedule_start:
                        if isinstance(schedule_start, str):
                            base_date = datetime.strptime(schedule_start, "%Y-%m-%d")
                        else:
                            base_date = datetime(schedule_start.year, schedule_start.month, schedule_start.day)
                    else:
                        base_date = datetime.now()

                    day_map = {"SU": 6, "MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5}
                    target_day = day_map.get(schedule["day"], 0)
                    days_ahead = target_day - base_date.weekday()
                    if days_ahead < 0:
                        days_ahead += 7
                    next_occurrence = base_date + timedelta(days=days_ahead)

                    start_time = schedule["start_time"].split(":")
                    end_time = schedule["end_time"].split(":") if schedule.get("end_time") else start_time

                    dtstart = next_occurrence.replace(
                        hour=int(start_time[0]),
                        minute=int(start_time[1]),
                        second=0,
                        microsecond=0
                    )
                    dtend = next_occurrence.replace(
                        hour=int(end_time[0]),
                        minute=int(end_time[1]),
                        second=0,
                        microsecond=0
                    )

                    program_location = program.get("location", address)

                    uid = generate_uid(entry_id, program_name)
                    events.append(create_vevent(
                        uid=uid,
                        summary=full_name,
                        description=description,
                        location=program_location,
                        dtstart=format_ical_date(dtstart),
                        dtend=format_ical_date(dtend),
                        rrule=rrule,
                        url=website,
                        category=category,
                        platform=platform,
                        html_description=html_desc
                    ))

    # Handle schedule field directly on entry
    schedule_str = entry.get("schedule")
    if schedule_str and not programs and not dates:
        schedule = parse_schedule(schedule_str)
        if schedule.get("day") and schedule.get("start_time"):
            description, html_desc = generate_event_description(entry)

            rrule_parts = [f"FREQ=WEEKLY;BYDAY={schedule['day']}"]
            if schedule.get("week_of_month"):
                weeks = schedule["week_of_month"]
                rrule_parts = [f"FREQ=MONTHLY;BYDAY={schedule['day']};BYSETPOS={','.join(map(str, weeks))}"]

            rrule = ";".join(rrule_parts)

            # Use schedule_start_date if specified, otherwise use today
            schedule_start = entry.get("schedule_start_date")
            if schedule_start:
                if isinstance(schedule_start, str):
                    base_date = datetime.strptime(schedule_start, "%Y-%m-%d")
                else:
                    base_date = datetime(schedule_start.year, schedule_start.month, schedule_start.day)
            else:
                base_date = datetime.now()

            day_map = {"SU": 6, "MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5}
            target_day = day_map.get(schedule["day"], 0)
            days_ahead = target_day - base_date.weekday()
            if days_ahead < 0:
                days_ahead += 7
            next_occurrence = base_date + timedelta(days=days_ahead)

            start_time = schedule["start_time"].split(":")
            end_time = schedule["end_time"].split(":") if schedule.get("end_time") else start_time

            dtstart = next_occurrence.replace(
                hour=int(start_time[0]),
                minute=int(start_time[1]),
                second=0,
                microsecond=0
            )
            dtend = next_occurrence.replace(
                hour=int(end_time[0]),
                minute=int(end_time[1]),
                second=0,
                microsecond=0
            )

            uid = generate_uid(entry_id, "recurring")
            events.append(create_vevent(
                uid=uid,
                summary=name,
                description=description,
                location=address,
                dtstart=format_ical_date(dtstart),
                dtend=format_ical_date(dtend),
                rrule=rrule,
                url=website,
                category=category,
                platform=platform,
                html_description=html_desc
            ))

    return events


def generate_vtimezone() -> str:
    """Generate VTIMEZONE component for America/Los_Angeles."""
    return """BEGIN:VTIMEZONE
TZID:America/Los_Angeles
X-LIC-LOCATION:America/Los_Angeles
BEGIN:DAYLIGHT
TZOFFSETFROM:-0800
TZOFFSETTO:-0700
TZNAME:PDT
DTSTART:19700308T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:-0700
TZOFFSETTO:-0800
TZNAME:PST
DTSTART:19701101T020000
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
END:STANDARD
END:VTIMEZONE"""


def create_vcalendar(
    events: list[str],
    calendar_name: str,
    platform: str = "google",
    category: str = None
) -> str:
    """Create a full VCALENDAR optimized for the target platform."""
    header = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Portland Metro Resources//Calendar Generator//EN",
        f"X-WR-CALNAME:{calendar_name}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]

    # Platform-specific headers
    if platform == "google":
        # Google needs explicit timezone
        header.append("X-WR-TIMEZONE:America/Los_Angeles")

    elif platform == "apple":
        header.append("X-WR-TIMEZONE:America/Los_Angeles")
        # Apple Calendar color
        if category and category in CATEGORY_COLORS:
            header.append(f"X-APPLE-CALENDAR-COLOR:{CATEGORY_COLORS[category]}")
        else:
            # Default color for combined calendar
            header.append("X-APPLE-CALENDAR-COLOR:#7B68EE")

    elif platform == "outlook":
        header.append("X-WR-TIMEZONE:America/Los_Angeles")

    # Add VTIMEZONE for all platforms
    timezone = generate_vtimezone()

    footer = ["END:VCALENDAR"]

    # Combine: header + timezone + events + footer
    header_str = "\r\n".join(header)
    footer_str = "\r\n".join(footer)

    return header_str + "\r\n" + timezone + "\r\n" + "\r\n".join(events) + "\r\n" + footer_str


def generate_json_feed(entries: list[dict]) -> dict:
    """Generate a JSON feed for web applications."""
    events = []

    for entry in entries:
        event_data = {
            "id": entry.get("id"),
            "title": entry.get("name"),
            "category": entry.get("category"),
            "categoryName": CATEGORY_NAMES.get(entry.get("category", ""), entry.get("category", "")),
            "color": CATEGORY_COLORS.get(entry.get("category", ""), "#808080"),
            "address": entry.get("address"),
            "phone": entry.get("phone"),
            "website": entry.get("website"),
            "pricing": entry.get("pricing"),
            "programs": entry.get("programs", []),
            "dates": entry.get("dates"),
            "schedule": entry.get("schedule"),
            "schedule_start_date": entry.get("schedule_start_date"),
            "flags": entry.get("flags", []),
            "accessibility": entry.get("accessibility", []),
            "social_intensity": entry.get("social_intensity"),
            "good_for": entry.get("good_for", []),
        }
        events.append(event_data)

    return {
        "generated": datetime.now().isoformat(),
        "count": len(events),
        "categories": CATEGORY_NAMES,
        "colors": CATEGORY_COLORS,
        "events": events
    }


def copy_to_docs(output_dir: Path, docs_dir: Path, platforms: list[str]) -> None:
    """Copy generated calendar files to docs/ for GitHub Pages hosting."""
    docs_dir.mkdir(parents=True, exist_ok=True)

    # Copy platform directories
    for platform in platforms:
        src_platform = output_dir / platform
        dst_platform = docs_dir / platform
        if src_platform.exists():
            # Remove existing and copy fresh
            if dst_platform.exists():
                shutil.rmtree(dst_platform)
            shutil.copytree(src_platform, dst_platform)

    # Copy events.json if it exists
    json_src = output_dir / "events.json"
    if json_src.exists():
        shutil.copy2(json_src, docs_dir / "events.json")

    print(f"Copied calendar files to {docs_dir}")


def main():
    parser = argparse.ArgumentParser(description="Generate calendar feeds from sources.yaml")
    parser.add_argument("--sources", default="../data/sources.yaml", help="Path to sources.yaml")
    parser.add_argument("--output", default="../output", help="Output directory")
    parser.add_argument("--platform", choices=["google", "apple", "outlook", "all"], default="all",
                        help="Target platform (default: all)")
    parser.add_argument("--category", help="Generate calendar for specific category only")
    parser.add_argument("--json", action="store_true", help="Also generate JSON feed")
    parser.add_argument("--publish", action="store_true",
                        help="Copy generated files to docs/ for GitHub Pages")

    args = parser.parse_args()

    script_dir = Path(__file__).parent
    sources_path = (script_dir / args.sources).resolve()
    output_dir = (script_dir / args.output).resolve()

    if not sources_path.exists():
        print(f"Error: sources.yaml not found at {sources_path}")
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading sources from {sources_path}...")
    entries = load_sources(sources_path)
    print(f"Loaded {len(entries)} entries")

    # Filter by category if specified
    if args.category:
        entries = [e for e in entries if e.get("category") == args.category]
        print(f"Filtered to {len(entries)} entries in category '{args.category}'")

    # Determine which platforms to generate
    platforms = ["google", "apple", "outlook"] if args.platform == "all" else [args.platform]

    # Group entries by category
    categories: dict[str, list[dict]] = {}
    for entry in entries:
        cat = entry.get("category", "general")
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(entry)

    # Generate calendars for each platform
    for platform in platforms:
        platform_dir = output_dir / platform
        platform_dir.mkdir(parents=True, exist_ok=True)

        all_events = []
        total_events = 0

        for category, cat_entries in categories.items():
            cat_events = []
            for entry in cat_entries:
                events = entry_to_events(entry, platform=platform)
                cat_events.extend(events)
                all_events.extend(events)

            if cat_events:
                category_name = CATEGORY_NAMES.get(category, category.replace("_", " ").title())
                calendar = create_vcalendar(
                    cat_events,
                    f"Portland Resources - {category_name}",
                    platform=platform,
                    category=category
                )
                output_path = platform_dir / f"{category}.ics"
                with open(output_path, "w", encoding="utf-8", newline="") as f:
                    f.write(calendar)
                total_events += len(cat_events)

        # Generate combined calendar with all categories
        if all_events:
            combined = create_vcalendar(
                all_events,
                "Portland Metro Resources - All Events",
                platform=platform,
                category=None  # No specific category color for combined
            )
            combined_path = platform_dir / "all-events.ics"
            with open(combined_path, "w", encoding="utf-8", newline="") as f:
                f.write(combined)

        print(f"Generated {platform}/ ({len(all_events)} events across {len(categories)} categories)")

    # Generate JSON feed (platform-independent)
    if args.json:
        json_feed = generate_json_feed(entries)
        json_path = output_dir / "events.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_feed, f, indent=2, default=str)
        print(f"Generated events.json")

    # Copy to docs/ for GitHub Pages if --publish flag is set
    if args.publish:
        docs_dir = script_dir.parent / "docs"
        copy_to_docs(output_dir, docs_dir, platforms)

    print(f"\nCalendar files saved to {output_dir}")
    print("\nOutput structure:")
    for platform in platforms:
        print(f"  {platform}/")
        print(f"    all-events.ics  - Combined calendar with all categories")
        for cat in sorted(categories.keys()):
            print(f"    {cat}.ics")

    print("\nPlatform-specific features:")
    print("  google/  - Proper VTIMEZONE, clean formatting")
    print("  apple/   - X-APPLE-CALENDAR-COLOR for category colors")
    print("  outlook/ - X-ALT-DESC for HTML descriptions, busy status")


if __name__ == "__main__":
    main()
