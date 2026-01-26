# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A living database of free and low-cost activities, services, and resources for adults in the Portland metro area, with special focus on accessibility for peer support programs and mental health communities.

**Purpose:** Maintain accurate, up-to-date resource guides for FolkTime's peer support programs. The guides serve people on limited incomes, including those living with mental health conditions.

**Primary Goal:** Serve accurate events in iCal/ICS format compatible with Google Calendar, Apple Calendar, Outlook, and other calendar platforms.

## Quick Status Check

Run `python scripts/audit_check.py` to see current database status, entries due for audit, and statistics.

## Architecture

**Source of truth:** `data/sources.yaml` contains all resource entries with verification metadata. The markdown guides in `guides/` are generated/updated from this data.

**Data flow:**
1. Research → add/update entry in `sources.yaml`
2. Update corresponding section in `guides/*.md`
3. Log the change in `data/audit-log.yaml`
4. Run `python scripts/generate_calendar.py` to update calendar feeds

**Key files:**
- `data/sources.yaml` - Master registry with ~213 resources and audit metadata (multi-document YAML with `---` separators)
- `docs/events.json` - JSON feed used by web calendar preview (generated from sources.yaml)
- `data/audit-log.yaml` - Verification history
- `data/queue.yaml` - Pending resources to research
- `guides/activities-guide-1.md` - Parks, arts, libraries, discount programs
- `guides/activities-guide-2.md` - U-pick farms, community centers, peer support
- `templates/resource-entry.yaml` - Template for new entries

**Scripts (require Python 3.13+ with PyYAML, python-dateutil):**
- `scripts/generate_calendar.py` - Generates iCal/ICS calendar feeds to `output/`
- `scripts/generate_monthly_calendars.py` - Expands recurring events into month-specific calendars in `distribution/`
- `scripts/audit_check.py` - Reports entries due for audit, unverified entries, statistics
- `scripts/audit_complete.py` - Mark entries as audited, auto-updates dates and logs
- `scripts/deduplicate_entries.py` - Merge duplicate entries in sources.yaml
- `scripts/add_type_fields.py` - Migration script for adding location_type/resource_type fields
- `scripts/add_audience_fields.py` - Migration script for adding audience tags
- `scripts/requirements.txt` - Python dependencies (pyyaml, python-dateutil)
- `scripts/venv/` - Virtual environment

**Templates:**
- `templates/resource-entry.yaml` - Template for new database entries
- `templates/audit-report.md` - Template for quarterly audit reports

**Output files (platform-specific calendars):**
```
output/                    # Raw generated calendars (recurring events)
├── google/
├── apple/
├── outlook/
└── events.json

distribution/              # User-ready files (recurring events expanded by month)
├── START HERE - README.txt
├── calendars.zip          # All calendars zipped for easy sharing
├── Apple Calendar/
│   ├── HOW TO IMPORT - READ FIRST.txt
│   ├── Full Schedule/     # Category-specific calendars
│   └── By Month/          # Month-specific calendars (Dec 2025 - Dec 2026)
├── Google Calendar/
│   └── [same structure]
└── Outlook/
    └── [same structure]
```

**Category colors (for Apple Calendar):**
- Peer Support: #7B68EE (Medium slate blue)
- Fitness & Wellness: #32CD32 (Lime green)
- Events: #FF6347 (Tomato red)
- Arts & Culture: #9370DB (Medium purple)
- Parks & Nature: #228B22 (Forest green)
- Food & Farms: #DAA520 (Goldenrod)
- Social Activities: #FF69B4 (Hot pink)
- Discount Programs: #4169E1 (Royal blue)
- Transportation: #708090 (Slate gray)

## Core Workflows

### 1. Audit Existing Resources

Run periodically to verify resource accuracy. Use `audit_check.py` to identify what needs attention:

```bash
python scripts/audit_check.py              # Full report with statistics
python scripts/audit_check.py --due-this-month  # Entries due now
python scripts/audit_check.py --due-next-month  # Preview next month
python scripts/audit_check.py --unverified      # Entries needing official sources
python scripts/audit_check.py --quality         # Data quality issues
python scripts/audit_check.py --category peer_support  # Filter by category
```

