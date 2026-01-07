#!/usr/bin/env python3
"""
Generate monthly calendar files by expanding recurring events.

This script reads the existing .ics files and creates month-specific
calendar files with expanded recurrence rules so users can import
just the months they need.

Usage:
    python generate_monthly_calendars.py
"""

import re
import os
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict


def parse_ical_date(date_str):
    """Parse iCal date string to datetime."""
    date_str = date_str.strip()
    if 'T' in date_str:
        # DateTime format: YYYYMMDDTHHMMSS
        return datetime.strptime(date_str.replace('Z', ''), '%Y%m%dT%H%M%S')
    else:
        # Date only format: YYYYMMDD
        return datetime.strptime(date_str, '%Y%m%d')


def format_ical_date(dt, all_day=False):
    """Format datetime for iCal."""
    if all_day:
        return dt.strftime('%Y%m%d')
    return dt.strftime('%Y%m%dT%H%M%S')


def parse_rrule(rrule_str):
    """Parse RRULE string into components."""
    parts = {}
    for part in rrule_str.split(';'):
        if '=' in part:
            key, value = part.split('=', 1)
            parts[key] = value
    return parts


def get_nth_weekday_of_month(year, month, weekday, n):
    """
    Get the nth occurrence of a weekday in a month.
    weekday: 0=Monday, 6=Sunday
    n: 1-5 for which occurrence (negative for from end)
    """
    from calendar import monthrange

    first_day = datetime(year, month, 1)
    last_day = monthrange(year, month)[1]

    if n > 0:
        # Count from start
        day = first_day
        count = 0
        while day.month == month:
            if day.weekday() == weekday:
                count += 1
                if count == n:
                    return day
            day += timedelta(days=1)
    else:
        # Count from end
        day = datetime(year, month, last_day)
        count = 0
        while day.month == month:
            if day.weekday() == weekday:
                count -= 1
                if count == n:
                    return day
            day -= timedelta(days=1)
    return None


def expand_weekly_rrule(start_dt, rrule, start_month, end_month):
    """Expand a weekly recurrence rule into specific dates."""
    occurrences = []
    parts = parse_rrule(rrule)

    byday = parts.get('BYDAY', '')
    day_map = {'SU': 6, 'MO': 0, 'TU': 1, 'WE': 2, 'TH': 3, 'FR': 4, 'SA': 5}
    target_weekday = day_map.get(byday, start_dt.weekday())

    # Start from the beginning of start_month
    current = datetime(start_month.year, start_month.month, 1,
                       start_dt.hour, start_dt.minute, start_dt.second)

    # Find the first occurrence of the target weekday
    while current.weekday() != target_weekday:
        current += timedelta(days=1)

    # Calculate the last day of end_month
    if end_month.month == 12:
        last_day_of_end_month = datetime(end_month.year, 12, 31, 23, 59, 59)
    else:
        last_day_of_end_month = datetime(end_month.year, end_month.month + 1, 1) - timedelta(seconds=1)

    # Generate occurrences until end of end_month
    while current <= last_day_of_end_month:
        occurrences.append(current)
        current += timedelta(weeks=1)

    return occurrences


def expand_monthly_rrule(start_dt, rrule, start_month, end_month):
    """Expand a monthly recurrence rule into specific dates."""
    occurrences = []
    parts = parse_rrule(rrule)

    byday = parts.get('BYDAY', '')
    bysetpos = parts.get('BYSETPOS', '')

    day_map = {'SU': 6, 'MO': 0, 'TU': 1, 'WE': 2, 'TH': 3, 'FR': 4, 'SA': 5}
    target_weekday = day_map.get(byday, 0)

    positions = [int(p) for p in bysetpos.split(',')] if bysetpos else [1]

    # Iterate through months
    current_month = start_month
    while current_month <= end_month:
        for pos in positions:
            date = get_nth_weekday_of_month(
                current_month.year, current_month.month,
                target_weekday, pos
            )
            if date:
                dt = date.replace(
                    hour=start_dt.hour,
                    minute=start_dt.minute,
                    second=start_dt.second
                )
                occurrences.append(dt)

        # Move to next month
        if current_month.month == 12:
            current_month = datetime(current_month.year + 1, 1, 1)
        else:
            current_month = datetime(current_month.year, current_month.month + 1, 1)

    return occurrences


