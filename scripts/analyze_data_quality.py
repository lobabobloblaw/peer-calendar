#!/usr/bin/env python3
"""
Comprehensive data quality and completeness analysis for sources.yaml.

Analyzes:
1. Field completeness (optional fields adoption rates)
2. Category distribution
3. Schedule coverage (parseable vs. vague/missing)
4. Audit freshness (last_verified date distribution)
5. Source URL health
6. Location type & resource type coverage
7. Pricing patterns
8. Enrichment field adoption (peer-specialist-focused fields)

Usage:
    python scripts/analyze_data_quality.py
"""

import re
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

# Ensure scripts/ is on the path so imports work
sys.path.insert(0, str(Path(__file__).parent))

from utils import load_sources, parse_date, VALID_CATEGORIES, VALID_LOCATION_TYPES, VALID_RESOURCE_TYPES


# ---------------------------------------------------------------------------
# Schedule classification helpers (adapted from validate_schedules.py)
# ---------------------------------------------------------------------------

VAGUE_PATTERNS = [
    r"^various", r"^weekly", r"^seasonal", r"^monthly", r"^annual",
    r"^ongoing", r"^by appointment",
    r"contact\b.*\b(schedule|dates?|time)",
    r"check\b.*\b(website|calendar|facebook|meetup|eventbrite|library)",
    r"dates?\s+vary", r"times?\s+vary",
    r"various\s+(dates|times|events|workshops)",
    r"^\d+\+?\s+meetings", r"^multiple\b.*\b(meetings|groups)",
    r"^once\s+(weekly|monthly)", r"^twice\s+monthly", r"^periodic",
    r"summer\s+(evenings?|mornings?)", r"\(was seasonal\)",
    r"^weekend\s+mornings?\s+during", r"year-round\b.*\bcleanups",
    r"exhibitions?\s+per\s+year", r"^24/7", r"^365 days", r"done-in-a-day",
    r"^(january|february|march|april|may|june|july|august|september|october|november|december)(\s+\d+)?(\s*-\s*.+)?$",
    r"^\w+\s*-\s*(january|february|march|april|may|june|july|august|september|october|november|december)(\s|$)",
]
_vague_re = re.compile("|".join(VAGUE_PATTERNS), re.IGNORECASE)


# Minimal day/time detection to classify schedules without importing the full parser
_DAY_RE = re.compile(
    r"\b(sun|mon|tue|wed|thu|fri|sat|sunday|monday|tuesday|wednesday|thursday|friday|saturday|daily|weekday)\b",
    re.IGNORECASE,
)
_TIME_RE = re.compile(r"\d{1,2}(:\d{2})?\s*(am|pm)\b|\bnoon\b|\bmidnight\b", re.IGNORECASE)


def classify_schedule(schedule_str: str | None) -> str:
    """Classify a schedule string as 'parseable', 'vague', 'incomplete', or 'missing'."""
    if not schedule_str or not schedule_str.strip():
        return "missing"
    s = schedule_str.strip()
    if _vague_re.search(s):
        return "vague"
    has_day = bool(_DAY_RE.search(s))
    has_time = bool(_TIME_RE.search(s))
    if has_day and has_time:
        return "parseable"
    if has_day or has_time:
        return "incomplete"
    # Check for ordinal patterns like "1st and 3rd Wednesday"
    if re.search(r"\b(1st|2nd|3rd|4th|last)\b", s, re.IGNORECASE) and _DAY_RE.search(s):
        return "parseable"
    return "vague"


# ---------------------------------------------------------------------------
# Analysis helpers
# ---------------------------------------------------------------------------

def has_field(entry: dict, field: str) -> bool:
    """Return True if an entry has a non-empty value for a field."""
    val = entry.get(field)
    if val is None:
        return False
    if isinstance(val, str) and not val.strip():
        return False
    if isinstance(val, (list, dict)) and len(val) == 0:
        return False
    return True


