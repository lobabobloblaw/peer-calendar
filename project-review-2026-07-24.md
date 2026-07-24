# Project Review — July 24, 2026

A full review of the peer-calendar project for correctness and information accuracy.
Scope: `data/sources.yaml` (269 entries), the generation scripts, the published feeds in
`docs/`, the web calendar, CI, and the project documentation.

**Headline:** the data collection is in good shape, but the calendar *generator* was
introducing errors that the data itself did not contain. Roughly a fifth of the recurring
events in the published ICS feeds landed on a wrong date, and seven dated festivals were
published a full year late. Those are fixed. What remains is an external-verification
backlog that needs a network-connected session.

---

## 1. What was fixed in this pass

### 1.1 Recurring events started on a date the rule did not allow

**Impact: 37 of 198 published events (19%).**

Monthly rules were written as `BYDAY=TH;BYSETPOS=1` ("first Thursday") but `DTSTART` was set
to the next matching *weekday* after the generation date. Generated on Friday July 24, "Portland
Art Museum: Free First Thursday" got `DTSTART` = **Thursday July 30** — the fifth Thursday.
Per RFC 5545, `DTSTART` is always part of the recurrence set, so every subscriber saw a
phantom event on the wrong day, in addition to the correct series. Affected NAMI Multnomah and
Clackamas support groups, Q Center's Trans PDX and QTIBIPOC groups, Hopewell House grief
support, Rock Haven community climbs, OMSI First Sunday, and 30 others.

Because `DTSTART` was anchored to *generation time*, the wrong date changed on every CI run.

*Fix:* `_first_monthly_occurrence()` walks forward month by month to find a date that actually
satisfies the rule. Regression test asserts `DTSTART` matches its own `RRULE`.

### 1.2 "First Tuesday and first Saturday" collapsed to one day

`BYDAY=TU,SA;BYSETPOS=1` means "the first item in the combined set" — whichever of Tuesday or
Saturday comes first in the month — not "the first Tuesday *and* the first Saturday". Q Center's
Trans PDX Support Group and Faith Café's monthly meal were both mis-encoded this way.

*Fix:* monthly rules now use the prefixed form `BYDAY=1TU,1SA`, which says what is meant.

### 1.3 Dated festivals published a year late

`parse_date_string()` could not parse a cross-month range, so `"May 22 - June 28, 2026"` fell
through to the single-date branch, which then ignored the stated year and defaulted to
"next year". Seven events were wrong in the live feeds:

| Entry | Written in sources.yaml | Published as |
|---|---|---|
| Portland Rose Festival | May 22 – June 28, 2026 | May 22, **2027** (one day) |
| Wooden Shoe Tulip Festival | March 20 – April 26, 2026 | March 20, **2027** (one day) |
| Swan Island Dahlias | August 1 – September 30, 2026 | August 1, **2027** (one day) |
| Christmas Ships Parade | November 27 – December 21, 2026 | November 27, **2027** (one day) |
| PPR Summer Free For All | July 9 – September 5, 2026 | July 9, **2027** (one day) |
| Peacock Lane | December 15-31 (no year) | December 15-31, **2027** |
| Pedalpalooza | June through August 2026 | **August 20, 2027** |

*Fix:* the parser now handles cross-month ranges, month-to-month spans without days
("June through August 2026"), en/em dashes, and "to"/"through". A written year always wins;
a year-less date resolves to its next occurrence rather than always jumping forward a year.
All 32 dated events now parse to the dates written in the data.

### 1.4 `Mon-Fri` rendered as Monday and Friday only

Two independent schedule parsers exist — Python for the ICS feeds, JavaScript for the web
preview — and they disagreed on 12 of 257 schedule strings.

In the JavaScript parser the day-range branch was unreachable: individual day matching ran
first and always found the two endpoints of a range, so `result.days.length === 0` was never
true. **Bridges to Change Club Hope's recovery drop-in center ("Monday-Friday 8am-5pm") showed
on the website as open Mondays and Fridays only.** Same for SPOT Southwest, DDA's daily central
office meetings, Dharma Rain's morning meditation, Gresham's free summer kids' lunch, and the
Elsie Stuhr Meals on Wheels lunch.

