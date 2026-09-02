# Orchestration Plan — September 2026

A work plan derived from `project-review-2026-09-02.md`, written for an autonomous agent
(Opus 5) to execute task by task. Each task is one pull request. Tasks inside a wave are
independent and can run in parallel; waves are ordered by dependency and by merge-conflict
risk. Read the review first for the evidence behind each task.

## 0. Ground rules for every task

- **Branch and PR per task.** Branch name `agent/<task-id>-<slug>` (for example
  `agent/t0.1-freeze-test-today`). PR title in imperative sentence case, body per
  `AGENTS.md`: impact, affected resource IDs, verification sources and dates, validation
  commands run, generated diffs called out. Link the issue where one exists.
- **Run the full check list before every push**, from the repo root:

  ```bash
  python scripts/audit_check.py --validate
  python scripts/validate_schedules.py
  python -m unittest discover -s scripts -p 'test_*.py'
  python scripts/generate_calendar.py --json            # writes output/, not docs/
  node scripts/test_web_schedule_parity.mjs             # after generation
  npm run test:web-contract
  npm run test:web-e2e                                  # when docs/index.html or sky-effect.js changed
  ```

  Regenerate `docs/` (`--publish`) and `guides/resources-guide.md` only when the task is
  a data or generator change, and say so in the PR.
- **Preserve determinism.** Regenerating from unchanged `sources.yaml` must produce
  byte-identical output. No wall-clock values in generated files.
- **Never delete a closed entry, never advance `last_verified` without verification**, never
  add a second natural-language schedule parser (the browser consumes `resolved_schedule`).
- **Network.** Tasks marked `[network]` fetch source websites and cannot run in a
  sandbox without outbound access. Tasks marked `[human]` need a phone call or a browser on a
  site that blocks bots. Do everything else first; leave a clear note in the PR for what
  remains.
- **Do not widen a task.** If a task uncovers a neighbouring problem, file an issue or add it
  to the notes section of the PR; do not fix it in the same PR.
- **Conflict map.** Only one open PR at a time may touch each of these files:
  `docs/index.html`, `scripts/generate_calendar.py`, `.github/workflows/generate-calendars.yml`,
  `CLAUDE.md`. Merge before starting the next task that touches the same file.

## 1. Waves

| Wave | Tasks | Why this grouping |
|---|---|---|
| 0 — today | T0.1, T0.2 | Unblocks the Sept 7 scheduled run; single PR, merge immediately |
| 1 — parallel | T1.1, T1.2, T1.3, T1.4, T4.1, T6.1, T6.2 | Disjoint files; no `index.html` or generator changes |
| 2 — parallel with one lock | T2.1 (generator + page), T2.2, T3.1, T5.1 (generator only, after T2.1), T1.5 | T2.1 takes the `index.html` lock |
| 3 | T2.3, T2.4, T4.2 (index split, alone), T3.2 | T4.2 rewrites `index.html`; nothing else may touch it while open |
| 4 | T4.3, T4.4, T3.5, T5.2, T5.3, T3.3 `[network]`, T3.4 `[network]` | After the split, UI work is in `app.js` |
| 5 | T7.x product features | Only after the platform work above |

## 2. Tasks

### Wave 0 — unblock CI

#### T0.1 Freeze `today` in bounded-window tests
- **Problem.** `scripts/test_schedule_parsing.py::TestRecurrenceRules::test_until_is_utc`
  builds an event with `schedule_end_date: 2026-08-31` and no `today`; after Aug 31 the
  window is expired, `build_recurring_event()` returns `None`, and the test raises
  `AttributeError`. The Generate Calendars workflow runs tests before generating, so the
  Sept 7 scheduled run will fail and publishing stops.
- **Do.** In `TestRecurrenceRules.build()`, pass `today=date(2026, 8, 1)` (a module constant
  `FROZEN_TODAY`). Audit every test in the file that constructs a window with dates and give
  each an explicit `today`. Add one regression test that calls `build()` with a window ending
  before `FROZEN_TODAY` and asserts `None` (already exists as
  `test_expired_window_produces_no_event`; keep it).
