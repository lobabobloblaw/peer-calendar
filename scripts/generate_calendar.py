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
import calendar
import hashlib
import html
import json
import re
import shutil
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

from utils import load_sources, parse_date


# Category color scheme (hex colors)
CATEGORY_COLORS = {
    "peer_support": "#3E56B5",      # Blue - calming, mental health
    "fitness_wellness": "#496800",  # Olive green - health, activity
    "events": "#B6402F",            # Brick red - excitement, events
    "arts_culture": "#6949AC",      # Purple - creativity
    "parks_nature": "#176C47",      # Forest green - nature
    "food_farms": "#745800",        # Brown-gold - harvest, food
    "social_activities": "#AD2F77", # Magenta - social, community
    "discount_programs": "#1D5F9B", # Blue - services, programs
    "transportation": "#516170",    # Slate gray - transit, infrastructure
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

# Audience detection patterns
AUDIENCE_PATTERNS = {
    'children': [r'\bchildren\b', r'ages?\s*3[\s-]*12', r'kids?\b'],
    'teens': [r'teens?\b', r'ages?\s*13[\s-]*1[78]', r'grades?\s*[6-9][\s-]*12', r'adolescent'],
    'young_adults': [r'young\s*adults?', r'young\s*people', r'youth[\s-]*focused',
                     r'ages?\s*1[4-8][\s-]*35', r'ages?\s*18[\s-]*35', r'\(18-35\)', r'\(14-35\)'],
    'seniors': [r'seniors?\b', r'65\+', r'62\+', r'55\+', r'older\s*adults?'],
    'women': [r'\bwomen\b', r"women's", r'female[\s-]*identif', r'women[\s-]*only'],
    'lgbtq': [r'lgbtq', r'queer\b', r'lgbtqia', r'lgbtq2sia', r'pride\b'],
    'trans_nonbinary': [r'\btrans\b', r'nonbinary', r'non-binary', r'gender[\s-]*diverse'],
    'bipoc': [r'\bbipoc\b', r'black,?\s*indigenous', r'people\s*of\s*color'],
    'spanish_speaking': [r'spanish[\s-]*speaking', r'en\s*espa[nñ]ol', r'esperanza'],
}


def detect_audience(text: str) -> list:
    """Detect audience tags from text using pattern matching."""
    if not text:
        return []
    text_lower = text.lower()
    detected = set()
    for tag, patterns in AUDIENCE_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                # Filter out false positives
                if tag == 'children' and 'adult children' in text_lower:
                    continue  # "Adult Children of Alcoholics" is not for children
                detected.add(tag)
                break
    return sorted(list(detected))


def get_entry_audience(entry: dict) -> list:
    """Get audience for an entry, either from field or by detection."""
    # If audience is explicitly set, use it
    if entry.get("audience"):
        return entry.get("audience", [])

    # Otherwise, detect from text fields
    # Include practical_tips which often contains audience info
    practical_tips = entry.get("practical_tips", "")
    if isinstance(practical_tips, dict):
        practical_tips = " ".join(str(v) for v in practical_tips.values() if v)

    text_fields = [
        entry.get("name", ""),
        entry.get("eligibility", ""),
        entry.get("notes", ""),
        practical_tips,
    ]
    combined = " ".join(str(t) for t in text_fields if t)
    return detect_audience(combined)


def get_program_audience(program: dict, entry: dict) -> list:
    """Get audience for a program, either from field or by detection."""
    # If program has explicit audience, use it
    if program.get("audience"):
        return program.get("audience", [])

    # Otherwise, detect from program text
    text = " ".join([
        program.get("name", ""),
        str(program.get("eligibility", "")),
        str(program.get("notes", "")),
    ])
    detected = detect_audience(text)
    if detected:
        return detected

    # Fall back to entry-level audience
    return get_entry_audience(entry)


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

    # Normalize "noon" to "12:00" for time parsing
    schedule_normalized = re.sub(r'\bnoon\b', '12:00', schedule_lower)

    day_map = {
        "sunday": "SU", "sundays": "SU", "sun": "SU",
        "monday": "MO", "mondays": "MO", "mon": "MO",
        "tuesday": "TU", "tuesdays": "TU", "tue": "TU",
        "wednesday": "WE", "wednesdays": "WE", "wed": "WE",
        "thursday": "TH", "thursdays": "TH", "thu": "TH",
        "friday": "FR", "fridays": "FR", "fri": "FR",
        "saturday": "SA", "saturdays": "SA", "sat": "SA",
    }

    # Day ranges: "Mon-Fri", "Sat-Sun", "Wed-Sat", "Monday-Friday".
    # Ranges are expanded first, then any standalone day names are added, so a
    # string like "Fri 11am-1pm; Sat-Sun 2:30-4:30pm" keeps all three days.
    day_codes_ordered = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
    abbrev_to_idx = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
    day_word = r'(mon|tue|wed|thu|fri|sat|sun)(?:day|sday|nesday|rsday|urday)?s?'
    days_found = []
    range_spans = []
    for range_match in re.finditer(day_word + r'\s*[-–]\s*' + day_word, schedule_lower):
        start_idx = abbrev_to_idx[range_match.group(1)]
        end_idx = abbrev_to_idx[range_match.group(2)]
        if start_idx <= end_idx:
            span = range(start_idx, end_idx + 1)
        else:
            # Wrap-around range such as "Sat-Tue"
            span = list(range(start_idx, 7)) + list(range(0, end_idx + 1))
        for i in span:
            if day_codes_ordered[i] not in days_found:
                days_found.append(day_codes_ordered[i])
        range_spans.append(range_match.span())

    # Individual day matching (for "Tuesdays & Thursdays", "Tue/Thu"), skipping
    # day names already consumed by a range above.
    for day_name, day_code in sorted(day_map.items(), key=lambda x: -len(x[0])):
        if day_code in days_found:
            continue
        for match in re.finditer(r'\b' + re.escape(day_name) + r'\b', schedule_lower):
            if any(s <= match.start() < e for s, e in range_spans):
                continue
            days_found.append(day_code)
            break

    if days_found:
        # Keep a stable Mon-first ordering so output does not depend on dict order
        days_found = [d for d in day_codes_ordered if d in days_found]
        result["day"] = ",".join(days_found)

    ordinal_pattern = r"\b([1-5])(?:st|nd|rd|th)\b"
    ordinals = re.findall(ordinal_pattern, schedule_lower)
    if ordinals:
        result["week_of_month"] = sorted({int(o) for o in ordinals})

    # "Last Sunday of each month", "Last Wednesday"
    if re.search(r'\blast\b', schedule_lower) and not ordinals:
        result["last_of_month"] = True

    if "every" in schedule_lower:
        result["weekly"] = True

    # "Every other Monday", "bi-weekly", "alternate Tuesdays"
    if re.search(r'every\s+other|bi-?weekly|alternate', schedule_lower):
        result["interval"] = 2

    # "Daily 2-10pm" means every day, but only when no explicit days were given.
    # Otherwise phrases like "Fri-Sun (check Facebook for daily schedule)" would
    # be widened to all seven days.
    if re.search(r'\bdaily\b', schedule_lower) and not result.get("day"):
        result["daily"] = True
        result["day"] = "MO,TU,WE,TH,FR,SA,SU"

    if "weekdays" in schedule_lower and not result.get("day"):
        result["day"] = "MO,TU,WE,TH,FR"
        result["weekly"] = True

    time_pattern = r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*-\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?"
    time_match = re.search(time_pattern, schedule_normalized)
    if time_match:
        start_hour = int(time_match.group(1))
        start_min = int(time_match.group(2) or 0)
        start_period = time_match.group(3)
        end_hour = int(time_match.group(4))
        end_min = int(time_match.group(5) or 0)
        end_period = time_match.group(6)

        # Infer start period when only end has one (matches JS parseSchedule logic)
        if not start_period and end_period:
            raw_end_hour = int(time_match.group(4))
            if start_hour <= raw_end_hour and end_period == "pm" and start_hour < 12:
                # Same period: "2-10pm" means 2pm-10pm
                start_period = "pm"
            # else: different periods, start stays as AM: "10-7pm" = 10am-7pm

        if start_period == "pm" and start_hour < 12:
            start_hour += 12
        elif start_period == "am" and start_hour == 12:
            start_hour = 0

        if end_period == "pm" and end_hour < 12:
            end_hour += 12
        elif end_period == "am" and end_hour == 12:
            end_hour = 0

        result["start_time"] = f"{start_hour:02d}:{start_min:02d}"
        result["end_time"] = f"{end_hour:02d}:{end_min:02d}"
    else:
        # Try single time (e.g., "6pm", "10am") — assume 1-hour duration
        single_time = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)', schedule_normalized)
        if single_time:
            hour = int(single_time.group(1))
            minute = int(single_time.group(2) or 0)
            period = single_time.group(3)
            if period == "pm" and hour < 12:
                hour += 12
            elif period == "am" and hour == 12:
                hour = 0
            result["start_time"] = f"{hour:02d}:{minute:02d}"
            end_hour = hour + 1 if hour < 23 else 23
            end_minute = minute if hour < 23 else 59
            result["end_time"] = f"{end_hour:02d}:{end_minute:02d}"

    return result


MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
    "aug": 8, "sept": 9, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

_MONTH_ALT = "|".join(sorted(MONTHS, key=len, reverse=True))


def _resolve_year(explicit_year: int | None, month: int, day: int, today: date | None = None) -> int:
    """Pick the year for a date that may not carry one.

    When a year is written in the string it always wins. Otherwise assume the
    next occurrence of that month/day: this year if it has not passed yet,
    next year if it has. (Previously this always guessed next year, which put
    every year-less date - and, because of a parsing gap, several dates that
    *did* carry a year - twelve months into the future.)
    """
    if explicit_year:
        return explicit_year
    today = today or date.today()
    try:
        candidate = date(today.year, month, day)
    except ValueError:  # e.g. Feb 29 in a non-leap year
        return today.year
    return today.year if candidate >= today else today.year + 1


def parse_date_string(date_str: str, today: date | None = None) -> tuple[datetime | None, datetime | None]:
    """Parse date strings into (start, end) datetimes.

    Handles same-month ranges ("July 17-19, 2026"), cross-month ranges
    ("May 22 - June 28, 2026"), month-to-month spans without days
    ("June through August 2026"), and single dates.
    """
    if not date_str:
        return None, None

    date_lower = date_str.lower()

    # An explicit four-digit year anywhere in the string applies to the whole range
    year_match = re.search(r"\b(20\d{2})\b", date_lower)
    explicit_year = int(year_match.group(1)) if year_match else None

    month_day = rf"({_MONTH_ALT})\s+(\d{{1,2}})\b"
    dash = r"\s*(?:-|–|—|to|through|thru)\s*"

    # Cross-month range: "May 22 - June 28, 2026"
    m = re.search(month_day + dash + month_day, date_lower)
    if m:
        start_month, start_day = MONTHS[m.group(1)], int(m.group(2))
        end_month, end_day = MONTHS[m.group(3)], int(m.group(4))
        year = _resolve_year(explicit_year, start_month, start_day, today)
        end_year = year + 1 if end_month < start_month else year
        try:
            return datetime(year, start_month, start_day), datetime(end_year, end_month, end_day)
        except ValueError:
            pass

    # Same-month range: "July 17-19, 2026", "December 15-31"
    m = re.search(month_day + dash + r"(\d{1,2})\b", date_lower)
    if m:
        month, start_day, end_day = MONTHS[m.group(1)], int(m.group(2)), int(m.group(3))
        year = _resolve_year(explicit_year, month, start_day, today)
        try:
            return datetime(year, month, start_day), datetime(year, month, end_day)
        except ValueError:
            pass

    # Month-to-month span without days: "June through August 2026"
    m = re.search(rf"\b({_MONTH_ALT})\b{dash}\b({_MONTH_ALT})\b", date_lower)
    if m:
        start_month, end_month = MONTHS[m.group(1)], MONTHS[m.group(2)]
        year = _resolve_year(explicit_year, start_month, 1, today)
        end_year = year + 1 if end_month < start_month else year
        last_day = calendar.monthrange(end_year, end_month)[1]
        return datetime(year, start_month, 1), datetime(end_year, end_month, last_day)

    # Single date: "June 6, 2026"
    m = re.search(month_day, date_lower)
    if m:
        month, day = MONTHS[m.group(1)], int(m.group(2))
        year = _resolve_year(explicit_year, month, day, today)
        try:
            return datetime(year, month, day), None
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

    # Program pricing overrides a venue/resource's general pricing. This matters
    # for cases such as a free-admission museum hosting a ticketed fundraiser.
    pricing = program.get("cost") if program and program.get("cost") is not None else entry.get("pricing", {})
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
    html_description: str = None,
    dtstamp: str = None,
) -> str:
    """Create a VEVENT component optimized for the target platform."""
    lines = [
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{dtstamp or DEFAULT_DTSTAMP}",
    ]

    # Date/time handling
    if all_day:
        lines.append(f"DTSTART;VALUE=DATE:{dtstart}")
        if dtend:
            lines.append(f"DTEND;VALUE=DATE:{dtend}")
    else:
        lines.append(f"DTSTART;TZID=America/Los_Angeles:{dtstart}")
        if dtend:
            lines.append(f"DTEND;TZID=America/Los_Angeles:{dtend}")

    # Summary with category prefix for combined calendars
    lines.append(fold_ical_line(f"SUMMARY:{escape_ical_text(summary)}"))

    # Description - plain text for all, HTML for Outlook
    if description:
        lines.append(fold_ical_line(f"DESCRIPTION:{escape_ical_text(description)}"))

    # Outlook: Add HTML description (no iCal escaping — HTML uses its own encoding;
    # no line folding — splitting mid-tag corrupts HTML and Outlook handles long lines)
    if platform == "outlook" and html_description:
        lines.append(f"X-ALT-DESC;FMTTYPE=text/html:{html_description}")
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


