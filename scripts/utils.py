"""Shared utilities for Portland Metro Resources scripts."""

import sys
from datetime import date, datetime
from pathlib import Path

import yaml


def load_sources(sources_path: str | Path) -> list[dict]:
    """Load and parse the sources.yaml file (multi-document YAML)."""
    with open(sources_path, "r", encoding="utf-8") as f:
        content = f.read()

    documents = []
    for doc in yaml.safe_load_all(content):
        if doc and isinstance(doc, list):
            documents.extend(doc)
        elif doc and isinstance(doc, dict):
            documents.append(doc)

    return [d for d in documents if d and isinstance(d, dict) and "id" in d]


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

    res_type = entry.get("resource_type")
    if res_type and res_type not in VALID_RESOURCE_TYPES:
        warnings.append(f"{entry_id}: unknown resource_type '{res_type}'")

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