- **Accept.** `python -m unittest discover -s scripts -p 'test_*.py'` passes with the system
  clock set to any date (verify by running once with `faketime` or by temporarily patching
  `date.today` in a scratch script; do not commit the patch).
- **Files.** `scripts/test_schedule_parsing.py` only.

#### T0.2 Fix the broken Arts for All URL `[network]`
- **Problem.** `https://racc.org/artsforall` returns 404 (entry `arts-for-all`).
- **Do.** Find the current official Arts for All page (RACC was succeeded by the City of
  Portland's arts office; check `portland.gov` and the Arts for All partner venues list).
  Update `website` and `source_urls`, confirm the $5 ticket policy and the eligibility
  wording, then `python scripts/audit_complete.py --id arts-for-all --changes "..."`.
- **Accept.** `python scripts/check_source_urls.py` reports 0 broken.
- **Without network.** Skip; note in the T0.1 PR that this remains.

### Wave 1 — CI and publishing pipeline

#### T1.1 Pull-request validation workflow
- **Problem.** PRs that touch `data/sources.yaml` run only the URL-checker unit tests and
  audit-policy tests. Schema validation, schedule validation, the parsing suite, and the
  browser parity test run only after merge.
- **Do.** Add `.github/workflows/validate.yml` on `pull_request` (and `push` to non-main
  branches) for paths `data/**`, `scripts/**`, `docs/index.html`, `docs/events.json`,
  `package*.json`, the workflow itself. Steps: setup Python 3.13 with
  `pip install -r scripts/requirements.txt`; `audit_check.py --validate`;
  `validate_schedules.py`; `python -m unittest discover -s scripts -p 'test_*.py'`;
  `generate_calendar.py --json` to `output/`; `node scripts/test_web_schedule_parity.mjs`
  run against the fresh `output/events.json` (add a `--feed` argument or an env var so the
  test can read a path other than `docs/events.json`); `npm run test:web-contract`. Do not
  publish. Then remove the duplicated test steps from `check-source-urls.yml` and
  `generate-calendars.yml` where they now run twice, and switch `generate-calendars.yml` to
  install from `requirements.txt`.
- **Accept.** A PR that introduces `schedule: "Every Funday 3pm"` fails on the PR check. The
  merge-time job still runs generation.
- **Files.** `.github/workflows/*.yml`, `scripts/test_web_schedule_parity.mjs`.

#### T1.2 Deterministic guide header
- **Problem.** `scripts/generate_guides.py:398` writes `date.today()` into
  `guides/resources-guide.md`, so every weekly run commits.
- **Do.** Use the newest `last_verified` across active entries, formatted the same way, with
  the wording "Generated from data verified through <date>". Add a unit test in a new
  `scripts/test_generate_guides.py` that generates twice and asserts identical output, and
  that the date equals the max `last_verified` of a fixture.
- **Accept.** Two consecutive runs of `generate_guides.py` produce no git diff.
- **Files.** `scripts/generate_guides.py`, new test, regenerated `guides/resources-guide.md`.

#### T1.3 Scheduled-run failure visibility and push safety
- **Do.** In `generate-calendars.yml`: (a) before `git push`, `git pull --rebase origin main`;
  (b) add a final step `if: failure() && github.event_name == 'schedule'` that uses
  `actions/github-script` to open an issue titled "Weekly calendar generation failed
  <date>" with a link to the run, or comment on an existing open issue with that title;
  (c) bump `actions/checkout`, `actions/setup-python`, `actions/setup-node`,
  `actions/upload-artifact` to the current majors to clear the Node 20 deprecation warnings;
  (d) `permissions: issues: write` for the notify step only.
- **Accept.** Workflow YAML validates (`actionlint` if available, otherwise a dry
  `workflow_dispatch` on the branch). A forced failure on a test branch opens the issue.
- **Files.** `.github/workflows/generate-calendars.yml`, `check-source-urls.yml`,
  `test-web-ui.yml`.

#### T1.4 Route URL-health results to the weekly workflow
- **Problem.** 112 warnings and 1 broken URL live in a run summary nobody reads.
- **Do.** (a) `check_source_urls.py --state data/url-health.json` writes a compact,
  sorted, deterministic summary (per URL: status class, http code, checked date, entry IDs);
  the scheduled workflow commits that file when it changes (same commit-if-changed pattern
  as generation). (b) `audit_check.py --weekly-summary` reads it and prints "broken" and
  "warning" URLs next to the entries they belong to. (c) Add an optional per-entry field
  `source_url_notes: {url: "blocks bots; verify in a browser"}` (or a top-level
  `url_check: manual` list) that downgrades known bot-blockers from warning to "manual", and
  document it in `CLAUDE.md`. (d) Triage the current 112 warnings once, from the artifact of
  run 33667336296 or a fresh run, and encode the manual ones.
- **Accept.** `audit_check.py --weekly-summary` shows the Arts for All 404 (until T0.2
  merges); `data/url-health.json` is byte-stable across two runs with no network change.
- **Files.** `scripts/check_source_urls.py`, `scripts/audit_check.py`, `scripts/utils.py`,
  `data/url-health.json`, `CLAUDE.md`, workflow.

#### T1.5 One command that runs everything
- **Do.** Add `scripts/check_all.sh` (bash, `set -euo pipefail`) that runs the list in
  section 0 in order, skipping Playwright unless `--e2e` is passed; add `npm run check`
  that calls it; reference it from `AGENTS.md`, `CLAUDE.md`, and the PR template you add at
  `.github/pull_request_template.md` (sections: Impact, Resource IDs, Sources verified,
  Validation, Generated diffs).
- **Accept.** `scripts/check_all.sh` exits 0 on `main`.

#### T4.1 Asset diet (no `index.html` logic change)
- **Do.** Convert the 12 PNG logos in `docs/calendar-logos/` to WebP at ≤120KB each (same
  pixel size; `cwebp -q 82`), delete the PNGs, and update the 16-item array in
  `index.html` to the `.webp` names (that array is the only `index.html` edit; it does not
  conflict with the lock). Delete `docs/cakes/`, `docs/cakes.html`,
  `docs/database-overview.html`, `docs/database-overview.md`. Compress
  `docs/2026-calendar-2.png` (OpenGraph image; keep the filename). Confirm nothing links to
  the deleted files (`grep -r` across the repo). Close issue #7's asset item in the PR body.
- **Accept.** `du -sh docs/` drops from 22MB to under 5MB; e2e passes; logo still renders.

#### T6.1 Human README and documentation reconciliation
- **Do.** Write a root `README.md` for humans: what the calendar is, who it is for
  (FolkTime peer support programs), the live URL, the three subscription URLs, how to report a
  correction (link to issues), how to run the tooling locally (venv, `check_all.sh`), and a
  pointer to `CLAUDE.md`/`AGENTS.md` for contributors and agents. Reconcile `CLAUDE.md`:
  entry count, geocoded count, line counts (or drop the numbers), Python version statement
  ("3.11+ works; CI uses 3.13"), `sky-effect.js` instead of "Vanta.js", and list every
  script in `scripts/` including `audit_policy.py`, `check_source_urls.py`,
  `analyze_data_quality.py`, and the `.mjs` tests. Move `SESSION_STATE.md`,
  `HOME-MACHINE-TODO.md`, `research-sweep-2026-03-04.md`, and both `project-review-*.md`
  files to `docs-archive/` (not under `docs/`, which is published) with a one-line index;
  move `add_audience_fields.py`, `add_type_fields.py`, `migrate_audit_cadence.py`,
  `deduplicate_entries.py` to `scripts/archive/` and fix any import or test that references
  them (`test_audit_policy.py` imports `migrate_audit_cadence`; keep that import working via
  `scripts/archive/__init__.py` and a path insert, or leave `migrate_audit_cadence.py` in
  place and archive only the other three). Decide `generate_monthly_calendars.py`: either add
  a test that its expansion matches `resolved_schedule` for a sample month, or move it to
  `scripts/archive/` and remove `distribution/` from `CLAUDE.md`.
- **Accept.** `check_all.sh` passes; `CLAUDE.md` has no number that disagrees with
  `audit_check.py` output.

#### T6.2 Issue and branch hygiene
- **Do.** Close #3 with a comment pointing at the `schedule_end_date` already in the data.
  Retitle #4 to the two remaining phone items (Sikh Center langar, Providence grief intake).
  Delete remote branches `agent/audit-cadence-and-link-checking`,
  `agent/correct-calendar-data-and-schedules`, `agent/refresh-broken-links-and-flags`,
  `agent/remediate-ui-accessibility`, `claude/audit-content-HGGy2` (all merged). Add
  `.github/dependabot.yml` for `github-actions` and `npm` (monthly).
- **Accept.** `git ls-remote --heads origin` shows `main` plus active work branches only.

### Wave 2 — data reaches the site

#### T2.1 Export `locations` and put them on the map
- **Problem.** Twelve entries keep their addresses in `locations`; the feed drops the field,
  so FolkTime's two centers, YMCA's three branches, Loaves & Fishes' four centers, and the
  rest have no map pin and no address in the modal.
- **Do.** (a) Normalize `locations` in the data to a list of mappings with `name`,
  `address`, optional `phone`, `hours`, `notes`, `format`, `latitude`, `longitude`
  (`ppr-fitness-in-park` and `gresham-movies-in-park` currently use other shapes; convert
  them). (b) `validate_entry()` enforces that shape. (c) `generate_json_feed()` exports
  `locations`. (d) `geocode_addresses.py` geocodes location addresses and writes
  coordinates back into each location `[network]`; without network, geocode by hand the two
  FolkTime centers (4837 NE Couch St, Portland; 710 6th St, Oregon City) from the existing
  cache or known coordinates and mark the rest for the next networked run. (e) In
  `index.html`: `renderMapMarkers()` adds one marker per geocoded location, labelled
  "<entry name> — <location name>", using the entry's category colour; `showResourceModal()`
  renders a "Locations" section with name, address (as a maps link), phone (tel link), hours.
  (f) ICS: for a `locations` entry with an entry-level `schedule` but no entry `address`,
  keep current behaviour; do not fan out ICS events per location in this task.
- **Accept.** FolkTime appears on the map twice; `test_schedule_parsing.py` gets a
  `TestJsonFeedLocations` case; parity and e2e pass; `events.json` diff shows only the new
  field.
- **Files.** `data/sources.yaml`, `scripts/utils.py`, `scripts/generate_calendar.py`,
  `scripts/geocode_addresses.py`, `docs/index.html`, tests. Takes the `index.html` and
  generator locks.

#### T2.2 String programs become objects; FolkTime hours reach the calendar
- **Problem.** 77 programs across 16 entries are bare strings; nothing validates program
  shape; FolkTime's drop-in hours exist only inside `locations`.
- **Do.** (a) Convert every string program to `{name: <string>}`; where the same entry's
  `hours`, `locations`, or `notes` already state a schedule, add `schedule` and `location`
  (FolkTime: "Drop-in peer support" → two programs, "NE Portland drop-in, Mon/Wed/Thu
  10am-2pm" at 4837 NE Couch St and "Oregon City drop-in, Tuesday 10am-2pm" at 710 6th St;
  use the exact wording from the entry, do not invent hours). (b) `validate_entry()` rejects
  non-mapping programs and programs without `name`. (c) Remove the `typeof p === 'string'`
  branch in `index.html` once the data is clean (small edit; coordinate with the lock).
  (d) Log each entry in `data/audit-log.yaml` as `type: data-shape` without touching
  `last_verified`.
- **Accept.** `audit_check.py --validate` passes; `events.json` has zero string programs;
  FolkTime drop-in hours appear on the calendar grid and in `peer_support.ics`.
- **Entries.** folktime, yoga-on-yamhill, ymca-columbia-willamette, ttad-pools,
  lake-oswego-lorac, hollywood-theatre, naya, artichoke-music, oxbow-regional-park,
  tualatin-river-nwr, bird-alliance-oregon, ppr-community-gardens, multnomah-arts-center,
  portland-art-guild, hidden-creek-community-center, and one more reported by the validator.

#### T3.1 Page snapshots in the URL checker
- **Problem.** The weekly check fetches every page and discards the body; humans re-read
  unchanged pages.
- **Do.** `check_source_urls.py` gains `--snapshots data/url-snapshots.json`: for each
  reachable URL, extract visible text (strip tags, scripts, styles; collapse whitespace;
  drop lines matching a small noise list such as dates, "cookie", nav menus by tag), hash
  it (sha256), and store `{url: {hash, checked, changed_since_verified: bool}}`.
  `changed_since_verified` is true when the hash differs from the hash recorded at the
  entry's `last_verified` date (store `verified_hash` alongside). `audit_check.py
  --weekly-summary` and `--workload` show "source changed" next to entries whose page moved,
  and `audit_complete.py` records the current hash as `verified_hash` when it marks an
  entry audited. Keep the snapshot file deterministic (sorted keys, no timestamps other
  than dates).
- **Accept.** Mocked tests in `test_check_source_urls.py` cover text extraction, hashing,
  and the changed/unchanged decision; the live run `[network]` populates the file.
- **Files.** `scripts/check_source_urls.py`, `scripts/audit_check.py`,
  `scripts/audit_complete.py`, tests, workflow, `data/url-snapshots.json`.

#### T5.1 One calendar-year constant
- **Do.** In `generate_calendar.py` introduce `CALENDAR_YEAR = 2026` and derive
  `CALENDAR_EPOCH` and `DEFAULT_DTSTAMP` from it; add `--year` to override for dry runs;
  write `calendar_year` into `events.json`. In `index.html` (after T2.1 merges), read
  `feed.calendar_year` and use it for the `<title>` suffix, the `<h1>`, the logo `alt`, the
  print minimum date, and the print header; keep the static markup as the fallback for the
  no-JS first paint. Document in `CLAUDE.md` under a new "Year rollover" heading: the one
  constant, `generate_monthly_calendars.py` range (if kept), the OpenGraph title/image, and
  the logo set.
- **Accept.** `grep -c 2026 docs/index.html` is limited to the OpenGraph tags and static
  fallbacks you list in the PR; `generate_calendar.py --year 2027 --json` runs and produces
  the same recurring UIDs as 2026 (assert in a test).

#### T1.5 (see Wave 1; can also land here)

### Wave 3 — schema, split, assisted verification

#### T2.3 Export the remaining hidden fields and surface `TEMPORARILY CLOSED`
- **Do.** Export `services`, `transit`, `languages`, `season`, `status`, `parking`,
  `organizer` in `generate_json_feed()`. In the resource modal render Services (list),
  Getting there (`transit`, `parking`), Languages, Season. Show a badge for
  `status: TEMPORARILY CLOSED` on cards and in the modal, and include the status in the ICS
  description prefix ("TEMPORARILY CLOSED — ") for such entries. Derive
  `audience: spanish_speaking` in `get_entry_audience()` when `languages` mentions Spanish,
  so the Spanish filter returns Oregon Warmline, NW Natural, IRCO.
- **Accept.** Spanish filter returns three entries; Sisters of the Road shows the badge;
  e2e passes.

#### T2.4 Tighten the schema
- **Do.** Add to `scripts/utils.py` an allowlist of entry keys (the documented ones plus
  `locations`, `services`, `transit`, `languages`, `season`, `parking`, `organizer`,
  `status`, `closed_date`, `latitude`, `longitude`, `features`, `eligibility`,
  `apply`/`application` merged to one) and an `extra:` mapping for anything else. Write
  `scripts/migrate_schema_keys.py` (preview by default, `--apply`) that moves one-off keys
  under `extra:` and merges `apply`/`application`, `notes_extra`/`notes_on_access` into
  `notes`. `validate_entry()` warns on unknown top-level keys; `hours` must be a string or a
  mapping of day → string; phone strings normalized to `NNN-NNN-NNNN` (allow `x`
  extensions and the `YOGI` vanity number via a `phone_display` field). Update
  `templates/resource-entry.yaml` and `CLAUDE.md`.
- **Accept.** `--validate` passes after migration; `events.json` unchanged except where
  `extra` is added; generator and guide output byte-identical for untouched entries.

#### T4.2 Split `index.html` into `styles.css` and `app.js`
- **Do.** Move the `<style>` block to `docs/styles.css` and the two inline scripts to
  `docs/app.js` (the logo picker can stay inline; it is six lines). No bundler, no build.
  Preserve execution order (`sky-effect.js` before `app.js`). Export the pure functions the
  tests need (`resolvedScheduleDates`, `localDateFromIso`, `matchesAllFilters`,
  `formatHours`, `escapeHtml`, `phoneHref`) via a `window.PeerCalendar` namespace or a
  guarded `module.exports` so `test_web_schedule_parity.mjs` and `test_web_ui_contract.mjs`
  can `import`/`require` instead of slicing HTML. Replace the `awk` syntax check in
  `test-web-ui.yml` with `node --check docs/app.js`. Update `CLAUDE.md`'s file list.
- **Accept.** All node and e2e tests pass; the page renders identically (compare one
  Playwright screenshot before and after at 1280×800); Lighthouse-equivalent: no new
  render-blocking resource beyond `styles.css`.
- **Lock.** Nothing else may touch `docs/index.html` while this PR is open.

#### T3.2 Assisted verification `[network]`
- **Do.** `scripts/verify_entry.py --id <id>`: fetches each `source_urls` page (reuse the
  checker's fetch, per-host limits, and bot-block detection), extracts candidate facts with
  regexes and simple heuristics (phone numbers, `$` prices and "free", day/time patterns
  reusing `parse_schedule`, street addresses), compares each with the entry, and prints a
  side-by-side report plus a ready-to-run `audit_complete.py --id <id> [--changes "..."]`
  line. Optional `--llm` flag that, when an API key is present, sends the page text and the
  entry YAML to Claude with instructions to return only a JSON diff of changed facts with
  quoted evidence; the script never writes to `sources.yaml` itself. Add
  `--batch critical` to iterate the priority queue from `audit_policy.audit_queue()`.
- **Accept.** Mocked tests for extraction; a dry run on three entries in the PR body with
  the report pasted.

### Wave 4 — audit throughput, UI polish, rollover

#### T3.3 Work the critical backlog `[network]` `[human]`
- **Do.** Using T3.2, verify the 50 critical overdue entries in batches of ~10 per PR,
  peer support first (24), then food (26). Each PR: `audit_complete.py` per entry, changes
  described in `data/audit-log.yaml`, feeds regenerated. Anything that needs a phone call
  goes to issue #4.
- **Accept.** `audit_check.py --workload` shows critical overdue at 0.

#### T3.4 Convert vague peer-support schedules `[network]`
- **Do.** NAMI Washington County (both groups), PFLAG Portland, Prism Moves BIPOC class,
  Disabled Hikers Portland, Every Body Athletics, Willamette Writers. Replace "Contact for
  current schedule" with real recurrences or `dates` lists from the organizer; where the
  organizer publishes none, leave the vague string and add a `practical_tips` line saying
  how to get the schedule.
- **Accept.** `validate_schedules.py` vague count drops by at least 8.

#### T3.5 Staleness tiers and "report a change"
- **Do.** In `app.js`: the verified badge shows three tiers computed from `last_verified`
  and today (≤90 days "Verified <date>", ≤180 "Verified <date> · check before going", older
  "Last verified <date> · may be out of date"); colours from the existing accessible
  palette; tier text in the ICS description is out of scope. Add a "Report a change" link on
  each resource modal that opens a prefilled GitHub issue
  (`https://github.com/lobabobloblaw/peer-calendar/issues/new?title=...&body=...` with the
  entry ID and URL). Add an issue template `.github/ISSUE_TEMPLATE/correction.yml`.