WEEKDAY_INDEX = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}

# Versioned contract consumed by docs/index.html. Human-readable schedule text
# remains in the feed for display, but clients should use ``resolved_schedule``
# for recurrence math so every surface agrees with the ICS generator.
SCHEDULE_SCHEMA_VERSION = 1

# Recurring events with no schedule_start_date are anchored here rather than at
# generation time. An RRULE runs forward from DTSTART indefinitely, so a fixed
# anchor produces exactly the same series - but the output stops changing on
# every CI run, which keeps the docs/ diff limited to what the data change did.
CALENDAR_EPOCH = datetime(2026, 1, 1)

DEFAULT_DTSTAMP = "20260101T000000Z"


def entry_dtstamp(entry: dict) -> str:
    """DTSTAMP for an entry's events, taken from when its data was last confirmed.

    Using `last_verified` rather than the wall clock keeps regenerated feeds
    byte-identical until the underlying data actually changes, and gives the
    stamp a meaning: this is when a human last checked these details.
    """
    verified = parse_date(entry.get("last_verified"))
    if not verified:
        return DEFAULT_DTSTAMP
    return verified.strftime("%Y%m%dT000000Z")


def _first_weekly_occurrence(base_date: datetime, days: list[str]) -> datetime | None:
    """Earliest date on or after base_date falling on one of the given weekdays."""
    offsets = []
    for day in days:
        target = WEEKDAY_INDEX.get(day)
        if target is None:
            continue
        offsets.append((target - base_date.weekday()) % 7)
    if not offsets:
        return None
    return base_date + timedelta(days=min(offsets))