def parse_vevent(event_text):
    """Parse a VEVENT block into a dictionary."""
    event = {}
    lines = []

    # Handle line folding (continuation lines start with space)
    for line in event_text.split('\n'):
        line = line.rstrip('\r')
        if line.startswith(' ') or line.startswith('\t'):
            if lines:
                lines[-1] += line[1:]
        else:
            lines.append(line)

    for line in lines:
        if ':' in line:
            # Handle property parameters (e.g., DTSTART;VALUE=DATE:20250101)
            if ';' in line.split(':')[0]:
                prop_part = line.split(':')[0]
                value = ':'.join(line.split(':')[1:])
                prop = prop_part.split(';')[0]
            else:
                prop = line.split(':')[0]
                value = ':'.join(line.split(':')[1:])
            event[prop] = value

    return event


def create_vevent_from_occurrence(original_event, occurrence_dt, uid_suffix, all_day=False):
    """Create a VEVENT string for a specific occurrence."""
    lines = ['BEGIN:VEVENT']

    # Generate unique UID for this occurrence
    base_uid = original_event.get('UID', 'unknown')
    lines.append(f"UID:{base_uid.replace('@', f'-{uid_suffix}@')}")

    lines.append(f"DTSTAMP:{format_ical_date(datetime.now())}Z")

    # Calculate duration from original event
    if 'DTEND' in original_event and 'DTSTART' in original_event:
        orig_start = parse_ical_date(original_event['DTSTART'])
        orig_end = parse_ical_date(original_event['DTEND'])
        duration = orig_end - orig_start
    else:
        duration = timedelta(hours=1)

    end_dt = occurrence_dt + duration

    if all_day:
        lines.append(f"DTSTART;VALUE=DATE:{format_ical_date(occurrence_dt, True)}")
        lines.append(f"DTEND;VALUE=DATE:{format_ical_date(end_dt, True)}")
    else:
        lines.append(f"DTSTART:{format_ical_date(occurrence_dt)}")
        lines.append(f"DTEND:{format_ical_date(end_dt)}")

    # Copy other properties (but not RRULE)
    skip_props = {'UID', 'DTSTAMP', 'DTSTART', 'DTEND', 'RRULE'}
    for prop, value in original_event.items():
        if prop not in skip_props and prop not in ('BEGIN', 'END'):
            # Re-fold long lines
            line = f"{prop}:{value}"
            if len(line) > 75:
                folded = []
                while len(line) > 75:
                    folded.append(line[:75])
                    line = ' ' + line[75:]
                folded.append(line)
                lines.append('\r\n'.join(folded))
            else:
                lines.append(line)

    lines.append('END:VEVENT')
    return '\r\n'.join(lines)


def extract_events(ics_content):
    """Extract all VEVENT blocks from ICS content."""
    events = []
    in_event = False
    current_event = []

    for line in ics_content.split('\n'):
        line = line.rstrip('\r')
        if line == 'BEGIN:VEVENT':
            in_event = True
            current_event = [line]
        elif line == 'END:VEVENT':
            current_event.append(line)
            events.append('\n'.join(current_event))
            in_event = False
            current_event = []
        elif in_event:
            current_event.append(line)

    return events


def extract_header(ics_content):
    """Extract the calendar header (everything before first VEVENT)."""
    lines = []
    for line in ics_content.split('\n'):
        line = line.rstrip('\r')
        if line == 'BEGIN:VEVENT':
            break
        lines.append(line)
    return '\r\n'.join(lines)


