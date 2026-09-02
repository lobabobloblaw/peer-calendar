# Portland Metro Peer Support Calendar

A maintained calendar and directory of **free and low-cost activities, services, and
resources for adults in the Portland metro area**, built for FolkTime's peer support
programs and for anyone living on a limited income.

**Live site:** <https://lobabobloblaw.github.io/peer-calendar/>

It covers peer support groups, community meals and food pantries, free fitness and
recreation, libraries and museums, parks, festivals, discount programs, and transit
assistance across Multnomah, Clackamas, and Washington counties — currently 272 active
resources and 571 programs, each carrying the official source it was verified against and
the date someone last checked it.

## Subscribe

The calendar is published as standard iCal feeds, so it updates itself once you subscribe.
Replace `apple` with `google` or `outlook` for the platform-specific version.

| What | URL |
|---|---|
| Everything | `https://lobabobloblaw.github.io/peer-calendar/apple/all-events.ics` |
| Peer support only | `https://lobabobloblaw.github.io/peer-calendar/apple/peer_support.ics` |
| Food and farms | `https://lobabobloblaw.github.io/peer-calendar/apple/food_farms.ics` |

Other categories: `arts_culture`, `events`, `fitness_wellness`, `parks_nature`,
`social_activities`, `transportation`.

- **Apple Calendar** — File → New Calendar Subscription, paste the URL. Category colors
  come through automatically.
- **Google Calendar** — Settings → Add calendar → From URL, paste the URL.
- **Outlook** — Add calendar → Subscribe from web, paste the URL.

The website also offers month, list, seasonal, map, and full-directory views, with filters
for category, vibe, social intensity, and audience, and a print option for handing out
paper schedules.

## Something out of date?

Schedules change and places close. If you find something wrong,
[open an issue](https://github.com/lobabobloblaw/peer-calendar/issues/new) with the
resource name and what you saw. Corrections are welcome from anyone — you do not need to
know how any of this works.

Contact: avoigt@folktime.org

## How it works

`data/sources.yaml` is the single source of truth. Everything published is generated from
it, so the feeds, the website, and the markdown guide can never disagree with each other:

```
data/sources.yaml ──> generate_calendar.py ──> docs/{apple,google,outlook}/*.ics
                                          └──> docs/events.json ──> the website
                  └─> generate_guides.py  ──> guides/resources-guide.md
```

Generation is deterministic: regenerating from unchanged data produces byte-identical
files, so a diff shows only what a data change actually did. A GitHub Actions workflow
regenerates and commits the feeds whenever the data changes, and again every Monday.

Resources are re-verified against their official sources on a schedule set by how fast
they change — quarterly for peer support schedules and food services, annually for stable
places. `data/audit-log.yaml` records every check.

## Working on it

Requires Python 3.11 or newer (CI uses 3.13) and Node 22 for the web tests.

```bash
python3 -m venv scripts/venv
source scripts/venv/bin/activate
python -m pip install -r scripts/requirements.txt

npm run check            # every check CI runs, in CI's order
npm run check -- --e2e   # also the Playwright browser suite
```

Common tasks:

```bash
python scripts/audit_check.py --weekly-summary   # what needs verifying
python scripts/audit_check.py --workload         # how much work that is
python scripts/audit_complete.py --id <entry-id> # record a verification
python scripts/generate_calendar.py --json       # regenerate into output/
python scripts/generate_guides.py                # regenerate the markdown guide
```

`AGENTS.md` covers conventions and the pull request checklist. `CLAUDE.md` is the detailed
working guide, including the data schema, the controlled vocabularies, and the audit
process. Reviews and planning documents live in `docs-archive/`.

## Repository layout

| Path | What it is |
|---|---|
| `data/sources.yaml` | The database. Multi-document YAML, one document per category. |
| `data/audit-log.yaml` | Verification history. |
| `data/queue.yaml` | Resources still to research. |
| `scripts/` | Generation, validation, audit, and geocoding tooling, plus its tests. |
| `docs/` | The published GitHub Pages site: `index.html`, `events.json`, and the ICS feeds. |
| `guides/resources-guide.md` | Generated markdown guide. |
| `templates/` | Templates for new entries and audit reports. |

Generated output in `docs/` and `guides/` is committed because GitHub Pages serves it
directly; `output/` and `distribution/` are local scratch and are gitignored.

## A note on the data

Only public facts from official sources are stored here. No participant or client
information of any kind belongs in this repository. Resources confirmed closed are kept
with `status: CLOSED` rather than deleted, so they are not researched and re-added later —
they are excluded from everything published.
