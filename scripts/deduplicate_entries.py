#!/usr/bin/env python3
"""
Deduplicate entries in sources.yaml by merging duplicate IDs.

Strategy:
- Keep the entry with more complete base data (full address, hours, services)
- Merge in enrichment fields from other copies (social_intensity, good_for, practical_tips)
- Output a cleaned YAML file
"""

import copy
import yaml
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path


def count_completeness(entry):
    """Score how complete the base data is."""
    score = 0

    # Address completeness
    addr = entry.get('address', '') or ''
    if addr and len(addr) > 20:  # Has full address
        score += 3
    elif addr:
        score += 1

    # Hours
    if entry.get('hours'):
        score += 2

    # Services list
    services = entry.get('services', [])
    if services:
        score += len(services)

    # Programs list
    programs = entry.get('programs', [])
    if programs:
        score += len(programs) * 2

    # Phone
    if entry.get('phone'):
        score += 1

    # Website
    if entry.get('website'):
        score += 1

    # Source URLs
    if entry.get('source_urls'):
        score += len(entry.get('source_urls', []))

    return score


def count_enrichment(entry):
    """Score how complete the enrichment data is."""
    score = 0

    # Social intensity
    if entry.get('social_intensity'):
        score += 2

    # Good for tags
    score += len(entry.get('good_for', []))

    # Accessibility tags
    score += len(entry.get('accessibility', []))

    # Practical tips (count filled values)
    tips = entry.get('practical_tips', {}) or {}
    for v in tips.values():
        if v:
            score += 1

    return score


def merge_entries(entries_list):
    """Merge multiple entries with same ID into one."""
    if len(entries_list) == 1:
        return entries_list[0]

    # Score each entry
    scored = []
    for e in entries_list:
        base_score = count_completeness(e)
        enrich_score = count_enrichment(e)
        scored.append((base_score, enrich_score, e))

    # Sort by base completeness (highest first)
    scored.sort(key=lambda x: -x[0])

    # Start with most complete base entry
    merged = copy.deepcopy(scored[0][2])

    # Merge in enrichment from others
    for _, _, entry in scored[1:]:
        # social_intensity
        if not merged.get('social_intensity') and entry.get('social_intensity'):
            merged['social_intensity'] = entry['social_intensity']

        # good_for - merge lists
        existing_gf = set(merged.get('good_for', []) or [])
        new_gf = set(entry.get('good_for', []) or [])
        if new_gf - existing_gf:
            merged['good_for'] = list(existing_gf | new_gf)

        # accessibility - merge lists
        existing_acc = set(merged.get('accessibility', []) or [])
        new_acc = set(entry.get('accessibility', []) or [])
        if new_acc - existing_acc:
            merged['accessibility'] = list(existing_acc | new_acc)

        # practical_tips - fill in missing
        merged_tips = merged.get('practical_tips', {}) or {}
        entry_tips = entry.get('practical_tips', {}) or {}
        for key in ['first_visit', 'registration', 'what_to_bring', 'good_to_know']:
            if not merged_tips.get(key) and entry_tips.get(key):
                if 'practical_tips' not in merged:
                    merged['practical_tips'] = {}
                merged['practical_tips'][key] = entry_tips[key]

        # services - merge lists
        existing_services = merged.get('services', []) or []
        new_services = entry.get('services', []) or []
        if new_services and len(new_services) > len(existing_services):
            merged['services'] = new_services

    return merged


def main():
    sources_path = Path(__file__).parent.parent / "data" / "sources.yaml"

    with open(sources_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Parse all documents
    all_entries = []
    for doc in yaml.safe_load_all(content):
        if doc and isinstance(doc, list):
            all_entries.extend(doc)
        elif doc and isinstance(doc, dict) and "id" in doc:
            all_entries.append(doc)

    # Group by ID
    by_id = defaultdict(list)
    for e in all_entries:
        by_id[e.get('id')].append(e)

    # Find duplicates
    dupes = {k: v for k, v in by_id.items() if len(v) > 1}

    if not dupes:
        print("No duplicates found!")
        return

    print(f"Found {len(dupes)} duplicate IDs")

    # Merge duplicates
    merged_entries = []
    seen_ids = set()

    for entry in all_entries:
        entry_id = entry.get('id')
        if entry_id in seen_ids:
            continue

        if entry_id in dupes:
            # Merge all copies
            merged = merge_entries(dupes[entry_id])
            merged_entries.append(merged)
            print(f"  Merged: {entry_id} ({len(dupes[entry_id])} copies)")
        else:
            merged_entries.append(entry)

        seen_ids.add(entry_id)

    print(f"\nOriginal entries: {len(all_entries)}")
    print(f"After dedup: {len(merged_entries)}")

    # Preview mode - show what would change
    if '--preview' in sys.argv:
        print("\n[Preview mode - no changes made]")
        return

    # Write back
    # We need to preserve the document structure with separators
    # For simplicity, write as a single list
    output_path = sources_path.parent / "sources-deduped.yaml"

    # Group by category for organization
    by_category = defaultdict(list)
    for e in merged_entries:
        cat = e.get('category', 'uncategorized')
        by_category[cat].append(e)

    # Write with category headers
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# Portland Metro Resources - Source Registry\n")
        f.write(f"# Last updated: {date.today().isoformat()}\n")
        f.write("# Deduplicated and merged from sources.yaml\n")
        f.write("#\n")
        f.write("# This file is the source of truth for all resources in the guides.\n")
        f.write("# Each entry includes verification metadata for audit tracking.\n\n")

        category_order = [
            'discount_programs', 'transportation', 'peer_support',
            'fitness_wellness', 'arts_culture', 'events',
            'parks_nature', 'food_farms', 'social_activities'
        ]

        for cat in category_order:
            if cat in by_category:
                f.write(f"---\n# {cat.upper().replace('_', ' ')}\n---\n\n")
                yaml.dump(by_category[cat], f, default_flow_style=False, sort_keys=False, allow_unicode=True)
                f.write("\n")

    print(f"\nWrote deduplicated data to: {output_path}")
    print("Review the file, then replace sources.yaml if it looks correct")


if __name__ == "__main__":
    main()