- **Accept.** Contract test asserts the three tier strings; e2e checks the link target.

#### T4.3 Feed and sky-effect weight
- **Do.** Emit `docs/events.min.json` (no indentation) alongside the pretty file; the page
  fetches the min file. In `sky-effect.js`, skip loading Three/Vanta when
  `navigator.connection?.saveData`, when `prefers-reduced-motion`, or on viewports under the
  mobile breakpoint unless the user opts in (keep the CSS gradient sky, which already exists
  as the fallback); add `integrity` attributes to the two CDN script loads (compute the
  SRI hashes for the pinned versions).
- **Accept.** `events.min.json` is at most 60% of `events.json`; reduced-motion e2e still
  passes; a run with a stubbed `saveData: true` never requests the CDN scripts.

#### T4.4 Skip link and small accessibility items
- **Do.** Add a visually-hidden-until-focused "Skip to calendar" link targeting
  `#page-content`; confirm focus order lands on the view tabs. Add `aria-describedby` on the
  verified badge tiers from T3.5.
- **Accept.** axe passes; keyboard-only run reaches the calendar in one Tab.

#### T5.2 Stale-event detection
- **Do.** `audit_check.py --stale-events`: entries or programs whose every `dates` value
  ended more than 60 days ago and that have no future date; `validate_schedules.py` prints
  the same as `[stale]` (warning, not failure). The Seasonal tab hides events whose end date
  is more than 60 days past (the ICS already stops emitting expired windows).