def has_practical_tips(entry: dict) -> bool:
    """Return True if practical_tips has at least one sub-field populated."""
    tips = entry.get("practical_tips")
    if not tips or not isinstance(tips, dict):
        return False
    return any(v for v in tips.values() if v)


def pricing_model(entry: dict) -> str:
    """Classify the pricing model of an entry."""
    pricing = entry.get("pricing")
    if not pricing:
        return "missing"
    if isinstance(pricing, str):
        desc = pricing.lower()
    elif isinstance(pricing, dict):
        desc = (pricing.get("description", "") or "").lower()
    else:
        return "other"

    if not desc.strip():
        return "missing"
    if "free" in desc and ("donation" in desc or "suggested" in desc):
        return "free/donation-based"
    if "free" in desc:
        return "free"
    if "sliding" in desc or "income" in desc:
        return "sliding-scale/income-based"
    if "discount" in desc or "%" in desc or "off" in desc:
        return "discount-program"
    if "$" in desc:
        if "free" in desc:
            return "free-with-paid-options"
        return "paid"
    if "donation" in desc:
        return "donation-based"
    if "varies" in desc:
        return "varies"
    return "other"


def section_header(title: str):
    width = 70
    print()
    print("=" * width)
    print(f"  {title}")
    print("=" * width)


def sub_header(title: str):
    print(f"\n--- {title} ---")


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------

