# Project Review — September 2, 2026

A full review of the peer-calendar project: data, generators, published feeds, web calendar,
CI, documentation, and process. Everything below was measured in this session against
`main` at `cec6f32`. The companion document `orchestration-2026-09.md` turns the
recommendations into a work plan for an agent to execute.

**Headline:** the July review's structural fixes held. Generation is deterministic, the
browser and the ICS feeds share one schedule resolver, closed entries are filtered, and the
site now has a real accessibility test gate. The risks have moved from *correctness of the
generator* to *operations and reach*:

1. **A time-bombed unit test will fail the next weekly CI run (Monday, September 7).** The
   Generate Calendars workflow runs tests before it regenerates, so publishing stops until it
   is fixed. Four summer concert series that ended August 31 will stay in the live feeds.
2. **Audit capacity is at 316%.** 145 of 272 active entries are overdue, 50 of them
   critical (24 peer-support, 26 food). Retiering was done in August; it is not enough.
3. **Real data never reaches the site.** Twelve entries, including FolkTime's own two peer
   connection centers, keep their addresses in a `locations` list the feed does not export.
   FolkTime is not on the map, and its drop-in hours are not on the calendar.
4. **2027 is unplanned.** The calendar year is hard-coded in 23 places across the
   generator (9) and the page (14).

---

## 1. What was verified this session

| Check | Result |
|---|---|
| `audit_check.py --validate` | 275 entries, clean |
| `validate_schedules.py` | 505 schedules, 0 failures, 9 incomplete, 56 vague, 0 unanchored |
| Python unit tests (`unittest discover`) | 153 tests, **1 error** (`test_until_is_utc`) |
| Node contract tests (`npm run test:web-contract`) | 8 pass |
| Playwright + axe browser suite (`npm run test:web-e2e`) | 10 pass |
| Regenerate feeds vs. published `docs/` | **9 ICS files and `events.json` differ** (4 expired series still published) |
| Regenerate `guides/resources-guide.md` | Differs by the date stamp only |
| Live URL health (CI run this morning) | 414 URLs: 301 reachable, **112 warnings, 1 broken** |
| Audit backlog | **145 overdue** of 272 active (53%), oldest 114 days |

Corpus shape: 275 entries (3 closed), 571 programs in 120 entries, 416 events per platform
feed, 182 entries geocoded, 124 entries with no schedule or dates at all (directory-only).

---

## 2. Findings

Ordered by severity. Each has a task in the orchestration document.

### P0 — fix this week

**2.1 `test_until_is_utc` fails after August 31 and blocks regeneration.**
The fixture uses `schedule_end_date: 2026-08-31`. Once that date passes,
`build_recurring_event()` correctly returns `None` for an expired window, and the test
dereferences it (`scripts/test_schedule_parsing.py:478`). The function already accepts a
`today` argument; the test does not pass one. The Aug 31 scheduled run passed because the
window had not yet expired. The Sept 7 run will fail at the "Run tests" step, before
generation, so:

- the four series with `UNTIL=20260901T065959Z` (Tualatin Library Summer Sunday Music,
  Gresham Music in the Parks, Happy Valley Thursday Concerts, Tualatin Concerts in the Parks)
  remain in every published feed;
- any edit to `sources.yaml` stops reaching subscribers until someone notices a red
  scheduled run, and nothing notifies anyone when a scheduled run fails.

Fix is one line (pass `today=date(2026, 8, 1)`), plus a rule for the suite: any test that
builds a bounded window passes an explicit `today`.

**2.2 One confirmed broken source URL.** `https://racc.org/artsforall` (entry `arts-for-all`)
returns 404. Arts for All is one of the highest-value discount programs in the database.

### P1 — high

**2.3 Audit load is not sustainable, and the automation to change that is half-built.**

| Measure | Value |
|---|---|
| Overdue now | 145 (critical 50, high 49, standard 9, low 37) |
| Due between now and Dec 1 | 28 more |
| Steady-state load | 821 audits/year = 15.8/week |
| Documented capacity | 5/week (316% utilized) |
| Critical overdue by category | peer_support 24, food_farms 26 |

The August retiering moved 53 entries to annual; the queue and priority model in
`audit_policy.py` are good. What is missing is anything that reduces *human* work per entry:

- The URL checker already fetches every source page weekly but throws the content away. A
  normalized text snapshot per URL would let it say "this page changed since you last
  verified it" and, more importantly, "this page has not changed," which is most of them.
- There is no assisted verification path. A `verify_entry.py --id X` that fetches the sources,
  extracts hours/price/schedule/phone/address, and prints a proposed diff would turn a
  15-minute audit into a 2-minute review.
- The site shows a "verified" badge but no staleness. A three-tier badge (under 90 days, under
  180, older) makes the backlog visible to users and to the people who can fix it.

**2.4 Data that never reaches the published site.**

`generate_json_feed()` exports a fixed field list. Fields it drops, with counts:

