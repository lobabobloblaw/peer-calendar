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
- `data/sources.yaml` - Master registry with ~90 resources and audit metadata (multi-document YAML with `---` separators)
- `data/audit-log.yaml` - Verification history
- `data/queue.yaml` - Pending resources to research
- `guides/activities-guide-1.md` - Parks, arts, libraries, discount programs
- `guides/activities-guide-2.md` - U-pick farms, community centers, peer support
- `templates/resource-entry.yaml` - Template for new entries

**Scripts (require Python 3.13+ with PyYAML):**
- `scripts/generate_calendar.py` - Generates iCal/ICS calendar feeds to `output/`
- `scripts/generate_monthly_calendars.py` - Expands recurring events into month-specific calendars in `distribution/`
- `scripts/audit_check.py` - Reports entries due for audit, unverified entries, statistics
- `scripts/deduplicate_entries.py` - Merge duplicate entries in sources.yaml
- `scripts/add_type_fields.py` - Migration script for adding location_type/resource_type fields
- `scripts/add_enrichment_fields.py` - Migration script for adding enrichment fields
- `scripts/requirements.txt` - Python dependencies (pyyaml)
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
- Responsive two-column layout on desktop (768px+), single-column on mobile
- Platform selector (Apple/Google/Outlook) with subscribe buttons
- Inline calendar preview with List and Calendar grid views
- Updates section for announcing new content

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
- `index.html` - Landing page with subscription links
- `apple/`, `google/`, `outlook/` - Platform-specific ICS files
- `events.json` - JSON feed for programmatic access

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
- The `parse_schedule()` function in `generate_calendar.py` handles this conversion

## Ongoing Work

Check `data/queue.yaml` for pending research items and `data/audit-log.yaml` for recent changes.

Future improvements:
- Guide regeneration from sources.yaml (guides are currently manually maintained)
- Enrichment data population (practical_tips, accessibility, social_intensity, good_for)