def group_events_by_month(events, months_ahead=12):
    """
    Group events by month, expanding recurring events.
    Returns dict: {(year, month): [event_strings]}
    """
    today = datetime.now()
    start_month = datetime(today.year, today.month, 1)

    # Calculate end month
    end_year = today.year
    end_month_num = today.month + months_ahead
    while end_month_num > 12:
        end_month_num -= 12
        end_year += 1
    end_month = datetime(end_year, end_month_num, 1)

    events_by_month = defaultdict(list)

    for event_text in events:
        event = parse_vevent(event_text)

        if not event.get('DTSTART'):
            continue

        start_dt = parse_ical_date(event['DTSTART'])
        all_day = 'VALUE=DATE' in event_text.split('DTSTART')[1].split('\n')[0] if 'DTSTART' in event_text else False

        rrule = event.get('RRULE')

        if rrule:
            # Expand recurring event
            parts = parse_rrule(rrule)
            freq = parts.get('FREQ', '')

            if freq == 'WEEKLY':
                occurrences = expand_weekly_rrule(start_dt, rrule, start_month, end_month)
            elif freq == 'MONTHLY':
                occurrences = expand_monthly_rrule(start_dt, rrule, start_month, end_month)
            else:
                occurrences = [start_dt]

            for i, occ in enumerate(occurrences):
                month_key = (occ.year, occ.month)
                event_str = create_vevent_from_occurrence(event, occ, f"occ{i}", all_day)
                events_by_month[month_key].append(event_str)
        else:
            # Single event - just check if it's in our range
            if start_month <= datetime(start_dt.year, start_dt.month, 1) <= end_month:
                month_key = (start_dt.year, start_dt.month)
                events_by_month[month_key].append(event_text.replace('\n', '\r\n'))

    return events_by_month


def create_monthly_calendar(header, events, month_name):
    """Create a complete calendar for a specific month."""
    # Update calendar name in header
    header_lines = header.split('\r\n')
    new_header_lines = []
    for line in header_lines:
        if line.startswith('X-WR-CALNAME:'):
            new_header_lines.append(f"X-WR-CALNAME:Portland Resources - {month_name}")
        else:
            new_header_lines.append(line)

    header = '\r\n'.join(new_header_lines)

    content = header + '\r\n'
    for event in events:
        content += event + '\r\n'
    content += 'END:VCALENDAR'

    return content


def main():
    script_dir = Path(__file__).parent
    project_dir = script_dir.parent
    distribution_dir = project_dir / 'distribution'

    platforms = {
        'apple': 'Apple Calendar',
        'google': 'Google Calendar',
        'outlook': 'Outlook'
    }

    month_names = {
        1: 'January', 2: 'February', 3: 'March', 4: 'April',
        5: 'May', 6: 'June', 7: 'July', 8: 'August',
        9: 'September', 10: 'October', 11: 'November', 12: 'December'
    }

    for platform_key, platform_name in platforms.items():
        source_file = project_dir / 'output' / platform_key / 'all-events.ics'
        output_dir = distribution_dir / platform_name / 'By Month'

        if not source_file.exists():
            print(f"Warning: {source_file} not found, skipping {platform_name}")
            continue

        print(f"Processing {platform_name}...")

        with open(source_file, 'r', encoding='utf-8') as f:
            content = f.read()

        header = extract_header(content)
        events = extract_events(content)
        print(f"  Found {len(events)} events")

        events_by_month = group_events_by_month(events, months_ahead=12)

        for (year, month), month_events in sorted(events_by_month.items()):
            if not month_events:
                continue

            month_name = f"{month_names[month]} {year}"
            calendar = create_monthly_calendar(header, month_events, month_name)

            output_file = output_dir / f"{month_name}.ics"
            with open(output_file, 'w', encoding='utf-8', newline='') as f:
                f.write(calendar)

            print(f"  Created {month_name}.ics ({len(month_events)} events)")

    print("\nMonthly calendars generated successfully!")


if __name__ == '__main__':
    main()