def _nth_weekday_of_month(year: int, month: int, weekday: int, nth: int) -> date | None:
    """Date of the nth (1-5, or -1 for last) given weekday in a month."""
    days_in_month = calendar.monthrange(year, month)[1]
    matches = [
        day for day in range(1, days_in_month + 1)
        if date(year, month, day).weekday() == weekday
    ]
    try:
        return date(year, month, matches[nth - 1 if nth > 0 else nth])
    except IndexError:
        return None


def _first_monthly_occurrence(
    base_date: datetime, days: list[str], weeks: list[int]
) -> datetime | None:
    """Earliest date on or after base_date matching any (week, weekday) pair.

    DTSTART must itself be a valid occurrence of the RRULE, otherwise calendar
    clients render an extra event on the DTSTART date. Walking forward month by
    month guarantees that; simply advancing to the next matching weekday does not.
    """
    year, month = base_date.year, base_date.month
    for _ in range(14):  # a year plus slack covers 5th-week rules that skip months
        candidates = []
        for day in days:
            weekday = WEEKDAY_INDEX.get(day)
            if weekday is None:
                continue
            for nth in weeks:
                found = _nth_weekday_of_month(year, month, weekday, nth)
                if found and found >= base_date.date():
                    candidates.append(found)
        if candidates:
            best = min(candidates)
            return datetime(best.year, best.month, best.day)
        month += 1
        if month > 12:
            month, year = 1, year + 1
    return None


def _end_day_offset(start_time: str, end_time: str) -> int:
    """Return 1 when an event's end clock time falls on the following day."""
    start_hour, start_minute = (int(part) for part in start_time.split(":"))
    end_hour, end_minute = (int(part) for part in end_time.split(":"))
    return int((end_hour, end_minute) <= (start_hour, start_minute))