The Python parser had the mirror-image bug: it stopped after the first range, so
`"Fri 11am-1pm & 4-7pm; Sat-Sun 2:30-4:30pm"` (Mt Scott Community Center slide hours) dropped
Friday. It also did not recognise ranges written out in full (`"Monday-Friday"` → `MO,FR`).

*Fix:* both parsers now expand ranges first, then add standalone day names that a range did
not already cover, and both accept full day names in ranges. Verified: **0 divergences across
all 257 schedule strings.**

### 1.5 "daily" in prose widened events to all seven days

`"Fri-Sun (check Facebook for daily schedule)"` (Delta Park Powwow) matched the `daily`
keyword and became a seven-day event. *Fix:* `daily` only applies when no explicit days were
found. Both parsers.

### 1.6 Events that ended before they started

Ground Kontrol's two free-play sessions are `"12-12am"` — noon to midnight. `DTEND` was
computed as 00:00 *the same day*, twelve hours before `DTSTART`, which is invalid per RFC 5545.
*Fix:* an end time at or before the start rolls to the next day.

### 1.7 `UNTIL` was not a UTC timestamp

RFC 5545 requires `UNTIL` to be UTC when `DTSTART` carries a `TZID`. All eight bounded
recurrences emitted floating local time (`UNTIL=20261224T235959`). *Fix:* converted to UTC
using the same US DST rule the generated `VTIMEZONE` already declares — no `tzdata`
dependency, so it behaves identically in CI.

### 1.8 Permanently closed resources were published as if open

Three entries carried `status: CLOSED` and a `❌` flag, and nothing filtered them. They
appeared in `events.json`, which drives the map and the Resources directory:

- **Five Oaks Museum** — closed April 2025 (funding cuts)
- **Lunchtime Disc Golf** — closed July 2021
- **NeighborWalks** — program ended October 2022

Someone could have travelled to a museum that has been shut for over a year.

*Fix:* `is_closed()` drops them from every published artifact. They stay in `sources.yaml` as
a record so they are not re-researched and re-added, and `generate_guides.py` already lists
them in a separate "no longer operating" section.

### 1.9 Events stored in a field nothing reads

`dates_2026` looked meaningful in the YAML but was read by no script and no view.

- **Portland Sunday Parkways** — all four 2026 car-free-street days were invisible in every
  calendar, on the map, and in the Seasonal Events tab.
- **Clackamas County Repair Fairs** — all twelve 2026 fairs, likewise invisible.
- **THPRD Fitness in the Park** (`schedule_winter_2026`) — six free outdoor classes, invisible.
- **Repair PDX** and **Friends of Lone Fir Cemetery Tours** — published date lists shadowed by
  looser recurrence strings.

*Fix:* all converted to real `programs` with `dates`. This required teaching the generator and
the web preview about **program-level `dates`** — a program can now pin specific dates with
`schedule` supplying only the time of day, which is the right model for a touring series.
Sunday Parkways now publishes 4 events, the Clackamas repair fairs 12, and THPRD Fitness in
the Park 9 — **25 events that previously reached nobody**, on their correct dates and times.
Repair PDX (16) and Lone Fir (34) went from loose monthly recurrences to the organizers'
published dates.

Two of the Lone Fir tours also demonstrate why explicit dates beat recurrence strings:
"1st Saturday of even months" is not expressible as an RRULE, and was being generated every
month. The published date list is now the source of truth.

### 1.10 A weekly meal collapsed into a monthly one

Faith Café's schedule string — `"Sundays 4:15pm; last Thursday of each month 4:15pm"` —
merged into a single rule meaning "last Thursday *or* Sunday of the month", losing the weekly
Sunday meal entirely. This is one of the few free community meals in Washington County.
*Fix:* split into two programs in the data.

### 1.11 Validation gaps that let all this through

`audit_check.py --validate` reported a clean bill of health throughout. It now also checks:

- **Year-suffixed field names** (`dates_2026`, `schedule_winter_2026`, `exhibits_2025_2026`) —
  the exact class of silent-data-loss bug above, at both entry and program level.
- **Tag vocabularies** for `accessibility`, `good_for`, `audience`, `social_intensity` against
  the lists in CLAUDE.md. This caught `accessibility: outdoor` (a `good_for` value in the wrong
  field) on two entries, now removed.
- `validate_schedules.py` now also parses every `dates` value, so an unparseable date fails CI
  instead of silently dropping the event. It no longer flags a program's time-of-day
  `schedule` as "missing a weekday" when the dates are explicit.