- **Accept.** Running with `--as-of 2027-01-15` lists the 2026 festivals.

#### T5.3 Rollover checklist and dry run
- **Do.** `docs-archive/` is for history; put the checklist in `CLAUDE.md` under "Year
  rollover": bump `CALENDAR_YEAR`, refresh the logo set and OpenGraph image, run
  `--stale-events`, request 2027 dates for the 44 date-sensitive entries, regenerate,
  confirm UIDs of recurring events are unchanged (`diff` of `UID:` lines). Perform the dry
  run with `--year 2027` into `output/` and attach the UID diff (should be empty) to the PR.

### Wave 5 — product enhancements (existing issues)

Do these only after Waves 0–4 have merged. Each is its own PR in `app.js`.

- **T7.1 Print weekly meeting list (#22).** A print mode that lists the next 7 days grouped
  by day, category-coloured bar, name, time, address, phone; reuse `printCalendar()` data
  path. Peer specialists hand these out.
- **T7.2 "New this month" (#21).** `add_update_post.py --auto` already computes added,
  removed, and changed IDs; write them to `docs/changes.json` (rolling 90 days) and render a
  "New this month" strip above the Updates list.
- **T7.3 Per-category subscribe (#15).** When one category filter is active, the Subscribe
  block offers that category's ICS URL for the selected platform.
- **T7.4 PWA shell (#17).** `manifest.webmanifest`, a service worker that caches the shell,
  `styles.css`, `app.js`, and the last `events.min.json`; offline banner. Depends on T4.2
  and T4.3.
- **T7.5 Near-me radius (#13)** and **T7.6 weather tags (#16)**: lower priority; near-me
  needs geolocation consent UI; weather tags reuse the Open-Meteo call already made by
  `sky-effect.js`.
- **T7.7 Submit-an-event form (#20)**: partly covered by T3.5's prefilled issue; extend the
  template with the fields from `templates/resource-entry.yaml`.

## 3. Kickoff prompt for the agent

Paste this to start a session:

> You are working in `lobabobloblaw/peer-calendar`. Read `AGENTS.md`, `CLAUDE.md`,
> `project-review-2026-09-02.md`, and `orchestration-2026-09.md`. Execute the orchestration
> in wave order, one pull request per task, honouring the ground rules in section 0 and the
> conflict map. Start with T0.1 and T0.2 and open that PR before anything else. Then take
> every Wave 1 task that does not need network, in parallel branches. Before each push run
> the check list; paste the command output summary into the PR body. When a task needs
> network or a human, do the part that does not and leave a "Remaining" section in the PR
> body. Do not start a task whose lock file is touched by an open PR. Report at the end of
> each wave: PRs opened, what was skipped and why, and any finding you filed as an issue.

## 4. Definition of done for the whole plan

- Sept 7 and every later scheduled run is green, and a failed scheduled run opens an issue.
- PRs cannot merge with invalid data or schedules.
- FolkTime and every multi-location entry is on the map; no string programs remain.
- `audit_check.py --workload` shows zero critical overdue and the weekly summary lists
  changed source pages and broken URLs beside the entries they belong to.
- `docs/` is under 5MB, `index.html` is markup only, and the page loads without Three.js
  on data-saver connections.
- The 2027 rollover is a one-constant change with a written checklist and a passing dry run.