| Field | Entries | What is lost |
|---|---|---|
| `locations` | 12 | Branch addresses and hours: FolkTime (NE Couch St and Oregon City), YMCA (3), TTAD pools (2), Loaves & Fishes (4), Hillsboro and Clackamas libraries, Gresham splash pads |
| `services` | 24 | Service lists for crisis centers, libraries, senior centers |
| `season` | 15 | Seasonal availability |
| `transit` | 8 | Transit directions for parks and events |
| `languages` | 3 | Language access, including Oregon Warmline's Spanish line |
| `status` | 1 | `TEMPORARILY CLOSED` (Sisters of the Road) is published like any other entry |

Because `folktime` has no entry-level `address`, the sponsoring organization has no map pin,
and its programs are four bare strings, so its Mon/Wed/Thu 10am–2pm drop-in hours are not
on the calendar. Sixteen entries carry **77 string programs** this way. They pass validation
(nothing checks that a program is a mapping) and render as plain bullets.

Separately, `audience: spanish_speaking` is a documented tag used by **zero** entries, so the
Spanish filter pill always returns nothing, while three entries list Spanish under
`languages`. `women`, `children`, and `bipoc` are used by two entries each.

**2.5 Pull requests are not validated before merge.**
For a PR that touches `data/sources.yaml`, CI runs only the URL-checker unit tests and the
audit-policy tests. `audit_check.py --validate`, `validate_schedules.py`, the schedule
parsing suite, and the browser parity test run only after merge to `main`, inside the job
that publishes. A malformed schedule string is caught after it lands, by a red run that
nobody is notified about.

**2.6 The weekly regeneration commits every Monday even when nothing changed.**
`generate_guides.py:398` stamps `date.today()` into the guide header. The workflow's
`git diff --quiet docs/ guides/` is therefore never quiet, so every scheduled run produces
an "Auto-generate…" commit (Aug 24, Aug 31). This contradicts the documented determinism
rule and hides real changes in the history. `events.json` already solved this by using the
newest `last_verified`.

**2.7 URL health results have no owner.**
The live check step fails with `--fail-on-broken` under `continue-on-error`, so the run shows
green. The 112 warnings (27% of all source URLs) and the one broken link live in a run
summary and a 30-day artifact. Nothing feeds them into `audit_check.py --weekly-summary`,
and warnings are never triaged into "known bot-blocker, check by hand" versus "look at this."

### P2 — medium

**2.8 2027 rollover.** Hard-coded 2026 appears 9 times in `generate_calendar.py`
(`CALENDAR_EPOCH`, `DEFAULT_DTSTAMP`) and 14 times in `index.html` (title, OpenGraph, `<h1>`,
logo alt text, print minimum date, print header). `generate_monthly_calendars.py` is fixed to
Dec 2025–Dec 2026. There is no check that flags entries whose `dates` are all in the past, so
2026 festivals will linger in the Seasonal tab into 2027. Recurring-event UIDs are
epoch-independent, which is good; the rollover should not change them.

**2.9 Page weight and tracked assets.** `docs/` is 22MB in git:

| Asset | Size | Status |
|---|---|---|
| `calendar-logos/` | 9.3MB, 16 files | One random logo per page load; 12 are 320–920KB PNGs, only 4 have WebP versions |
| `cakes/` + `cakes.html` | ~7MB | Unreferenced |
| `database-overview.html/.md` | 124KB | Unreferenced, says "over 200 resources" |
| `2026-calendar-2.png` | 680KB | OpenGraph image only |
| `events.json` | 762KB | Pretty-printed; parsed on every page load |
| Three.js r134 + Vanta (CDN) | ~600KB | Loaded on all devices; no `saveData` check; no SRI on the dynamic loads |

The audience includes people on limited data plans and older phones.

**2.10 Front-end maintainability.** `index.html` is one 196KB file: 2,214 lines of CSS and
2,212 lines of JavaScript in 64 functions. The tests reach into it with
`html.indexOf('const resolvedWeekdayNumbers')` and an `awk` script to find the `<script>`
block. Splitting into `styles.css` and `app.js` (still no bundler) would let node import the
functions directly and let `node --check` replace the awk.

**2.11 Schema sprawl.** Entries use 90+ distinct top-level keys; about 50 appear on a single
entry (`holes`, `crops`, `mission`, `peer_respite`, `notes_extra`, `notes_on_access`,
`self_guided_tours`…). Validation checks required fields, enums, and year-suffixed keys, but
not unknown keys, program shape, or `hours` type. Phone numbers use four formats.

**2.12 Calendar coverage.** 45% of entries carry no time information and 56 schedules are
vague. The highest-value conversions are in peer support: NAMI Washington County (both
groups: "Contact for current schedule"), PFLAG Portland ("Twice monthly"), Prism Moves BIPOC
class, Disabled Hikers, Every Body Athletics. 34 entries have an address but no coordinates.