`varies` was in use on 16 entries for `accessibility` and `social_intensity` but was not in the
documented vocabulary. It is a reasonable value for roving and umbrella programs, so it has
been added to CLAUDE.md rather than removed from the data.

### 1.12 Test coverage

The suite went from 56 to 79 tests. New coverage: day-range expansion in both directions,
wrap-around ranges, `daily` prose handling, all five date-string shapes, year resolution,
`DTSTART`-matches-`RRULE`, prefixed `BYDAY`, overnight events, UTC `UNTIL`, expired windows,
and closed-entry detection. Every fix above has a test that fails without it.

**Verification after the changes:** 269 events generated (up from 198), 0 with a `DTSTART`
outside their own rule, 0 with `DTEND ≤ DTSTART`, 0 non-UTC `UNTIL`, 0 parser divergences,
79/79 tests passing, all three CI gates green. Browser smoke test confirms the web calendar
renders, the drop-in center shows Monday through Friday, and Sunday Parkways appears on
August 2.

---

## 2. What still needs a human — external verification

**None of the resource facts could be re-verified in this session.** This environment's network
policy blocks outbound HTTPS to non-allowlisted hosts; all 418 source URLs failed at the proxy
(`403 Forbidden` on CONNECT), and `WebFetch` is blocked the same way. Everything above is
structural and internal-consistency work. The items below need a session with open network
access, or a phone.

### 2.1 The audit backlog is the largest accuracy risk

**185 of 269 entries (69%) are past their `next_audit` date**, the oldest by 74 days.

| Frequency | Overdue |
|---|---|
| quarterly | 162 |
| annually | 12 |
| monthly | 11 |

The 11 overdue monthly entries are the highest priority — monthly cadence was assigned to
things that change often (pricing, seasonal hours, event line-ups). `SESSION_STATE.md` still
describes a baseline sweep completed in January; the last recorded audit activity in
`data/audit-log.yaml` is from May.

At the documented pace of 15–30 minutes per weekly session, 185 entries is a multi-month
backlog. Two structural options worth considering:

1. **Re-tier the frequencies.** 162 quarterly entries means ~54 audits a month, which the
   weekly workflow cannot absorb. Many of these are stable (park addresses, library branch
   hours) and would be better as `annually`.
2. **Automate the cheap half.** A link-checker in CI would catch dead URLs and moved pages
   without human time, leaving people to verify the things only a person can — whether a
   support group still meets, whether the price changed.

### 2.2 Entries explicitly flagged as needing a phone call

| Entry | What to confirm |
|---|---|
| `dda-oregon` | Five open `⚠️ VERIFY` flags. Two conflicting phone numbers (503-737-4126 vs 503-222-6484), possible office move to 4141 SE Division, and a meeting schedule that disagrees with the national directory. The website's copyright reads 2008. Call both numbers. |
| `sisters-of-the-road` | Café temporarily closed since April 2026, seeking a new location. Any reopening news? |
| `sikh-center-langar` | Friday 8pm langar is not on the website schedule. Call 971-217-8577. |
| `lloyd-center-walking` | Lloyd Center is slated to close by end of 2026; demolition plan approved. Needs a `schedule_end_date` once a date is announced. |
| `4d-recovery` | `SESSION_STATE.md` records "may be temporarily closed/relocating" — never resolved. |
| `nami-clackamas` | Women's group schedule needs manual check (Wix site). |
| `providence-grief-support` | Page did not render for automated verification. |

### 2.3 Content that has aged out

- **`multnomah-discovery-pass`** still lists **Five Oaks Museum** as a participating venue.
  The museum closed permanently in April 2025, so at least one entry in that pass list is
  stale — the whole list needs re-checking. Flagged in the data.
- **`pcc-art-galleries`** — the listed exhibits are the 2025-26 academic year; the last closed
  May 27, 2026. The 2026-27 season is not captured. Flagged.
- **`thprd-fitness-in-park`** — the class list is the Winter/Spring 2026 session, which ended
  March 22. Now correctly bounded with `schedule_end_date` so it no longer appears in summer
  calendars, but the current session's classes are unknown. Flagged.
- **`tualatin-heritage-center`** — programs still carry 2025 dates (Fossil Fest, August 2 2025;
  Heritage Evening, September 5 2025). Needs the 2026 line-up.