**Audit process:**
1. Review `data/sources.yaml` for entries due this period
2. Fetch source URLs and verify: pricing, hours, addresses, phone numbers, eligibility
3. Update the entry's `last_verified` and `next_audit` dates
4. If changes found, update both `sources.yaml` AND the corresponding guide
5. Log the audit in `data/audit-log.yaml`

**Audit frequencies:**
- `weekly`: Event calendars, schedules for current month
- `monthly`: Pricing, hours, seasonal programs
- `quarterly`: Contact info, eligibility requirements, program details
- `annually`: Addresses, general descriptions, stable policies

**Weekly audit workflow (15-30 min):**

1. **Start your session:**
   ```bash
   source scripts/venv/bin/activate
   python scripts/audit_check.py --weekly-summary
   ```

2. **Work through entries in priority order:**
   - Overdue entries first (shown with days overdue)
   - Then entries due this week
   - Monthly-frequency entries take priority over quarterly/annual

3. **For each entry:**
   - Open the source URL(s) shown in the output
   - Verify: pricing, hours/schedule, address, phone, still operating
   - If **no changes**: `python scripts/audit_complete.py --id entry-id`
   - If **changes found**: Update `sources.yaml`, then run:
     `python scripts/audit_complete.py --id entry-id --changes "Brief description"`

4. **End of session:**
   - Run `python scripts/audit_check.py --overdue` to confirm none remain
   - If schedule changes were made, regenerate calendars:
     ```bash
     python scripts/generate_calendar.py --json --publish
     ```

**Quick reference - audit_check.py flags:**
- `--weekly-summary`: Best for weekly check-ins (shows overdue + due this week)
- `--overdue`: Show only overdue entries
- `--due-this-week`: Show entries due in next 7 days
- `--due-this-month`: Show all entries due this month
- `--category peer_support`: Filter by category

### 2. Add New Resources

When adding a new resource:

1. Research thoroughly - verify via official sources
2. Add entry to `data/sources.yaml` using the template format
3. Add content to appropriate guide in `guides/`
4. Log addition in `data/audit-log.yaml`

**Required fields for new entries:**
- `name`: Official name
- `category`: One of the defined categories
- `location_type`: One of: `physical`, `virtual`, `hybrid`, `online_service`, `varies`
- `resource_type`: One of: `place`, `event`, `service`, `program`, `organization`
- `address`: Full street address if physical location
- `phone`: Primary contact number
- `website`: Official URL
- `source_urls`: List of URLs used to verify info
- `pricing`: Cost details, discount programs accepted
- `hours`: Operating hours or schedule
- `last_verified`: Date of research
- `next_audit`: Based on data volatility
- `guide_location`: Which guide and approximate section

**Enrichment fields (for peer specialists):**
- `practical_tips`: First-visit tips, registration process, what to bring, insider knowledge
- `accessibility`: Standardized tags (see list below)
- `accessibility_notes`: Free-text details about accessibility
- `social_intensity`: `solo` | `drop_in` | `casual_group` | `structured_group` | `one_on_one`
- `good_for`: Standardized tags (see list below)
- `audience`: Standardized tags for who the resource targets (see list below)
- `audience_notes`: Free-text details about audience/eligibility

**Location types:**
- `physical`: Has a specific address where people go in person
- `virtual`: Meetings/events happen online only (Zoom, etc.)
- `hybrid`: Offers both in-person and virtual options
- `online_service`: Service accessed entirely online (utility discounts, warmline)
- `varies`: Location depends on which program/event (e.g., citywide discount programs)

**Resource types:**
- `place`: Physical location to visit (parks, museums, community centers)
- `event`: Time-bound occurrence with specific dates (festivals, holiday events)
- `service`: Ongoing assistance or benefit (discount programs, meals, crisis lines)
- `program`: Recurring activities with schedules (support groups, yoga classes)
- `organization`: Entity that offers multiple programs/services (NAMI, YMCA)

