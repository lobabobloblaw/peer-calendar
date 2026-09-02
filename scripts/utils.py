"""Shared utilities for Portland Metro Resources scripts."""

import re
import sys
from datetime import date, datetime
from pathlib import Path

import yaml


def parse_sources(content: str) -> list[dict]:
    """Parse sources from multi-document YAML text."""
    documents = []
    for doc in yaml.safe_load_all(content):
        if doc and isinstance(doc, list):
            documents.extend(doc)
        elif doc and isinstance(doc, dict):
            documents.append(doc)

    return [d for d in documents if d and isinstance(d, dict) and "id" in d]


def load_sources(sources_path: str | Path) -> list[dict]:
    """Load and parse the sources.yaml file (multi-document YAML)."""
    with open(sources_path, "r", encoding="utf-8") as f:
        return parse_sources(f.read())


def parse_date(date_val) -> date | None:
    """Parse a date value to a date object."""
    if isinstance(date_val, date) and not isinstance(date_val, datetime):
        return date_val
    if isinstance(date_val, datetime):
        return date_val.date()
    if isinstance(date_val, str):
        try:
            return datetime.strptime(date_val, "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def format_date(date_val) -> str:
    """Format a date value for display."""
    if isinstance(date_val, datetime):
        return date_val.strftime("%Y-%m-%d")
    elif isinstance(date_val, date):
        return date_val.strftime("%Y-%m-%d")
    elif isinstance(date_val, str):
        return date_val
    return str(date_val) if date_val else "N/A"


def get_default_sources_path() -> Path:
    """Return the default path to sources.yaml."""
    return Path(__file__).parent.parent / "data" / "sources.yaml"


VALID_CATEGORIES = {
    "parks_nature", "arts_culture", "fitness_wellness", "food_farms",
    "events", "peer_support", "social_activities", "discount_programs",
    "transportation",
}

VALID_LOCATION_TYPES = {"physical", "virtual", "hybrid", "online_service", "varies"}
VALID_RESOURCE_TYPES = {"place", "event", "service", "program", "organization"}

REQUIRED_FIELDS = ["id", "name", "category"]


VALID_AUDIT_FREQUENCIES = {"weekly", "monthly", "quarterly", "annually"}

VALID_ACCESSIBILITY = {
    "wheelchair_accessible", "transit_nearby", "elevator", "asl_available",
    "hearing_loop", "scent_free", "low_vision_friendly", "gender_neutral_restroom",
    "sliding_scale", "varies",
}

VALID_GOOD_FOR = {
    "anxiety_friendly", "grief", "isolation", "new_to_area", "low_energy",
    "active", "creative", "outdoor", "indoor", "family_friendly",
}

VALID_AUDIENCES = {
    "children", "teens", "young_adults", "seniors", "women", "lgbtq",
    "trans_nonbinary", "bipoc", "spanish_speaking",
}

VALID_SOCIAL_INTENSITY = {
    "solo", "drop_in", "casual_group", "structured_group", "one_on_one", "varies",
}

TAG_VOCABULARIES = {
    "accessibility": VALID_ACCESSIBILITY,
    "good_for": VALID_GOOD_FOR,
    "audience": VALID_AUDIENCES,
}

# Fields the calendar/guide scripts read. A key like `dates_2026` looks
# meaningful in the YAML but is silently ignored by every consumer, so any
# year-suffixed variant of a real field is flagged.
YEAR_SUFFIX_RE = re.compile(r"_(19|20)\d{2}(_(19|20)\d{2})?$")


def validate_entry(entry: dict) -> list[str]:
    """Validate a single entry and return a list of warnings."""
    warnings = []
    entry_id = entry.get("id", "<no id>")

    for field in REQUIRED_FIELDS:
        if not entry.get(field):
            warnings.append(f"{entry_id}: missing required field '{field}'")

    category = entry.get("category")
    if category and category not in VALID_CATEGORIES:
        warnings.append(f"{entry_id}: unknown category '{category}'")

    loc_type = entry.get("location_type")
    if loc_type and loc_type not in VALID_LOCATION_TYPES:
        warnings.append(f"{entry_id}: unknown location_type '{loc_type}'")
    elif not loc_type:
        warnings.append(f"{entry_id}: missing location_type")

    res_type = entry.get("resource_type")
    if res_type and res_type not in VALID_RESOURCE_TYPES:
        warnings.append(f"{entry_id}: unknown resource_type '{res_type}'")

    # Import lazily to avoid a module cycle: audit_policy uses parse_date above.
    from audit_policy import validate_audit_policy
    warnings.extend(validate_audit_policy(entry))

    if not entry.get("source_urls"):
        warnings.append(f"{entry_id}: missing source_urls")

    start = entry.get("schedule_start_date")
    end = entry.get("schedule_end_date")
    if start and end:
        s = parse_date(start)
        e = parse_date(end)
        if s and e and e < s:
            warnings.append(f"{entry_id}: schedule_end_date is before schedule_start_date")

    for field, vocabulary in TAG_VOCABULARIES.items():
        values = entry.get(field) or []
        if isinstance(values, str):
            values = [values]
        for value in values:
            if value not in vocabulary:
                warnings.append(f"{entry_id}: unknown {field} tag '{value}'")

    social = entry.get("social_intensity")
    if social and social not in VALID_SOCIAL_INTENSITY:
        warnings.append(f"{entry_id}: unknown social_intensity '{social}'")

    for key in entry:
        if YEAR_SUFFIX_RE.search(key):
            warnings.append(
                f"{entry_id}: field '{key}' is year-suffixed and is ignored by every "
                f"script - use the unsuffixed field (e.g. 'dates') instead"
            )

    programs = entry.get("programs")
    if programs is not None and not isinstance(programs, list):
        # A mapping here renders as nothing at all: the site tests
        # programs.length, which is undefined for an object, so the whole
        # catalogue silently disappears.
        warnings.append(
            f"{entry_id}: 'programs' must be a list, not "
            f"{type(programs).__name__} - a mapping is dropped by every consumer"
        )
        programs = []

    for program in programs or []:
        if not isinstance(program, dict):
            # A bare string program carries no schedule, so it can never reach
            # the calendar, and it suppressed the entry's own schedule too.
            warnings.append(
                f"{entry_id}: program {program!r} must be a mapping - "
                f"write it as '- name: {program}'"
            )
            continue
        if not program.get("name"):
            warnings.append(f"{entry_id}: a program is missing its 'name'")
        label = program.get("name", "<unnamed program>")
        for key in program:
            if YEAR_SUFFIX_RE.search(key):
                warnings.append(
                    f"{entry_id} > {label}: field '{key}' is year-suffixed and is "
                    f"ignored by every script - use the unsuffixed field instead"
                )

    return warnings


def validate_all_entries(entries: list[dict], quiet: bool = False) -> list[str]:
    """Validate all entries and print warnings to stderr. Returns all warnings."""
    all_warnings = []
    for entry in entries:
        all_warnings.extend(validate_entry(entry))

    if all_warnings and not quiet:
        print(f"Validation: {len(all_warnings)} warning(s) in {len(entries)} entries",
              file=sys.stderr)
        for w in all_warnings:
            print(f"  WARNING: {w}", file=sys.stderr)

    return all_warnings