- Several entries describe facilities as "newly opened" or "recently renovated" with 2025
  dates. Cosmetic, but it dates the guide.

### 2.4 Coverage gaps

- **36 entries with a street address have no coordinates**, so they are missing from the map.
  Some are legitimately un-geocodable ("Statewide", "Various parks", a P.O. box), but roughly
  half are real addresses that should geocode — including `nami-multnomah` (464 SE 185th Ave),
  `decompress-connect-meditation` (TaborSpace), and `south-barlow-berries`. `geocode_addresses.py`
  needs a network-connected run.
- **79 schedule strings still produce no calendar event** because they are genuinely vague
  ("Contact for current schedule", "Various times", "Multiple weekly meetings"). These
  resources appear in the Resources directory but never on the calendar. The largest single
  case is `alano-club-portland`, where seven recovery meeting groups are stored as "Weekly
  meetings" / "Multiple weekly meetings" — real schedules exist on portlandalano.org and would
  add meaningful peer-support coverage.
- **Biweekly events cannot be anchored.** `"Every other Monday 1-3pm"` becomes
  `INTERVAL=2` starting from whenever the file was generated, so which Monday it lands on is
  arbitrary — a 50/50 chance of being a week off. Affects Gresham Senior Center's movie
  matinees, Gresham Music in the Parks, and Shift's Foster Night Ride. The fix is a data one:
  add `schedule_start_date` set to a known meeting date. Worth a validator warning.

---

## 3. Smaller observations

- **`docs/index.html` duplicates `parse_schedule` in JavaScript.** The two implementations
  drifted into 12 disagreements before this pass. They agree now, but nothing enforces it.
  Consider having `generate_calendar.py` emit resolved days/times into `events.json` so the
  browser does not need to re-parse the strings at all — that would delete the duplication
  rather than police it.
- **CI regenerates `docs/` on every push, and every `DTSTART` moves.** Because recurring events
  are anchored to generation time, an unrelated commit produces a ~2,900-line diff and a fresh
  "Auto-generate calendar feeds" commit. Anchoring recurrences to a fixed season start
  (or to `schedule_start_date` where known) would make the output deterministic and the
  history readable.
- **CI does not run `generate_guides.py`,** so `guides/resources-guide.md` drifts from
  `sources.yaml` between manual regenerations. It was three months and three entries stale at
  the start of this review. Regenerated here; worth adding to the workflow.
- **Three legacy hand-maintained guides remain** — `activities-guide-1.md`,
  `activities-guide-2.md`, `food_farms-guide.md` — alongside the generated
  `resources-guide.md`. CLAUDE.md says the generator "replaces manual guide maintenance", but
  `guide_location` fields throughout `sources.yaml` still point at the old files. Either
  retire them or say in CLAUDE.md that they are frozen historical copies.
- **`data/sources-deduped.yaml` and `data/sources-backup-2025-12-03.yaml`** are 450KB of stale
  near-copies of the master file sitting next to it. An accidental edit to the wrong one would
  be easy and hard to notice.
- **`docs/` carries ~14MB of unreferenced assets** (`cakes/`, `calendar-logos/`,
  `weather-test.html`, `2026.png`, `2026psc.png`, `screenshot.jpeg`), which every GitHub Pages
  visitor's repo clone pays for.
- **CLAUDE.md says the scripts need Python 3.13+**; they run fine on 3.11. CI pins 3.13. Not a
  problem, just imprecise.
- **`fold_ical_line()` folds by character, not octet.** RFC 5545 specifies octets, so a line of
  75 multi-byte characters exceeds the limit. Harmless in practice — every major client
  tolerates it — but worth knowing.

---

## 4. Suggested order of work

1. Call the numbers in §2.2 — `dda-oregon` in particular has been carrying contradictory
   contact information since March.
2. Run `geocode_addresses.py` from a network-connected machine to close the map gaps (§2.4).
3. Work the overdue monthly entries (11), then re-tier the quarterly ones rather than trying to
   clear 162 at the documented pace (§2.1).
4. Refresh the aged-out content in §2.3 — all four are already flagged in the data.
5. Add `schedule_start_date` to the three biweekly events so they land on the right week.
6. Decide on the legacy guides and the duplicate `sources-*.yaml` files.