**Accessibility tags** (standardized list):
- `wheelchair_accessible`: Building/facility is wheelchair accessible
- `transit_nearby`: Within 5 min walk of bus/MAX stop
- `elevator`: Multi-story building has elevator
- `asl_available`: ASL interpretation available
- `hearing_loop`: Hearing loop system installed
- `scent_free`: Scent-free policy in place
- `low_vision_friendly`: Large print, audio descriptions, etc.
- `gender_neutral_restroom`: Gender-neutral restroom available
- `sliding_scale`: Sliding scale fees available

**Social intensity levels**:
- `solo`: Do alone (parks, trails, museums)
- `drop_in`: Come and go, minimal interaction required
- `casual_group`: Social but unstructured (craft nights, walking groups)
- `structured_group`: Facilitated, expected participation (support groups)
- `one_on_one`: Individual appointments/services

**Good-for tags** (standardized list):
- `anxiety_friendly`: Quiet, low-pressure, can leave easily
- `grief`: Appropriate for those experiencing grief
- `isolation`: Good for reconnecting with community
- `new_to_area`: Welcoming to newcomers
- `low_energy`: Doesn't require much physical/mental effort
- `active`: Physical activity involved
- `creative`: Art, writing, music activities
- `outdoor`: Takes place outdoors
- `indoor`: Takes place indoors
- `family_friendly`: Appropriate for families with children

**Audience tags** (for resources targeting specific groups):
- `children`: Ages 3-12
- `teens`: Ages 13-17
- `young_adults`: Ages 18-35
- `seniors`: Ages 55+/62+/65+
- `women`: Women-only spaces
- `lgbtq`: LGBTQ+ community
- `trans_nonbinary`: Trans, nonbinary, gender-diverse
- `bipoc`: Black, Indigenous, People of Color
- `spanish_speaking`: Spanish-language services

Note: Resources without an `audience` field are open to all adults. Programs within an entry can have their own `audience` field to specify program-specific demographics.

### 3. Generate Updated Guides

After audits or additions, regenerate the markdown guides from the source data to ensure consistency.

### 4. Quarterly Summary

Generate a summary of:
- Resources verified this quarter
- Changes detected
- New resources added
- Resources flagged as closed/changed
- Upcoming high-priority audits

## Data Categories

- `parks_nature`: Parks, trails, natural areas, gardens
- `arts_culture`: Museums, galleries, theaters, libraries
- `fitness_wellness`: Community centers, yoga, recreation
- `food_farms`: U-pick, farmers markets, community meals
- `events`: Festivals, seasonal events, recurring community events
- `peer_support`: Mental health groups, support meetings
- `social_activities`: Crafts, writing groups, volunteer opportunities
- `discount_programs`: Transit, utilities, access programs
- `transportation`: Transit options, bike programs

## Key Sources to Monitor

These URLs change frequently and should be checked monthly:

- portland.gov/parks - Programs, schedules, pricing
- trimet.org/fares - Low-income fare program
- namimultnomah.org - Support group schedules
- multcolib.org/events-classes - Library programs
- shift2bikes.org/calendar - Bike events
- portlandfarmersmarket.org - Market schedules

## Style Guidelines

When writing guide content:
- Lead with the most useful information (cost, address, eligibility)
- Use tables for comparative information
- Include transit access where relevant
- Note accessibility features
- Mention quieter times for those with social anxiety
- Always include phone numbers for those without internet access
- Verify SNAP/EBT acceptance explicitly - don't assume

## Flags and Alerts

Mark entries with:
- `⚠️ VERIFY` - Conflicting information found
- `🔄 SEASONAL` - Only available part of year
- `📅 DATE-SENSITIVE` - Event with specific dates
- `❌ CLOSED` - Confirmed permanently closed
- `❓ UNVERIFIED` - Added but not yet verified via official source

## Quick Start Commands

