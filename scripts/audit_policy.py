"""Risk-based audit cadence policy and workload calculations."""

from __future__ import annotations

from collections import Counter
from datetime import date

from dateutil.relativedelta import relativedelta

from utils import parse_date


AUDIT_PRIORITIES = ("critical", "high", "standard", "low")
RISK_RANK = {risk: rank for rank, risk in enumerate(AUDIT_PRIORITIES)}
CADENCE_PER_YEAR = {
    "weekly": 52,
    "monthly": 12,
    "quarterly": 4,
    "annually": 1,
}


def cadence_deadline(frequency: str, from_date: date) -> date:
    """Return the latest permitted audit date for a cadence."""
    offsets = {
        "weekly": relativedelta(weeks=1),
        "monthly": relativedelta(months=1),
        "quarterly": relativedelta(months=3),
        "annually": relativedelta(years=1),
    }
    try:
        return from_date + offsets[frequency]
    except KeyError as exc:
        raise ValueError(f"unknown audit frequency: {frequency}") from exc


def validate_audit_policy(entry: dict, as_of: date | None = None) -> list[str]:
    """Validate audit dates without treating legacy custom timing as invalid."""
    if entry.get("status") == "CLOSED":
        return []

    as_of = as_of or date.today()
    entry_id = entry.get("id", "<no id>")
    warnings = []
    frequency = entry.get("audit_frequency")
    verified = parse_date(entry.get("last_verified"))
    next_audit = parse_date(entry.get("next_audit"))

    if frequency not in CADENCE_PER_YEAR:
        warnings.append(f"{entry_id}: missing or unknown audit_frequency '{frequency}'")
    if not verified:
        warnings.append(f"{entry_id}: invalid last_verified date")
    elif verified > as_of:
        warnings.append(f"{entry_id}: last_verified is in the future")
    if not next_audit:
        warnings.append(f"{entry_id}: invalid next_audit date")
    elif verified and next_audit < verified:
        warnings.append(f"{entry_id}: next_audit is before last_verified")
    return warnings


def is_flagged(entry: dict) -> bool:
    """Return whether an entry explicitly needs verification or follow-up."""
    return any("VERIFY" in str(flag).upper() for flag in entry.get("flags", []))


def has_open_recurring_schedule(entry: dict) -> bool:
    """Return whether a parseable open recurrence reaches published calendars."""
    # This stays a lazy import because generate_calendar itself imports utils,
    # whose validator imports this module only when validation actually runs.
    from generate_calendar import parse_schedule, resolve_recurring_schedule

    programs = entry.get("programs", [])
    if not programs:
        if entry.get("dates") or not entry.get("schedule") or entry.get("schedule_end_date"):
            return False
        return bool(resolve_recurring_schedule(parse_schedule(entry["schedule"]), entry))

    for program in programs:
        if not isinstance(program, dict) or not program.get("schedule"):
            continue
        if program.get("dates"):
            continue
        effective = dict(entry)
        for field in ("schedule_start_date", "schedule_end_date"):
            if program.get(field):
                effective[field] = program[field]
        if effective.get("schedule_end_date"):
            continue
        if resolve_recurring_schedule(parse_schedule(program["schedule"]), effective):
            return True
    return False


STANDARD_PRIORITY_IDS = {
    "lloyd-center-walking", "thprd-fitness-in-park", "st-james-bach",
    "tualatin-heritage-center", "pcc-art-galleries", "pcc-theatre",
    "mhcc-visual-arts-gallery", "willamette-writers", "repair-pdx",
    "clackamas-county-repair-fairs", "lone-fir-cemetery-tours",
    "hawthorne-plaza-concerts",
}


def audit_priority(entry: dict) -> str:
    """Derive review priority from access consequence and data volatility."""
    category = entry.get("category")
    resource_type = entry.get("resource_type")
    if category == "peer_support" or (
        category == "food_farms" and resource_type in {"service", "organization"}
    ):
        return "critical"
    if category in {"discount_programs", "transportation"} or has_open_recurring_schedule(entry):
        return "high"
    if entry.get("id") in STANDARD_PRIORITY_IDS:
        return "standard"
    return "low"


def audit_queue(entries: list[dict], as_of: date | None = None) -> list[dict]:
    """Return active due entries ordered by flag, risk, and due date."""
    as_of = as_of or date.today()
    due = []
    for entry in entries:
        if entry.get("status") == "CLOSED":
            continue
        due_date = parse_date(entry.get("next_audit"))
        if due_date and due_date <= as_of:
            due.append(entry)
    return sorted(
        due,
        key=lambda entry: (
            not is_flagged(entry),
            RISK_RANK[audit_priority(entry)],
            parse_date(entry.get("next_audit")) or date.max,
            entry.get("name", ""),
        ),
    )


def workload_summary(
    entries: list[dict], capacity_per_week: float | None = None, as_of: date | None = None
) -> dict:
    """Calculate steady-state workload and whether a backlog is recoverable."""
    as_of = as_of or date.today()
    active = [entry for entry in entries if entry.get("status") != "CLOSED"]
    frequencies = Counter(entry.get("audit_frequency") for entry in active)
    risks = Counter(audit_priority(entry) for entry in active)
    audits_per_year = sum(
        frequencies.get(frequency, 0) * rate
        for frequency, rate in CADENCE_PER_YEAR.items()
    )
    audits_per_week = audits_per_year / 52
    backlog = len(audit_queue(active, as_of))
    result = {
        "as_of": as_of.isoformat(),
        "active_entries": len(active),
        "backlog": backlog,
        "by_frequency": dict(sorted(frequencies.items())),
        "by_priority": {priority: risks.get(priority, 0) for priority in AUDIT_PRIORITIES},
        "audits_per_year": audits_per_year,
        "audits_per_month": audits_per_year / 12,
        "audits_per_week": audits_per_week,
    }
    if capacity_per_week is not None:
        surplus = capacity_per_week - audits_per_week
        result.update(
            capacity_per_week=capacity_per_week,
            utilization=(audits_per_week / capacity_per_week if capacity_per_week else None),
            weekly_surplus=surplus,
            backlog_recoverable=surplus > 0,
            weeks_to_clear=(backlog / surplus if surplus > 0 else None),
        )
    return result