def main():
    sources_path = Path(__file__).parent.parent / "data" / "sources.yaml"
    entries = load_sources(sources_path)
    total = len(entries)
    today = date.today()

    print(f"Sources YAML Data Quality Analysis")
    print(f"Date: {today}")
    print(f"Total entries: {total}")

    # ------------------------------------------------------------------
    # 1. FIELD COMPLETENESS
    # ------------------------------------------------------------------
    section_header("1. FIELD COMPLETENESS")

    # Required fields
    required_fields = ["id", "name", "category", "website", "last_verified", "next_audit"]
    sub_header("Required / Core Fields")
    for field in required_fields:
        count = sum(1 for e in entries if has_field(e, field))
        pct = count / total * 100
        missing = total - count
        marker = " ***" if missing > 0 else ""
        print(f"  {field:25s}: {count:4d}/{total} ({pct:5.1f}%){' -- ' + str(missing) + ' missing' if missing else ''}{marker}")

    # Optional but important fields
    optional_fields = [
        "phone", "address", "hours", "schedule", "eligibility",
        "audit_frequency", "source_urls", "guide_location", "notes",
    ]
    sub_header("Optional but Important Fields")
    for field in optional_fields:
        count = sum(1 for e in entries if has_field(e, field))
        pct = count / total * 100
        print(f"  {field:25s}: {count:4d}/{total} ({pct:5.1f}%)")

    # Newer / enrichment fields
    enrichment_fields = [
        ("location_type", lambda e: has_field(e, "location_type")),
        ("resource_type", lambda e: has_field(e, "resource_type")),
        ("pricing", lambda e: has_field(e, "pricing")),
        ("accessibility", lambda e: has_field(e, "accessibility")),
        ("accessibility_notes", lambda e: has_field(e, "accessibility_notes")),
        ("social_intensity", lambda e: has_field(e, "social_intensity")),
        ("good_for", lambda e: has_field(e, "good_for")),
        ("audience", lambda e: has_field(e, "audience")),
        ("audience_notes", lambda e: has_field(e, "audience_notes")),
        ("practical_tips (any)", lambda e: has_practical_tips(e)),
        ("practical_tips.first_visit", lambda e: isinstance(e.get("practical_tips"), dict) and bool(e["practical_tips"].get("first_visit"))),
        ("practical_tips.registration", lambda e: isinstance(e.get("practical_tips"), dict) and bool(e["practical_tips"].get("registration"))),
        ("practical_tips.what_to_bring", lambda e: isinstance(e.get("practical_tips"), dict) and bool(e["practical_tips"].get("what_to_bring"))),
        ("practical_tips.good_to_know", lambda e: isinstance(e.get("practical_tips"), dict) and bool(e["practical_tips"].get("good_to_know"))),
        ("latitude", lambda e: e.get("latitude") is not None),
        ("longitude", lambda e: e.get("longitude") is not None),
    ]
    sub_header("Enrichment & Peer-Specialist Fields")
    for label, check_fn in enrichment_fields:
        count = sum(1 for e in entries if check_fn(e))
        pct = count / total * 100
        print(f"  {label:30s}: {count:4d}/{total} ({pct:5.1f}%)")

    # ------------------------------------------------------------------
    # 2. CATEGORY DISTRIBUTION
    # ------------------------------------------------------------------
    section_header("2. CATEGORY DISTRIBUTION")

    cat_counts = Counter(e.get("category", "<none>") for e in entries)
    for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1]):
        bar = "#" * count
        print(f"  {cat:25s}: {count:4d}  {bar}")

    # ------------------------------------------------------------------
    # 3. SCHEDULE COVERAGE
    # ------------------------------------------------------------------
    section_header("3. SCHEDULE COVERAGE")

    schedule_classes = Counter()
    vague_examples = []
    missing_schedule_entries = []
    incomplete_examples = []

    for e in entries:
        # Check both top-level schedule and programs
        top_schedule = e.get("schedule")
        programs = e.get("programs", [])

        if top_schedule:
            cls = classify_schedule(str(top_schedule))
            schedule_classes[cls] += 1
            if cls == "vague":
                vague_examples.append((e["id"], str(top_schedule)))
            elif cls == "incomplete":
                incomplete_examples.append((e["id"], str(top_schedule)))
        elif programs and isinstance(programs, list):
            # Count program-level schedules
            prog_schedules = [p.get("schedule") for p in programs if isinstance(p, dict) and p.get("schedule")]
            if prog_schedules:
                # Classify best schedule among programs
                prog_classes = [classify_schedule(str(s)) for s in prog_schedules]
                if "parseable" in prog_classes:
                    schedule_classes["parseable (program-level)"] += 1
                elif "vague" in prog_classes:
                    schedule_classes["vague (program-level)"] += 1
                else:
                    schedule_classes["incomplete (program-level)"] += 1
            else:
                schedule_classes["missing"] += 1
                missing_schedule_entries.append(e["id"])
        elif e.get("dates"):
            schedule_classes["date-based event"] += 1
        elif e.get("hours"):
            schedule_classes["hours-only (no schedule)"] += 1
        else:
            schedule_classes["missing"] += 1
            missing_schedule_entries.append(e["id"])

    sub_header("Schedule Classification")
    for cls, count in sorted(schedule_classes.items(), key=lambda x: -x[1]):
        pct = count / total * 100
        print(f"  {cls:35s}: {count:4d} ({pct:5.1f}%)")

    if vague_examples:
        sub_header(f"Vague Schedule Examples (showing up to 10 of {len(vague_examples)})")
        for eid, sched in vague_examples[:10]:
            print(f"  {eid:40s}: {sched[:60]}")

    if incomplete_examples:
        sub_header(f"Incomplete Schedule Examples (showing up to 10 of {len(incomplete_examples)})")
        for eid, sched in incomplete_examples[:10]:
            print(f"  {eid:40s}: {sched[:60]}")

    if missing_schedule_entries:
        sub_header(f"Entries With No Schedule/Hours/Dates ({len(missing_schedule_entries)})")
        for eid in missing_schedule_entries:
            name = next((e["name"] for e in entries if e["id"] == eid), eid)
            cat = next((e["category"] for e in entries if e["id"] == eid), "?")
            print(f"  {eid:40s}  [{cat}] {name[:40]}")

    # ------------------------------------------------------------------
    # 4. AUDIT FRESHNESS
    # ------------------------------------------------------------------
    section_header("4. AUDIT FRESHNESS")

    three_months_ago = today - timedelta(days=90)
    six_months_ago = today - timedelta(days=180)
    one_year_ago = today - timedelta(days=365)

    verified_dates = []
    missing_verified = []
    overdue_entries = []

    for e in entries:
        lv = parse_date(e.get("last_verified"))
        na = parse_date(e.get("next_audit"))
        if lv:
            verified_dates.append((e["id"], e.get("name", ""), e.get("category", ""), lv))
        else:
            missing_verified.append(e["id"])

        if na and na < today:
            days_overdue = (today - na).days
            overdue_entries.append((e["id"], e.get("name", ""), e.get("category", ""), na, days_overdue))

    sub_header("Verification Age Distribution")
    if verified_dates:
        ages = [(today - lv).days for _, _, _, lv in verified_dates]
        within_1mo = sum(1 for a in ages if a <= 30)
        within_3mo = sum(1 for a in ages if a <= 90)
        within_6mo = sum(1 for a in ages if a <= 180)
        within_1yr = sum(1 for a in ages if a <= 365)
        older = sum(1 for a in ages if a > 365)

        print(f"  Verified within last month  : {within_1mo:4d} ({within_1mo/total*100:.1f}%)")
        print(f"  Verified within 3 months    : {within_3mo:4d} ({within_3mo/total*100:.1f}%)")
        print(f"  Verified within 6 months    : {within_6mo:4d} ({within_6mo/total*100:.1f}%)")
        print(f"  Verified within 1 year      : {within_1yr:4d} ({within_1yr/total*100:.1f}%)")
        print(f"  Older than 1 year           : {older:4d} ({older/total*100:.1f}%)")
        print(f"  Missing last_verified       : {len(missing_verified):4d} ({len(missing_verified)/total*100:.1f}%)")

        print(f"\n  Oldest verification: {min(ages)} days ago")
        print(f"  Newest verification: {max(ages)} days ago")
        oldest = sorted(verified_dates, key=lambda x: x[3])
        print(f"\n  5 Oldest Verified Entries:")
        for eid, name, cat, lv in oldest[:5]:
            age = (today - lv).days
            print(f"    {eid:35s} [{cat:20s}] verified {lv} ({age}d ago)")

    # Verification by category
    sub_header("Average Verification Age by Category")
    cat_ages = defaultdict(list)
    for eid, name, cat, lv in verified_dates:
        cat_ages[cat].append((today - lv).days)
    for cat in sorted(cat_ages, key=lambda c: sum(cat_ages[c]) / len(cat_ages[c]), reverse=True):
        ages = cat_ages[cat]
        avg = sum(ages) / len(ages)
        print(f"  {cat:25s}: avg {avg:5.0f} days  (range {min(ages)}-{max(ages)})")

    # Overdue audits
    if overdue_entries:
        sub_header(f"Overdue Audits ({len(overdue_entries)} entries)")
        overdue_sorted = sorted(overdue_entries, key=lambda x: -x[4])
        for eid, name, cat, na, days in overdue_sorted[:15]:
            print(f"  {eid:35s} [{cat:15s}] due {na} ({days}d overdue)")
        if len(overdue_sorted) > 15:
            print(f"  ... and {len(overdue_sorted) - 15} more")

    # ------------------------------------------------------------------
    # 5. SOURCE URL HEALTH
    # ------------------------------------------------------------------
    section_header("5. SOURCE URL HEALTH")

    no_source_urls = [e for e in entries if not has_field(e, "source_urls")]
    no_website = [e for e in entries if not has_field(e, "website")]

    print(f"  Entries without source_urls: {len(no_source_urls)}/{total}")
    print(f"  Entries without website:     {len(no_website)}/{total}")

    if no_source_urls:
        sub_header(f"Entries Missing source_urls ({len(no_source_urls)})")
        for e in no_source_urls:
            print(f"  {e['id']:35s} [{e.get('category', '?'):15s}] {e.get('name', '')[:40]}")

    # URL domain distribution
    sub_header("Top Source URL Domains")
    domain_re = re.compile(r"https?://([^/]+)")
    domain_counts = Counter()
    for e in entries:
        for url in (e.get("source_urls") or []):
            m = domain_re.match(str(url))
            if m:
                domain = m.group(1).replace("www.", "")
                domain_counts[domain] += 1
    for domain, count in domain_counts.most_common(20):
        print(f"  {domain:40s}: {count}")

    # HTTP (not HTTPS) URLs
    http_entries = []
    for e in entries:
        for url in (e.get("source_urls") or []) + ([e.get("website")] if e.get("website") else []):
            if str(url).startswith("http://"):
                http_entries.append((e["id"], str(url)))
    if http_entries:
        sub_header(f"Non-HTTPS URLs ({len(http_entries)})")
        for eid, url in http_entries:
            print(f"  {eid:35s}: {url}")

    # ------------------------------------------------------------------
    # 6. LOCATION TYPE & RESOURCE TYPE COVERAGE
    # ------------------------------------------------------------------
    section_header("6. LOCATION TYPE & RESOURCE TYPE COVERAGE")

    loc_type_counts = Counter()
    res_type_counts = Counter()
    missing_loc_type = []
    missing_res_type = []

    for e in entries:
        lt = e.get("location_type")
        rt = e.get("resource_type")
        if lt:
            loc_type_counts[lt] += 1
        else:
            missing_loc_type.append(e["id"])
        if rt:
            res_type_counts[rt] += 1
        else:
            missing_res_type.append(e["id"])

    sub_header("Location Types")
    for lt, count in sorted(loc_type_counts.items(), key=lambda x: -x[1]):
        pct = count / total * 100
        valid = " (valid)" if lt in VALID_LOCATION_TYPES else " *** INVALID ***"
        print(f"  {lt:20s}: {count:4d} ({pct:5.1f}%){valid}")
    print(f"  {'<missing>':20s}: {len(missing_loc_type):4d} ({len(missing_loc_type)/total*100:.1f}%)")

    sub_header("Resource Types")
    for rt, count in sorted(res_type_counts.items(), key=lambda x: -x[1]):
        pct = count / total * 100
        valid = " (valid)" if rt in VALID_RESOURCE_TYPES else " *** INVALID ***"
        print(f"  {rt:20s}: {count:4d} ({pct:5.1f}%){valid}")
    print(f"  {'<missing>':20s}: {len(missing_res_type):4d} ({len(missing_res_type)/total*100:.1f}%)")

    # Cross-tab: category x location_type
    sub_header("Category x Location Type Cross-tab")
    cats = sorted(set(e.get("category", "<none>") for e in entries))
    ltypes = sorted(VALID_LOCATION_TYPES) + ["<missing>"]
    header = f"  {'Category':25s}" + "".join(f"{lt:>12s}" for lt in ltypes)
    print(header)
    print("  " + "-" * (25 + 12 * len(ltypes)))
    for cat in cats:
        row = f"  {cat:25s}"
        for lt in ltypes:
            if lt == "<missing>":
                count = sum(1 for e in entries if e.get("category") == cat and not e.get("location_type"))
            else:
                count = sum(1 for e in entries if e.get("category") == cat and e.get("location_type") == lt)
            row += f"{count:12d}"
        print(row)

    # ------------------------------------------------------------------
    # 7. PRICING PATTERNS
    # ------------------------------------------------------------------
    section_header("7. PRICING PATTERNS")

    pricing_models = Counter()
    missing_pricing_entries = []
    for e in entries:
        model = pricing_model(e)
        pricing_models[model] += 1
        if model == "missing":
            missing_pricing_entries.append(e)

    sub_header("Pricing Model Distribution")
    for model, count in sorted(pricing_models.items(), key=lambda x: -x[1]):
        pct = count / total * 100
        print(f"  {model:30s}: {count:4d} ({pct:5.1f}%)")

    # Pricing by category
    sub_header("Pricing by Category")
    for cat in sorted(VALID_CATEGORIES):
        cat_entries = [e for e in entries if e.get("category") == cat]
        if not cat_entries:
            continue
        models = Counter(pricing_model(e) for e in cat_entries)
        parts = ", ".join(f"{m}: {c}" for m, c in models.most_common())
        print(f"  {cat:25s} ({len(cat_entries):3d}): {parts}")

    if missing_pricing_entries:
        sub_header(f"Entries Missing Pricing ({len(missing_pricing_entries)})")
        for e in missing_pricing_entries[:20]:
            print(f"  {e['id']:35s} [{e.get('category', '?'):15s}] {e.get('name', '')[:40]}")
        if len(missing_pricing_entries) > 20:
            print(f"  ... and {len(missing_pricing_entries) - 20} more")

    # ------------------------------------------------------------------
    # 8. ENRICHMENT FIELD ADOPTION (PEER-SPECIALIST FIELDS)
    # ------------------------------------------------------------------
    section_header("8. ENRICHMENT FIELD ADOPTION")

    sub_header("Enrichment Completeness by Category")
    enrichment_checks = {
        "practical_tips": has_practical_tips,
        "accessibility": lambda e: has_field(e, "accessibility"),
        "access_notes": lambda e: has_field(e, "accessibility_notes"),
        "social_int": lambda e: has_field(e, "social_intensity"),
        "good_for": lambda e: has_field(e, "good_for"),
        "audience": lambda e: has_field(e, "audience"),
        "geocoded": lambda e: e.get("latitude") is not None,
    }

    header = f"  {'Category':25s}" + "".join(f"{k:>13s}" for k in enrichment_checks)
    print(header)
    print("  " + "-" * (25 + 13 * len(enrichment_checks)))
    for cat in sorted(VALID_CATEGORIES):
        cat_entries = [e for e in entries if e.get("category") == cat]
        if not cat_entries:
            continue
        row = f"  {cat:25s}"
        for label, check_fn in enrichment_checks.items():
            count = sum(1 for e in cat_entries if check_fn(e))
            pct = count / len(cat_entries) * 100
            row += f"{count:4d}/{len(cat_entries):3d} {pct:4.0f}%"
        print(row)

    # Overall enrichment score per entry
    sub_header("Enrichment Score Distribution (0-7 fields present)")
    scores = []
    for e in entries:
        score = sum(1 for check_fn in enrichment_checks.values() if check_fn(e))
        scores.append((score, e["id"], e.get("name", "")))

    score_dist = Counter(s for s, _, _ in scores)
    for score in range(8):
        count = score_dist.get(score, 0)
        bar = "#" * count
        print(f"  Score {score}: {count:4d}  {bar}")

    avg_score = sum(s for s, _, _ in scores) / total
    print(f"\n  Average enrichment score: {avg_score:.2f} / 7")

    # Least enriched entries
    low_scores = sorted(scores, key=lambda x: x[0])
    sub_header("Least Enriched Entries (score 0-1)")
    shown = 0
    for score, eid, name in low_scores:
        if score > 1:
            break
        cat = next((e.get("category", "?") for e in entries if e["id"] == eid), "?")
        print(f"  score={score}  {eid:35s} [{cat:15s}] {name[:40]}")
        shown += 1
        if shown >= 20:
            remaining = sum(1 for s, _, _ in low_scores if s <= 1) - 20
            if remaining > 0:
                print(f"  ... and {remaining} more")
            break

    # Accessibility tag distribution
    sub_header("Accessibility Tag Usage")
    acc_tags = Counter()
    for e in entries:
        tags = e.get("accessibility") or []
        if isinstance(tags, list):
            for t in tags:
                acc_tags[t] += 1
    for tag, count in sorted(acc_tags.items(), key=lambda x: -x[1]):
        print(f"  {tag:30s}: {count}")

    # good_for tag distribution
    sub_header("Good-For Tag Usage")
    gf_tags = Counter()
    for e in entries:
        tags = e.get("good_for") or []
        if isinstance(tags, list):
            for t in tags:
                gf_tags[t] += 1
    for tag, count in sorted(gf_tags.items(), key=lambda x: -x[1]):
        print(f"  {tag:30s}: {count}")

    # Social intensity distribution
    sub_header("Social Intensity Distribution")
    si_counts = Counter(e.get("social_intensity", "<missing>") for e in entries)
    for si, count in sorted(si_counts.items(), key=lambda x: -x[1]):
        pct = count / total * 100
        print(f"  {si:25s}: {count:4d} ({pct:5.1f}%)")

    # Audience tag distribution
    sub_header("Audience Tag Usage")
    aud_tags = Counter()
    entries_with_audience = 0
    for e in entries:
        tags = e.get("audience") or []
        if isinstance(tags, list) and tags:
            entries_with_audience += 1
            for t in tags:
                aud_tags[t] += 1
        elif isinstance(tags, str) and tags:
            entries_with_audience += 1
            aud_tags[tags] += 1
    print(f"  Entries with audience tags: {entries_with_audience}/{total} ({entries_with_audience/total*100:.1f}%)")
    for tag, count in sorted(aud_tags.items(), key=lambda x: -x[1]):
        print(f"  {tag:30s}: {count}")

    # ------------------------------------------------------------------
    # SUMMARY
    # ------------------------------------------------------------------
    section_header("SUMMARY & RECOMMENDATIONS")

    # Compute key metrics
    has_phone_pct = sum(1 for e in entries if has_field(e, "phone")) / total * 100
    has_hours_pct = sum(1 for e in entries if has_field(e, "hours")) / total * 100
    has_tips_pct = sum(1 for e in entries if has_practical_tips(e)) / total * 100
    has_access_pct = sum(1 for e in entries if has_field(e, "accessibility")) / total * 100
    has_social_pct = sum(1 for e in entries if has_field(e, "social_intensity")) / total * 100
    has_goodfor_pct = sum(1 for e in entries if has_field(e, "good_for")) / total * 100
    has_geocode_pct = sum(1 for e in entries if e.get("latitude") is not None) / total * 100
    has_loctype_pct = sum(1 for e in entries if has_field(e, "location_type")) / total * 100
    has_restype_pct = sum(1 for e in entries if has_field(e, "resource_type")) / total * 100
    overdue_pct = len(overdue_entries) / total * 100

    print(f"\n  Database size: {total} entries across {len(cat_counts)} categories")
    print(f"  Average enrichment score: {avg_score:.2f}/7")
    print()

    strengths = []
    if has_loctype_pct > 90:
        strengths.append(f"location_type coverage: {has_loctype_pct:.0f}%")
    if has_tips_pct > 50:
        strengths.append(f"practical_tips coverage: {has_tips_pct:.0f}%")
    if has_access_pct > 50:
        strengths.append(f"accessibility tags: {has_access_pct:.0f}%")

    gaps = []
    if has_phone_pct < 80:
        gaps.append(f"phone numbers: only {has_phone_pct:.0f}%")
    if has_hours_pct < 50:
        gaps.append(f"hours field: only {has_hours_pct:.0f}%")
    if has_geocode_pct < 80:
        gaps.append(f"geocoded locations: only {has_geocode_pct:.0f}%")
    if has_tips_pct < 50:
        gaps.append(f"practical_tips: only {has_tips_pct:.0f}%")
    if has_social_pct < 50:
        gaps.append(f"social_intensity: only {has_social_pct:.0f}%")
    if overdue_pct > 20:
        gaps.append(f"overdue audits: {len(overdue_entries)} entries ({overdue_pct:.0f}%)")

    if strengths:
        print("  STRENGTHS:")
        for s in strengths:
            print(f"    + {s}")

    if gaps:
        print("\n  GAPS TO ADDRESS:")
        for g in gaps:
            print(f"    - {g}")

    print()


if __name__ == "__main__":
    main()