```bash
# Activate the Python environment (from project root)
source scripts/venv/bin/activate

# Check what's due for audit
python scripts/audit_check.py

# Weekly audit workflow
python scripts/audit_check.py --weekly-summary    # Start here for weekly check-ins
python scripts/audit_check.py --overdue           # Show overdue entries
python scripts/audit_check.py --due-this-week     # Show entries due in 7 days

# Mark an entry as audited (auto-updates dates and logs)
python scripts/audit_complete.py --id entry-id                    # No changes found
python scripts/audit_complete.py --id entry-id --changes "desc"   # Changes were made
python scripts/audit_complete.py --id entry-id --preview          # Preview without writing

# Generate calendar files for all platforms
python scripts/generate_calendar.py --json

# Generate and publish to GitHub Pages
python scripts/generate_calendar.py --json --publish

# Generate for specific platform only
python scripts/generate_calendar.py --platform google
python scripts/generate_calendar.py --platform apple
python scripts/generate_calendar.py --platform outlook

# Generate specific category
python scripts/generate_calendar.py --category peer_support

# Use custom paths (both scripts support these)
python scripts/generate_calendar.py --sources /path/to/sources.yaml --output ./my-calendars
python scripts/audit_check.py --sources /path/to/sources.yaml

# Deduplicate entries (preview mode - no changes)
python scripts/deduplicate_entries.py --preview

# Deduplicate entries (writes to sources-deduped.yaml for review)
python scripts/deduplicate_entries.py

# Generate monthly calendars (expands recurring events for distribution)
python scripts/generate_monthly_calendars.py
```

## GitHub Pages Hosting

Calendars are hosted via GitHub Pages for public subscription access.

**Live URL:** https://lobabobloblaw.github.io/peer-calendar/

**Subscription URLs:**
- All events: `https://lobabobloblaw.github.io/peer-calendar/apple/all-events.ics`
- By category: `https://lobabobloblaw.github.io/peer-calendar/apple/peer_support.ics`
- Replace `apple` with `google` or `outlook` for platform-specific versions

**Landing page features:**
- Title: "2026 Peer Support Calendar for the Multnomah Tri-County Region"
- Contact: alex.voigt@folktime.org
- Responsive two-column layout on desktop (768px+), single-column on mobile
- Platform selector (Apple/Google/Outlook) with inline "Subscribe:" label
- Inline calendar preview with three view tabs:
  - **Calendar**: Monthly grid view with events on their dates
  - **List**: Chronological list of events for the month
  - **Seasonal Events**: Festivals, fairs, and date-ranged events (not recurring)
- Weather-reactive animated background (Vanta.js clouds):
  - Time of day: Dawn (pink/peach), Day (sky blue), Dusk (purple/orange), Night (navy)
  - Weather conditions via Open-Meteo API: Clear skies show subtle clouds, overcast/rain darkens sky
  - Gracefully falls back to time-based defaults if API unavailable
- Adaptive text styling for left panel (subscribe instructions, updates):
  - Night/dark: White text with subtle dark shadow
  - Day/light: Dark text with subtle light shadow for depth
  - Body class `daytime` toggles based on time of day from weather API
- Updates section for announcing new content
- Print functionality with date range selection dialog:
  - Users can select start/end dates (minimum: January 1, 2026)
  - Disclaimer about event accuracy included in print output
  - Compact layout optimized for paper

**Publishing workflow:**
```bash
# Generate calendars and copy to docs/ for hosting
python scripts/generate_calendar.py --json --publish

# Commit and push to update live site
git add docs/
git commit -m "Update calendar feeds"
git push
```

The `docs/` folder contains:
- `index.html` - Landing page with subscription links and calendar preview (~3500 lines)
  - Vanta.js for animated cloud background
  - Open-Meteo API for weather-reactive theming
  - Key JavaScript functions:
    - `parseSchedule()` - Parses schedule strings into day/time components
    - `isMonthInSeasonalRange()` - Filters events by season keywords and month ranges
    - `generateMonthEvents()` - Creates event list for calendar display
    - `printCalendar()` - Generates print-optimized output with date range
  - Event modal display system
  - Print dialog with date range selection
- `apple/`, `google/`, `outlook/` - Platform-specific ICS files
- `events.json` - JSON feed for programmatic access and web calendar preview
- `folktime.png`, `2026-calendar-2.png` - Logo and header images

