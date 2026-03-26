#!/usr/bin/env python3
"""Geocode addresses in sources.yaml using OpenStreetMap Nominatim.

Adds latitude/longitude fields to entries with addresses. Respects Nominatim's
usage policy (1 request per second, identifies via User-Agent).

Usage:
    python geocode_addresses.py                # Geocode entries missing coordinates
    python geocode_addresses.py --force        # Re-geocode all entries
    python geocode_addresses.py --preview      # Show what would be geocoded (no writes)
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path

import yaml

from utils import load_sources, get_default_sources_path

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "PeerSupportCalendar/1.0 (avoigt@folktime.org)"
CACHE_FILE = Path(__file__).parent / "geocode_cache.json"


def load_cache() -> dict:
    """Load geocoding cache from disk."""
    if CACHE_FILE.exists():
        with open(CACHE_FILE) as f:
            return json.load(f)
    return {}


def save_cache(cache: dict) -> None:
    """Save geocoding cache to disk."""
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)


def clean_address(address: str) -> str:
    """Clean an address for better geocoding results."""
    import re
    addr = address
    # Remove parenthetical notes: "(Alano Club)", "(near N Lombard)", "(Room AC1305)"
    addr = re.sub(r'\s*\([^)]*\)', '', addr)
    # Remove suite/room/floor numbers
    addr = re.sub(r',?\s*(Suite|Ste|Room|Rm|Floor|Fl|PMB|Unit)\s*#?\s*\w+', '', addr, flags=re.I)
    # Remove "2nd Floor", "3rd Floor" etc
    addr = re.sub(r',?\s*\d+(st|nd|rd|th)\s+Floor', '', addr, flags=re.I)
    # Remove venue name prefixes before the street number
    # e.g., "Keen Garage, 505 NW 13th Ave" → "505 NW 13th Ave"
    # Only if there's a clear street number following
    addr = re.sub(r'^[^,]+,\s*(\d+\s+\w)', r'\1', addr)
    # Remove trailing venue names after state abbreviation or zip
    addr = re.sub(r'(OR\s+\d{5}(-\d{4})?)\s*\(.*$', r'\1', addr)
    # Remove extended zip code
    addr = re.sub(r'-\d{4}\b', '', addr)
    return addr.strip().strip(',').strip()


def _query_nominatim(query: str) -> tuple[float, float] | None:
    """Send a single query to Nominatim. Returns (lat, lng) or None."""
    params = urllib.parse.urlencode({
        "q": query,
        "format": "json",
        "limit": 1,
        "countrycodes": "us",
    })
    url = f"{NOMINATIM_URL}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        print(f"    Error: {e}", file=sys.stderr)
        return None
    finally:
        time.sleep(1.1)  # Respect rate limit

    if data:
        return (float(data[0]["lat"]), float(data[0]["lon"]))
    return None


def geocode_address(address: str, cache: dict) -> tuple[float, float] | None:
    """Geocode a single address. Tries cleaned version if original fails."""
    if address in cache:
        result = cache[address]
        if result:
            return (result["lat"], result["lng"])
        # Cache has None — check if cleaned version would be different
        cleaned = clean_address(address)
        if cleaned != address and cleaned in cache and cache[cleaned]:
            return (cache[cleaned]["lat"], cache[cleaned]["lng"])
        return None

    # Try original address
    result = _query_nominatim(address)
    if result:
        cache[address] = {"lat": result[0], "lng": result[1]}
        return result

    # Try cleaned address
    cleaned = clean_address(address)
    if cleaned != address:
        result = _query_nominatim(cleaned)
        if result:
            cache[address] = {"lat": result[0], "lng": result[1]}
            return result

    cache[address] = None
    return None


def main():
    parser = argparse.ArgumentParser(description="Geocode addresses in sources.yaml")
    parser.add_argument("--sources", type=Path, default=get_default_sources_path())
    parser.add_argument("--force", action="store_true", help="Re-geocode all entries")
    parser.add_argument("--preview", action="store_true", help="Preview only, no writes")
    args = parser.parse_args()

    entries = load_sources(args.sources)
    cache = load_cache()
    print(f"Loaded {len(entries)} entries, {len(cache)} cached geocodes", file=sys.stderr)

    to_geocode = []
    for entry in entries:
        addr = entry.get("address")
        if not addr or entry.get("status") == "CLOSED":
            continue
        if not args.force and entry.get("latitude") and entry.get("longitude"):
            continue
        to_geocode.append(entry)

    print(f"{len(to_geocode)} entries need geocoding", file=sys.stderr)

    if args.preview:
        for entry in to_geocode:
            cached = entry["address"] in cache
            tag = "[cached]" if cached else "[new]"
            print(f"  {tag} {entry['id']}: {entry['address']}")
        return

    geocoded = 0
    failed = 0
    for i, entry in enumerate(to_geocode):
        addr = entry["address"]
        print(f"  [{i+1}/{len(to_geocode)}] {entry['id']}: {addr}", file=sys.stderr, end="")

        result = geocode_address(addr, cache)
        if result:
            entry["latitude"] = round(result[0], 6)
            entry["longitude"] = round(result[1], 6)
            geocoded += 1
            print(f" -> {result[0]:.4f}, {result[1]:.4f}", file=sys.stderr)
        else:
            failed += 1
            print(f" -> FAILED", file=sys.stderr)

        # Save cache periodically
        if (i + 1) % 20 == 0:
            save_cache(cache)

    save_cache(cache)
    print(f"\nGeocoded: {geocoded}, Failed: {failed}, Total cached: {len(cache)}", file=sys.stderr)

    if geocoded > 0:
        # Rebuild the YAML file preserving multi-document structure
        with open(args.sources) as f:
            raw = f.read()

        # Load as documents to preserve structure
        documents = list(yaml.safe_load_all(raw))

        # Build lookup of updated entries by id
        updated = {e["id"]: e for e in entries if e.get("latitude")}

        # Update entries in each document
        for doc_idx, doc in enumerate(documents):
            if not doc or not isinstance(doc, list):
                continue
            for entry_idx, entry in enumerate(doc):
                if not isinstance(entry, dict):
                    continue
                eid = entry.get("id")
                if eid and eid in updated:
                    entry["latitude"] = updated[eid]["latitude"]
                    entry["longitude"] = updated[eid]["longitude"]

        # Write back
        # Create backup
        backup = args.sources.with_suffix(".yaml.bak")
        import shutil
        shutil.copy2(args.sources, backup)
        print(f"Backup saved to {backup}", file=sys.stderr)

        with open(args.sources, "w") as f:
            for i, doc in enumerate(documents):
                if i > 0 or raw.lstrip().startswith("---"):
                    f.write("---\n")
                if doc is not None:
                    yaml.dump(doc, f, default_flow_style=False, allow_unicode=True,
                             sort_keys=False, width=120)

        print(f"Updated {args.sources}", file=sys.stderr)


if __name__ == "__main__":
    main()