def resolve_recurring_schedule(
    schedule: dict,
    entry: dict,
    today: date | None = None,
) -> dict | None:
    """Normalize a parsed recurring schedule for both ICS and JSON consumers.

    The returned anchor is itself a valid recurrence occurrence. Returning
    ``None`` means the schedule is too incomplete to publish, has an impossible
    window, or has already ended. Keeping that decision here prevents the web
    calendar and subscribed ICS feeds from interpreting the same source text
    differently.
    """
    if not (
        schedule.get("day")
        and schedule.get("start_time")
        and schedule.get("end_time")
    ):
        return None

    days = [day for day in schedule["day"].split(",") if day in WEEKDAY_INDEX]
    if not days:
        return None

    schedule_start = parse_date(entry.get("schedule_start_date"))
    base_date = (
        datetime(schedule_start.year, schedule_start.month, schedule_start.day)
        if schedule_start else CALENDAR_EPOCH
    )

    if schedule.get("last_of_month"):
        frequency = "monthly"
        month_weeks = [-1]
        first_occurrence = _first_monthly_occurrence(base_date, days, month_weeks)
    elif schedule.get("week_of_month"):
        frequency = "monthly"
        month_weeks = list(schedule["week_of_month"])
        first_occurrence = _first_monthly_occurrence(base_date, days, month_weeks)
    else:
        frequency = "weekly"
        month_weeks = []
        first_occurrence = _first_weekly_occurrence(base_date, days)

    if first_occurrence is None:
        return None

    schedule_end = parse_date(entry.get("schedule_end_date"))
    if schedule_end:
        if schedule_end < (today or date.today()):
            return None
        if schedule_end < first_occurrence.date():
            return None

    start_time = schedule["start_time"]
    end_time = schedule["end_time"]
    return {
        "type": "recurring",
        "frequency": frequency,
        "interval": max(1, int(schedule.get("interval", 1))),
        "weekdays": days,
        "month_weeks": month_weeks,
        "anchor_date": first_occurrence.date().isoformat(),
        "until_date": schedule_end.isoformat() if schedule_end else None,
        "start_time": start_time,
        "end_time": end_time,
        "end_day_offset": _end_day_offset(start_time, end_time),
    }


def resolve_fixed_schedule(
    dates: str | list,
    schedule: str | None = None,
    today: date | None = None,
) -> dict | None:
    """Normalize fixed dates, optionally applying a program's clock times.

    This mirrors ``_make_date_event``: only a single-day program occurrence is
    timed; date ranges and entry-level fixed dates remain all-day events.
    """
    date_items = [dates] if isinstance(dates, str) else dates
    if not isinstance(date_items, list):
        return None

    parsed_times = parse_schedule(schedule) if schedule else {}
    has_times = bool(parsed_times.get("start_time") and parsed_times.get("end_time"))
    occurrences = []
    for date_item in date_items:
        if not isinstance(date_item, str):
            continue
        start_date, end_date = parse_date_string(date_item, today=today)
        if not start_date:
            continue
        effective_end = end_date or start_date
        timed = has_times and start_date == effective_end
        start_time = parsed_times.get("start_time") if timed else None
        end_time = parsed_times.get("end_time") if timed else None
        occurrences.append({
            "start_date": start_date.date().isoformat(),
            "end_date": effective_end.date().isoformat(),
            "all_day": not timed,
            "start_time": start_time,
            "end_time": end_time,
            "end_day_offset": _end_day_offset(start_time, end_time) if timed else 0,
        })

    if not occurrences:
        return None
    return {"type": "fixed", "occurrences": occurrences}


def _effective_schedule_entry(entry: dict, program: dict) -> dict:
    """Return entry bounds with each program-level bound overriding its parent."""
    effective_entry = dict(entry)
    for key in ("schedule_start_date", "schedule_end_date"):
        if program.get(key):
            effective_entry[key] = program[key]
    return effective_entry


def _pacific_utc_offset(dt: datetime) -> int:
    """Hours to add to Pacific local time to get UTC (7 during PDT, 8 during PST).

    Implements the US rule the generated VTIMEZONE already declares - DST runs
    from the second Sunday in March to the first Sunday in November - so the
    result does not depend on the tzdata package being installed.
    """
    dst_start = _nth_weekday_of_month(dt.year, 3, 6, 2)   # 2nd Sunday in March
    dst_end = _nth_weekday_of_month(dt.year, 11, 6, 1)    # 1st Sunday in November
    if dst_start and dst_end and dst_start <= dt.date() < dst_end:
        return 7
    return 8


