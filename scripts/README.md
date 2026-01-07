# Scripts for Portland Metro Resources

This directory contains Python scripts for managing the resource database and generating calendar feeds.

## Setup

```bash
cd scripts
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Scripts

### generate_calendar.py

Generates iCal/ICS calendar feeds from `sources.yaml`. These calendars can be imported into Google Calendar, Apple Calendar, Outlook, or any calendar application that supports .ics files.

**Usage:**
```bash
# Generate all calendar files
python generate_calendar.py

# Generate with JSON feed for web apps
python generate_calendar.py --json

# Generate specific category only
python generate_calendar.py --category peer_support

# Custom output directory
python generate_calendar.py --output ./my-calendars
```

**Output:**
- `output/peer_support.ics` - Mental health and peer support events
- `output/events.ics` - Festivals, art walks, seasonal events
- `output/fitness_wellness.ics` - Yoga, running groups, etc.
- `output/all-events.ics` - Combined calendar with everything
- `output/events.json` - JSON feed for web applications (if --json flag used)

**Calendar Features:**
- Recurring events with proper iCal RRULE support (weekly, monthly, etc.)
- All-day events for festivals and multi-day events
- Location data for map integration
- URLs to official websites
- Category filtering

### audit_check.py

Analyzes `sources.yaml` and reports entries due for verification, data quality issues, and statistics.

**Usage:**
```bash
# Full audit report
python audit_check.py

# Show only entries due this month
python audit_check.py --due-this-month

# Show only unverified entries
python audit_check.py --unverified

# Filter by category
python audit_check.py --category peer_support

# Run data quality check
python audit_check.py --quality
```

**Report Includes:**
- Category statistics
- Entries due for audit this month
- Entries due next month
- Unverified entries needing official sources
- Data quality issues (missing fields, etc.)
- Summary statistics

## Integrating Calendars

### Google Calendar
1. Go to Google Calendar Settings
2. Click "Add calendar" → "From URL"
3. Paste the URL to your hosted .ics file
4. Calendar will auto-update periodically

### Apple Calendar
1. File → New Calendar Subscription
2. Enter the URL to your .ics file
3. Set refresh frequency

### Outlook
1. Add calendar → From internet
2. Enter the .ics file URL
3. Subscribe to the calendar

### Web Hosting
For auto-updating calendars, host the .ics files on a web server:
- GitHub Pages
- Any static file host
- Your own server

Then use the hosted URL instead of local files.

## Directory Structure

```
scripts/
├── README.md           # This file
├── requirements.txt    # Python dependencies
├── venv/               # Virtual environment (created by setup)
├── generate_calendar.py
└── audit_check.py

output/                 # Generated calendar files
├── peer_support.ics
├── events.ics
├── fitness_wellness.ics
├── all-events.ics
└── events.json
```

## Development

The scripts use standard Python 3.13+ features and depend only on PyYAML for parsing the source data. Calendar generation uses the iCal standard (RFC 5545) for maximum compatibility.

To add new event parsing logic, modify the `parse_schedule()` and `entry_to_events()` functions in `generate_calendar.py`.
