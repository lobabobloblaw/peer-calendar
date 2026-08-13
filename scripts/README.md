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
- `output/events.json` - JSON feed for web applications (if --json flag used), including versioned `resolved_schedule` data shared with the browser

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

### check_source_urls.py

Checks every unique `source_urls` value with bounded concurrency, per-host
limits, timeouts, retries, safe redirect detection, and a `HEAD` to `GET`
fallback. Redirect destinations are not fetched automatically; they are flagged
for browser verification.
It deliberately separates confirmed broken links from sites that block bots:
HTTP 403/429 responses, JavaScript challenges, temporary server errors, and
network failures are warnings that need human follow-up rather than hard
failures.

**Usage:**
```bash
# Concise console summary (informational exit code)
python check_source_urls.py

# Also write machine-readable JSON and a Markdown summary
python check_source_urls.py \
  --output ../artifacts/source-url-report.json \
  --markdown-output ../artifacts/source-url-summary.md

# Opt in to exit code 1 when confirmed broken links are present
python check_source_urls.py --fail-on-broken

# Run deterministic tests; these never contact live websites
python test_check_source_urls.py
```

The `Check Source URLs` GitHub Actions workflow runs the mocked test suite on
pull requests. After merge, it performs an informational live check each
Wednesday and whenever source data changes. It publishes the summary in the
workflow run and retains the full JSON report as an artifact for 30 days. The
live step is initially non-blocking even when it finds confirmed broken links.

### Audit workload and cadence policy

Audit cadence measures how often a human should re-check content; automated URL
reachability is only a separate maintenance signal. Review the sustainable load
and a consequence-aware queue with:

```bash
python audit_check.py --workload --capacity-per-week 5
python audit_check.py --workload --as-of 2026-08-13 --format json
```

The queue prioritizes explicit VERIFY flags, essential peer/basic-needs access,
discounts and transportation, and open-ended recurring schedules. Monthly and
quarterly cadences are retained for volatile schedules and rotating catalogs;
stable facilities, bounded annual events, and general descriptions can be
annual. A cadence migration must never update `last_verified`, because it is
policy maintenance rather than evidence of content verification. Earlier
`next_audit` dates may be preserved for TBA announcements or unresolved work.

`migrate_audit_cadence.py` records the reviewed issue #5 migration. It previews
by default; `--apply` writes the exact 53-entry migration and validates that no
`last_verified` value changed.

Retiering reduces low-value repetition but does not by itself make a five-audit
weekly capacity sustainable: the active corpus still projects above that rate,
and even one annual human review per active entry exceeds five per week. Use
the workload report to make that limitation explicit; do not interpret this
migration as closing the capacity question.

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
├── check_source_urls.py
├── test_check_source_urls.py
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

The scripts use standard Python 3.13+ features and depend on PyYAML and python-dateutil. Calendar generation uses the iCal standard (RFC 5545) for maximum compatibility.

To add schedule parsing logic, update `parse_schedule()` and the canonical resolver in `generate_calendar.py`, then extend both `test_schedule_parsing.py` and `test_web_schedule_parity.mjs`. The browser consumes `resolved_schedule`; it must not add a second natural-language parser.