def _local_end_of_day_utc(day: datetime) -> str:
    """Format 23:59:59 Pacific on the given day as a UTC iCalendar timestamp."""
    local_end = day.replace(hour=23, minute=59, second=59, microsecond=0)
    return (local_end + timedelta(hours=_pacific_utc_offset(local_end))).strftime("%Y%m%dT%H%M%SZ")


def build_recurring_event(
    schedule: dict,
    entry: dict,
    summary: str,
    description: str,
    html_desc: str,
    location: str,
    uid: str,
    website: str,
    category: str,
    platform: str,
    dtstamp: str = None,
    today: date = None,
) -> str | None:
    """Build a recurring VEVENT from parsed schedule data. Returns None if schedule is incomplete."""
    resolved = resolve_recurring_schedule(schedule, entry, today=today)
    if not resolved:
        return None

    days = resolved["weekdays"]

    # Monthly rules use the "1WE"/"-1SU" BYDAY form rather than BYDAY + BYSETPOS.
    # BYSETPOS picks the Nth item out of the *combined* set, so "1st Tuesday and
    # 1st Saturday" written as BYDAY=TU,SA;BYSETPOS=1 collapses to whichever of
    # the two falls first in the month. Prefixed BYDAY values say what is meant.
    if resolved["month_weeks"] == [-1]:
        byday = ",".join(f"-1{d}" for d in days)
        rrule_parts = [f"FREQ=MONTHLY;BYDAY={byday}"]
    elif resolved["month_weeks"]:
        weeks = resolved["month_weeks"]
        byday = ",".join(f"{w}{d}" for d in days for w in weeks)
        rrule_parts = [f"FREQ=MONTHLY;BYDAY={byday}"]
    else:
        rrule_parts = [f"FREQ=WEEKLY;BYDAY={','.join(days)}"]

    if resolved["interval"] > 1:
        rrule_parts.append(f"INTERVAL={resolved['interval']}")

    first_occurrence = datetime.fromisoformat(resolved["anchor_date"])
    if resolved["until_date"]:
        end_date = datetime.fromisoformat(resolved["until_date"])
        # RFC 5545: when DTSTART carries a TZID, UNTIL must be a UTC timestamp.
        rrule_parts.append(f"UNTIL={_local_end_of_day_utc(end_date)}")

    rrule = ";".join(rrule_parts)

    start_time = resolved["start_time"].split(":")
    end_time = resolved["end_time"].split(":")

    dtstart = first_occurrence.replace(
        hour=int(start_time[0]), minute=int(start_time[1]), second=0, microsecond=0
    )
    dtend = first_occurrence.replace(
        hour=int(end_time[0]), minute=int(end_time[1]), second=0, microsecond=0
    )
    if resolved["end_day_offset"]:
        # Overnight session such as "12-12am" (noon to midnight)
        dtend += timedelta(days=1)

    return create_vevent(
        uid=uid,
        summary=summary,
        description=description,
        location=location,
        dtstart=format_ical_date(dtstart),
        dtend=format_ical_date(dtend),
        rrule=rrule,
        url=website,
        category=category,
        platform=platform,
        html_description=html_desc,
        dtstamp=dtstamp,
    )


_warned_schedules = set()

def _make_date_event(
    date_str: str, entry_id: str, name: str, description: str,
    html_desc: str, address: str, website: str, category: str, platform: str,
    times: dict | None = None, uid_suffix: str = "", dtstamp: str = None,
) -> str | None:
    """Create a VEVENT from a date string.

    All-day by default. When `times` carries a parsed start/end time (from a
    program's `schedule`), a timed single-day event is produced instead.
    """
    start_date, end_date = parse_date_string(date_str)
    if not start_date:
        return None
    end = end_date if end_date else start_date
    uid = generate_uid(entry_id, uid_suffix + start_date.strftime("%Y%m%d"))

    if times and times.get("start_time") and start_date == end:
        start_h, start_m = (int(x) for x in times["start_time"].split(":"))
        end_h, end_m = (
            (int(x) for x in times["end_time"].split(":")) if times.get("end_time") else (start_h + 1, start_m)
        )
        dtstart = start_date.replace(hour=start_h, minute=start_m)
        dtend = start_date.replace(hour=end_h, minute=end_m)
        if dtend <= dtstart:
            dtend += timedelta(days=1)
        return create_vevent(
            uid=uid,
            summary=name,
            description=description,
            location=address,
            dtstart=format_ical_date(dtstart),
            dtend=format_ical_date(dtend),
            url=website,
            category=category,
            platform=platform,
            html_description=html_desc,
            dtstamp=dtstamp,
        )

    return create_vevent(
        uid=uid,
        summary=name,
        description=description,
        location=address,
        dtstart=format_ical_date(start_date, all_day=True),
        dtend=format_ical_date(end + timedelta(days=1), all_day=True),
        all_day=True,
        url=website,
        category=category,
        platform=platform,
        html_description=html_desc,
        dtstamp=dtstamp,
    )