**2.13 Repository hygiene and documentation drift.**

- No root `README.md`. A visitor to the GitHub repo sees no description of what this is,
  how to subscribe, or how to contribute. `CLAUDE.md` (30KB) is agent instructions.
- `CLAUDE.md` drift: "~269 resources" (275), "178 geocoded" (182), "~4400 lines" (4,749),
  "Vanta.js" (now `sky-effect.js`), "Python 3.13+" (runs on 3.11; CI uses 3.13). It does not
  list `audit_policy.py`, `check_source_urls.py`, `analyze_data_quality.py`,
  `migrate_audit_cadence.py`, or the three `.mjs` test files.
- `SESSION_STATE.md` (23KB, tables from January) and `HOME-MACHINE-TODO.md` (July) are
  hand-off notes whose content has moved to GitHub issues. `research-sweep-2026-03-04.md` and
  `project-review-2026-07-24.md` sit at the root.
- Four one-shot migration scripts remain in `scripts/` (`add_audience_fields.py`,
  `add_type_fields.py`, `migrate_audit_cadence.py`, `deduplicate_entries.py`).
- `generate_monthly_calendars.py` re-implements RRULE expansion (a third engine after the
  generator and the browser) and is not run or tested by CI.
- Five stale remote branches: four merged `agent/*` branches and `claude/audit-content-HGGy2`.
- Issue #3 (Lloyd Center) is complete in the data (`schedule_end_date: 2026-08-02`) but open.
  Issue #4's own comment says two of eleven items remain.
- `generate-calendars.yml` installs `pyyaml python-dateutil` by name instead of
  `requirements.txt`, pushes without `pull --rebase` (a documented race), and uses action
  versions that now emit Node 20 deprecation warnings.

**2.14 Accessibility and UX gaps.** No skip link to `<main>`. No visible treatment for
`TEMPORARILY CLOSED`. No "report a change" path from a resource card. The Updates section is
hand-curated plus one auto line per day; issue #21 ("new this month") could be derived from
the diff `add_update_post.py` already computes.

**2.15 ICS details.** UIDs end in `@portlandresources.org`, a domain the project does not
control. Changing UIDs duplicates events for existing subscribers, so if this is ever changed
it should coincide with a deliberate rollover. `fold_ical_line()` folds by character rather
than octet (harmless in practice).

---

## 3. What is working well

- **Deterministic generation** with `CALENDAR_EPOCH` and `DTSTAMP` from `last_verified`.
  A `docs/` diff shows only what a data change did.
- **One schedule resolver.** `resolved_schedule` in `events.json` (schema version 1) is
  consumed by the browser; the parity test guards it.
- **Program-level `dates`** for touring series, closed-entry filtering, biweekly anchoring
  checks, and year-suffix rejection all closed real classes of silent data loss.
- **Accessibility gate**: deterministic contract tests plus Playwright with axe across six
  viewports, reduced-motion, WebGL fallback.
- **Risk-based audit policy** with a priority queue and an honest workload report.
- **URL checker** that distinguishes broken links from bot-blocking, with per-host limits.
- **Clear agent instructions** in `CLAUDE.md` and `AGENTS.md`, and a clean PR history in
  August (six PRs, each with validation notes).

---

## 4. Recommendations, in priority order

1. **Unblock CI now** (2.1) and fix the Arts for All URL (2.2). One PR, merged before Monday.
2. **Make PRs safe** (2.5): a `validate.yml` workflow that runs every deterministic check on
   pull requests. Make the guide header deterministic (2.6). Notify on scheduled-run failure
   and route URL-health results into the weekly summary (2.7).
3. **Get the data onto the site** (2.4): export `locations`, `services`, `transit`,
   `languages`, `season`, `status`; convert string programs to objects; put FolkTime on the
   map and its drop-in hours on the calendar; make the Spanish filter work.
4. **Reduce human audit work per entry** (2.3): page snapshots in the URL checker, an
   assisted `verify_entry.py`, staleness tiers on the site, then work the 50 critical
   overdue entries with those tools.
5. **Plan 2027** (2.8): one `calendar_year` constant flowing from generator to page, a
   stale-event check, a rollover checklist.
6. **Asset diet and file split** (2.9, 2.10): WebP logos, delete unreferenced assets, split
   `index.html`, lazy sky effect, SRI on CDN loads.
7. **Tighten the schema** (2.11) and fill peer-support schedule gaps (2.12).
8. **Hygiene** (2.13, 2.14): root README, reconcile `CLAUDE.md`, archive stale hand-off
   docs and one-shot scripts, close finished issues, delete merged branches, skip link.
9. **Then the enhancement backlog**: print weekly list (#22), new-this-month (#21),
   per-category subscribe (#15), PWA (#17), near-me (#13), weather tags (#16), submit form (#20).

Items 3, 4, and the critical-entry audits need a network-connected session; the sandbox used
for this review could not fetch any source URL. Everything else is runnable anywhere.