## Calendar Import Instructions

**Google Calendar:**
1. Go to Settings > Add calendar > From URL
2. Paste the subscription URL (see above)
3. Note: Colors and categories are not supported on import

**Apple Calendar:**
1. Settings > Calendar > Accounts > Add Account > Other > Add Subscribed Calendar
2. Paste the subscription URL
3. Category colors will appear automatically

**Outlook:**
1. Add calendar > Subscribe from web
2. Paste the subscription URL
3. HTML descriptions with clickable links will display

## YAML Structure Notes

`sources.yaml` uses multi-document YAML format with `---` separators between category sections. When parsing:
```python
# Correct way to load sources.yaml
for doc in yaml.safe_load_all(content):
    if doc and isinstance(doc, list):
        entries.extend(doc)
```

Schedule strings are parsed with natural language patterns:
- "Every Tuesday 6-7pm" → weekly recurring on Tuesdays
- "1st and 3rd Wednesday 2-3:30pm" → monthly on specific week positions
- "Tue/Thu 8-9am" or "Tuesdays & Thursdays noon-1pm" → multiple days per week
- "Last Sunday of each month 4-6pm" → last occurrence of day in month
- "Daily 2-10pm" → every day
- Time parsing handles: "2-10pm" (both PM), "10-7pm" (AM to PM), "noon-1pm", "10am"
- The `parseSchedule()` function in `docs/index.html` handles the web calendar preview
- The `parse_schedule()` function in `generate_calendar.py` handles ICS generation

**Delaying recurring events:**
Use `schedule_start_date` to prevent a recurring event from appearing until a specific date:
```yaml
- id: example-group
  name: Example Support Group
  schedule: Every Friday 6-7pm
  schedule_start_date: 2026-02-01  # Won't appear in calendars until February
```
This is useful when a program is on hiatus or hasn't started yet. The field is respected by both the ICS calendar generation and the web calendar preview.

**One-time events vs recurring events:**
**Important:** Use `dates` for specific event dates, not `dates_2026` or other year-suffixed variants. The calendar scripts only recognize the `dates` field.

Entries with a `dates` field (e.g., "July 18-19, 2026") are treated as one-time events:
- They appear ONLY in the "Seasonal Events" tab
- They do NOT generate recurring calendar entries
- Use `dates` for festivals, fairs, and specific-date events

```yaml
- id: portland-pride
  name: Portland Pride
  dates: "July 18-19, 2026"  # One-time event - won't show as recurring
  schedule: "Sat noon-8pm, Sun 11:30am-6pm"  # Schedule is for display only
```

**Seasonal filtering:**
The web calendar automatically filters events based on seasonal keywords in schedule/notes:
- `summer` → Only shows June-August
- `winter` → Only shows December-February
- `spring` → Only shows March-May
- `fall`/`autumn` → Only shows September-November
- Month ranges like "June-August" or "May-October" are also recognized

Example: An entry with notes "Free outdoor summer concert series" will only appear in summer months.

## Known Issues

**iOS Safari safe area background mismatch:**
On iOS Safari, the status bar (top) and home indicator (bottom) safe areas may show a different color than the animated sky background when scrolling. This is a known iOS limitation with fixed-position elements using negative z-index. Current mitigations in place:
- `theme-color` meta tag (dynamically updated to match sky)
- `viewport-fit=cover` meta tag
- `apple-mobile-web-app-status-bar-style` meta tag
- `background-color` on `#sky-bg` element

A future iOS update (possibly iOS 26.2+) may resolve this, as the underlying WebKit bug has been marked resolved. See [Ben Frain's article](https://benfrain.com/ios26-safari-theme-color-tab-tinting-with-fixed-position-elements/) for details.

## Ongoing Work

Check `data/queue.yaml` for pending research items and `data/audit-log.yaml` for recent changes.

Future improvements:
- Guide regeneration from sources.yaml (guides are currently manually maintained)
- Enrichment data population (practical_tips, accessibility, social_intensity, good_for)