def _warn_unparseable(key: str, schedule_str: str, label: str) -> None:
    """Print a deduplicated warning for an unparseable schedule."""
    if key not in _warned_schedules:
        _warned_schedules.add(key)
        print(f"  WARNING: unparseable schedule for {label}: \"{schedule_str}\"", file=sys.stderr)


def has_scheduled_programs(programs) -> bool:
    """True if any program carries its own schedule or dates.

    An entry-level schedule is a fallback for entries whose programs are just a
    list of offerings. Suppressing it whenever `programs` is merely non-empty
    hid the entry's own schedule instead: portland-art-guild published nothing
    because three offering names sat alongside its schedule.
    """
    if not isinstance(programs, list):
        return False
    return any(
        isinstance(program, dict) and (program.get("schedule") or program.get("dates"))
        for program in programs
    )


def is_closed(entry: dict) -> bool:
    """True if the entry is recorded as permanently closed or discontinued."""
    if str(entry.get("status", "")).upper() == "CLOSED":
        return True
    return any("❌" in str(flag) for flag in entry.get("flags", []) or [])


def entry_to_events(entry: dict, platform: str = "google") -> list[str]:
    """Convert a source entry to one or more VEVENT strings."""
    events = []
    dtstamp = entry_dtstamp(entry)
    entry_id = entry.get("id", "unknown")
    name = entry.get("name", "Unnamed Event")
    category = entry.get("category", "general")
    address = entry.get("address", "")
    website = entry.get("website", "")

    # Date-based events (festivals, one-time occurrences)
    dates = entry.get("dates")
    if dates:
        description, html_desc = generate_event_description(entry)
        date_items = [dates] if isinstance(dates, str) else (dates if isinstance(dates, list) else [])
        for date_item in date_items:
            if isinstance(date_item, str):
                vevent = _make_date_event(
                    date_item, entry_id, name, description, html_desc,
                    address, website, category, platform, dtstamp=dtstamp,
                )
                if vevent:
                    events.append(vevent)

    # Recurring programs (sub-entries with their own schedules)
    programs = entry.get("programs", [])
    if isinstance(programs, list):
        for program in programs:
            if not isinstance(program, dict):
                continue
            program_name = program.get("name", name)
            program_key = program.get("id", program_name)
            full_name = f"{name}: {program_name}" if program_name != name else name

            # Programs with fixed dates (a touring series, a season of one-offs)
            program_dates = program.get("dates")
            if program_dates:
                description, html_desc = generate_event_description(entry, program)
                times = parse_schedule(program.get("schedule", "")) if program.get("schedule") else None
                date_items = [program_dates] if isinstance(program_dates, str) else program_dates
                for date_item in date_items:
                    if not isinstance(date_item, str):
                        continue
                    vevent = _make_date_event(
                        date_item, entry_id, full_name, description, html_desc,
                        program.get("location", address), website, category, platform,
                        times=times, uid_suffix=f"{program_key}-", dtstamp=dtstamp,
                    )
                    if vevent:
                        events.append(vevent)
                continue

            if "schedule" not in program:
                continue
            schedule = parse_schedule(program.get("schedule", ""))

            if program.get("schedule") and not schedule.get("day"):
                _warn_unparseable(f"{entry_id}>{program_name}", program["schedule"], f"{entry_id} > {program_name}")

            description, html_desc = generate_event_description(entry, program)

            # Merge program-level schedule bounds
            effective_entry = _effective_schedule_entry(entry, program)

            vevent = build_recurring_event(
                schedule=schedule, entry=effective_entry, summary=full_name,
                description=description, html_desc=html_desc,
                location=program.get("location", address),
                uid=generate_uid(entry_id, program_key),
                website=website, category=category, platform=platform,
                dtstamp=dtstamp,
            )
            if vevent:
                events.append(vevent)

    # Entry-level schedule, used when no program supplies its own timing
    schedule_str = entry.get("schedule")
    if schedule_str and not has_scheduled_programs(programs) and not dates:
        schedule = parse_schedule(schedule_str)
        if not schedule.get("day"):
            _warn_unparseable(entry_id, schedule_str, entry_id)
        description, html_desc = generate_event_description(entry)

        vevent = build_recurring_event(
            schedule=schedule, entry=entry, summary=name,
            description=description, html_desc=html_desc,
            location=address, uid=generate_uid(entry_id, "recurring"),
            website=website, category=category, platform=platform,
            dtstamp=dtstamp,
        )
        if vevent:
            events.append(vevent)

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
            header.append("X-APPLE-CALENDAR-COLOR:#3E56B5")

    elif platform == "outlook":
        header.append("X-WR-TIMEZONE:America/Los_Angeles")

    # Add VTIMEZONE for all platforms
    timezone = generate_vtimezone()

    footer = ["END:VCALENDAR"]

    # Combine: header + timezone + events + footer
    header_str = "\r\n".join(header)
    footer_str = "\r\n".join(footer)

    return header_str + "\r\n" + timezone + "\r\n" + "\r\n".join(events) + "\r\n" + footer_str


