# Home Machine Manifest — from the July 24, 2026 review

Everything here needs something this session did not have: **open network access, or a phone.**
The code and structural work is already done and pushed to
`claude/project-review-accuracy-42xldq`. Full findings in `project-review-2026-07-24.md`.

Ordered so the quick wins come first.

---

## 0. Before anything — 2 min

```bash
cd ~/peer-calendar
git fetch origin && git checkout claude/project-review-accuracy-42xldq
source scripts/venv/bin/activate
python scripts/test_schedule_parsing.py     # expect 83 tests, OK
python scripts/audit_check.py --validate    # expect clean
python scripts/validate_schedules.py        # expect 0 failures, 2 unanchored biweekly
```

If all three are green, the branch is good to merge. **Merging republishes the calendar feeds** —
263 events, with 37 previously-wrong recurring dates corrected and 7 festivals moved back from
2027. Existing subscribers pick the corrections up automatically.

---

## 1. Geocoding — 10 min, mostly waiting

36 entries have a street address but no coordinates, so they are missing from the map.

```bash
python scripts/geocode_addresses.py --preview   # see what it would do
python scripts/geocode_addresses.py             # ~1 sec/address via Nominatim
python scripts/geocode_addresses.py --check-bounds
python scripts/generate_calendar.py --json --publish
```

Roughly half of the 36 are genuinely un-geocodable ("Statewide", "Various parks", a P.O. box)
and will be skipped. The real ones worth confirming landed:

- `nami-multnomah` — 464 SE 185th Ave, Suite 315, Portland 97233
- `decompress-connect-meditation` — TaborSpace, 5441 SE Belmont St
- `south-barlow-berries` — 29190 S Barlow Rd, Canby
- `five-oaks-museum` — skip, it is closed and no longer published

---

## 2. Phone calls — ~45 min

The one that matters most is first. Each row's `⚠️ VERIFY` flag in `sources.yaml` has the full
context.

### 2a. DDA Oregon — **call both numbers**, five open flags since March

- **503-737-4126** (what the website shows, confirmed Feb 2026)
- **503-222-6484** (what we have stored)

Ask:
1. Which number is current?
2. Is the office still at the stored address, or has it moved to **4141 SE Division St**?
3. Current meeting schedule. The national directory (ddainc.org) lists **Fora Health Mon 3pm**
   and **Oregon Change Clinic Tue/Thu 12pm**, which do not match what we publish.
4. Is the **DDA meeting at FolkTime** (4837 NE Couch, Tue 2-3pm) still running?
5. Is there a **virtual Sat 10:30-11:30am** meeting? It is not on ddaoregon.com. The
   **Sat 10-11am at Alano Club** is confirmed via portlandalano.org.

ddaoregon.com's copyright still reads 2008, so treat the site as unreliable and go with the phone.

### 2b. Sisters of the Road Café

Closed since April 2026, looking for a new permanent location. Any reopening news or interim
location? If it is not coming back, change the flag to `❌ CLOSED` with `status: CLOSED` and it
will drop out of the feeds automatically.

### 2c. Sikh Center langar — **971-217-8577**

Confirm the **Friday 8pm** langar. It is not on the website schedule page.

### 2d. 4D Recovery

`SESSION_STATE.md` has recorded "may be temporarily closed/relocating" since January and it was
never resolved. Confirm open/closed and the drop-in hours.

### 2e. NAMI Clackamas — Women's group

Wix site, could not be read automatically. Confirm the day and time.

### 2f. Two biweekly events — need **one real meeting date each**

Without it they land on the wrong week half the time. Add `schedule_start_date: YYYY-MM-DD`
set to an actual meeting date; `validate_schedules.py` will stop flagging them.

- `gresham-senior-center > Monday Movie Matinees` — "Every other Monday 1-3pm"
- `shift-to-bikes > Foster Night Ride` — "Every other Tuesday"

---

## 3. Web checks — ~45 min

Four entries are already flagged in the data; just refresh and clear the flag.

| Entry | Where | What to get |
|---|---|---|
| `thprd-fitness-in-park` | thprd.org/fitness-in-the-park | **Current session's class list.** The six classes we have ended March 22 and are correctly no longer published, so this entry is currently contributing nothing to the calendar. |
| `pcc-art-galleries` | pcc.edu/galleries | 2026-27 exhibit schedule. The last one we have closed May 27. |
| `multnomah-discovery-pass` | multcolib.org/my-discovery-pass | **Re-check the whole venue list.** It still lists Five Oaks Museum, which closed in April 2025 — so it is stale, and probably not only there. |
| `tualatin-heritage-center` | tualatinheritagecenter.org | 2026 line-up. Programs still carry 2025 dates (Fossil Fest Aug 2 2025, Heritage Evening Sep 5 2025). |
| `lloyd-center-walking` | — | Lloyd Center closes by end of 2026, demolition approved. If a date is announced, add `schedule_end_date`. |

### Optional but high value: Alano Club schedules

`alano-club-portland` stores seven recovery meeting groups as "Weekly meetings" / "Multiple
weekly meetings", so **none of them reach the calendar**. Real schedules are on
portlandalano.org. This is the single largest peer-support coverage gap.

---

## 4. The audit backlog — needs a decision, not just time

**185 of 269 entries (69%) are past their audit date**, the oldest by 74 days.

| Frequency | Overdue |
|---|---|
| quarterly | 162 |
| annually | 12 |
| monthly | 11 |

```bash
python scripts/audit_check.py --weekly-summary
python scripts/audit_check.py --overdue
```

Do the **11 monthly ones first** — monthly cadence was assigned to things that actually change.

Then a call to make: 162 quarterly entries is ~54 audits a month, which the documented 15-30
minute weekly session cannot absorb. Two options, not exclusive:

1. **Re-tier.** Park addresses and library branch hours do not change quarterly. Moving the
   stable ones to `annually` would bring the load into range.
2. **Automate the cheap half.** A link-checker in CI catches dead URLs and moved pages with no
   human time, leaving people to verify what only a person can — whether a group still meets,
   whether the price changed. Worth doing regardless; I could not run one here because the
   sandbox blocks all 418 source URLs.

---

## 5. Housekeeping — your call, I did not touch these

Each is a deletion, so I left them for you.

- **`data/sources-deduped.yaml`** (212K) and **`data/sources-backup-2025-12-03.yaml`** (244K)
  are stale near-copies sitting next to the master file. Editing the wrong one would be easy
  and hard to notice. Git already has the history.
- **~14MB of unreferenced assets in `docs/`**: `cakes/` (7.4M), `calendar-logos/` (6.3M),
  `weather-test.html`, `2026.png`, `2026psc.png`, `screenshot.jpeg`. Nothing links to them and
  every clone pays for them.
- **Three legacy hand-maintained guides** — `activities-guide-1.md`, `activities-guide-2.md`,
  `food_farms-guide.md` — now that `resources-guide.md` is generated in CI. Note that
  `guide_location` fields throughout `sources.yaml` still point at the old filenames, so either
  retire them and update those fields, or say in CLAUDE.md that they are frozen copies.

---

## 6. One larger idea, if you want it

`docs/index.html` re-implements `parse_schedule` in JavaScript. The two copies had **drifted
into 12 disagreements** before this review — that is how the recovery drop-in centre ended up
showing Mon/Fri instead of Mon-Fri on the site. They agree now, and nothing enforces it.

The durable fix is to have `generate_calendar.py` write resolved days and times into
`events.json` so the browser never parses a schedule string. That deletes the duplication
rather than policing it. Maybe half a day's work, and it would need a careful pass over the
calendar, list, and seasonal views. Say the word and I will do it.