def generate_json_feed(entries: list[dict], today: date | None = None) -> dict:
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
            "latitude": entry.get("latitude"),
            "longitude": entry.get("longitude"),
            "phone": entry.get("phone"),
            "email": entry.get("email"),
            "website": entry.get("website"),
            "pricing": entry.get("pricing"),
            "hours": entry.get("hours"),
            "eligibility": entry.get("eligibility"),
            "features": entry.get("features", []),
            "location_type": entry.get("location_type"),
            "resource_type": entry.get("resource_type"),
            "programs": entry.get("programs", []),
            "dates": entry.get("dates"),
            "schedule": entry.get("schedule"),
            "schedule_start_date": entry.get("schedule_start_date"),
            "schedule_end_date": entry.get("schedule_end_date"),
            "resolved_schedule": None,
            "flags": entry.get("flags", []),
            "last_verified": entry.get("last_verified"),
            "accessibility": entry.get("accessibility", []),
            "social_intensity": entry.get("social_intensity"),
            "good_for": entry.get("good_for", []),
            "audience": get_entry_audience(entry),
            "audience_notes": entry.get("audience_notes"),
            "notes": entry.get("notes"),
            "practical_tips": entry.get("practical_tips"),
        }
        if entry.get("dates"):
            # Entry-level fixed dates are always all-day, matching ICS output.
            event_data["resolved_schedule"] = resolve_fixed_schedule(
                entry["dates"], today=today,
            )

        # Add detected audience to programs
        if event_data["programs"]:
            enriched_programs = []
            for prog in event_data["programs"]:
                if isinstance(prog, dict):
                    prog_copy = dict(prog)
                    prog_copy["audience"] = get_program_audience(prog, entry)
                    if prog.get("dates"):
                        prog_copy["resolved_schedule"] = resolve_fixed_schedule(
                            prog["dates"], prog.get("schedule"), today=today,
                        )
                    elif prog.get("schedule"):
                        prog_copy["resolved_schedule"] = resolve_recurring_schedule(
                            parse_schedule(prog["schedule"]),
                            _effective_schedule_entry(entry, prog),
                            today=today,
                        )
                    else:
                        prog_copy["resolved_schedule"] = None
                    enriched_programs.append(prog_copy)
                else:
                    # Program is just a string, skip enrichment
                    enriched_programs.append(prog)
            event_data["programs"] = enriched_programs
        if (
            entry.get("schedule")
            and not entry.get("dates")
            and not has_scheduled_programs(entry.get("programs"))
        ):
            event_data["resolved_schedule"] = resolve_recurring_schedule(
                parse_schedule(entry["schedule"]), entry, today=today,
            )
        events.append(event_data)

    # "As of" the newest verification date rather than the wall clock, so an
    # unchanged sources.yaml regenerates to an identical file.
    verified_dates = [d for d in (parse_date(e.get("last_verified")) for e in entries) if d]

    return {
        "schedule_schema_version": SCHEDULE_SCHEMA_VERSION,
        "generated": max(verified_dates).isoformat() if verified_dates else "",
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

    # Permanently closed resources stay in sources.yaml as a record, but must not
    # be published to calendars, the map, or the resources directory.
    closed = [e for e in entries if is_closed(e)]
    if closed:
        entries = [e for e in entries if not is_closed(e)]
        print(f"Excluding {len(closed)} closed entries: {', '.join(e.get('id', '?') for e in closed)}")

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
