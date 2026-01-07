#!/usr/bin/env python3
"""
Add location_type and resource_type fields to all entries in sources.yaml

location_type: physical | virtual | hybrid | varies | online_service
resource_type: place | event | service | program | organization

This script reads sources.yaml, adds the fields, and writes back.
"""

import re
from pathlib import Path

# Define the type mappings for each entry
ENTRY_TYPES = {
    # DISCOUNT PROGRAMS - services (apply online or in-person)
    "ppr-access-discount": {"location_type": "varies", "resource_type": "service"},
    "trimet-low-income": {"location_type": "varies", "resource_type": "service"},
    "arts-for-all": {"location_type": "physical", "resource_type": "service"},
    "thprd-financial-aid": {"location_type": "varies", "resource_type": "service"},

    # PARKS - physical places
    "forest-park": {"location_type": "physical", "resource_type": "place"},
    "smith-bybee-wetlands": {"location_type": "physical", "resource_type": "place"},
    "tryon-creek": {"location_type": "physical", "resource_type": "place"},
    "powell-butte": {"location_type": "physical", "resource_type": "place"},
    "oaks-bottom": {"location_type": "physical", "resource_type": "place"},
    "cooper-mountain": {"location_type": "physical", "resource_type": "place"},
    "oxbow-regional-park": {"location_type": "physical", "resource_type": "place"},
    "tualatin-river-nwr": {"location_type": "physical", "resource_type": "place"},
    "hoyt-arboretum": {"location_type": "physical", "resource_type": "place"},

    # PEER SUPPORT - programs with meetings (mostly hybrid/virtual)
    "nami-multnomah": {"location_type": "hybrid", "resource_type": "program"},
    "nami-clackamas": {"location_type": "hybrid", "resource_type": "program"},
    "folktime": {"location_type": "physical", "resource_type": "program"},
    "northstar-clubhouse": {"location_type": "physical", "resource_type": "program"},
    "new-narrative-comfort-zone": {"location_type": "physical", "resource_type": "program"},
    "bhrc": {"location_type": "physical", "resource_type": "service"},
    "dbsa-portland": {"location_type": "hybrid", "resource_type": "program"},
    "oregon-warmline": {"location_type": "online_service", "resource_type": "service"},
    "peer-company": {"location_type": "physical", "resource_type": "organization"},
    "q-center-portland": {"location_type": "hybrid", "resource_type": "organization"},
    "dda-oregon": {"location_type": "hybrid", "resource_type": "program"},
    "aa-portland-intergroup": {"location_type": "hybrid", "resource_type": "organization"},
    "dougy-center": {"location_type": "physical", "resource_type": "organization"},
    "providence-grief-support": {"location_type": "physical", "resource_type": "program"},
    "recovery-dharma": {"location_type": "hybrid", "resource_type": "program"},

    # U-PICK FARMS - physical places (seasonal)
    "south-barlow-berries": {"location_type": "physical", "resource_type": "place"},
    "columbia-farms": {"location_type": "physical", "resource_type": "place"},

    # COMMUNITY CENTERS - physical places with programs
    "matt-dishman-cc": {"location_type": "physical", "resource_type": "place"},
    "east-portland-cc": {"location_type": "physical", "resource_type": "place"},
    "mt-scott-cc": {"location_type": "physical", "resource_type": "place"},
    "gresham-senior-center": {"location_type": "physical", "resource_type": "place"},
    "milwaukie-community-center": {"location_type": "physical", "resource_type": "place"},
    "ymca-columbia-willamette": {"location_type": "physical", "resource_type": "organization"},

    # EVENTS - dated events at physical locations
    "summer-free-for-all-2025": {"location_type": "physical", "resource_type": "event"},
    "sunday-parkways-2025": {"location_type": "physical", "resource_type": "event"},
    "cathedral-park-jazz": {"location_type": "physical", "resource_type": "event"},
    "noon-tunes": {"location_type": "physical", "resource_type": "event"},
    "portland-rose-festival": {"location_type": "physical", "resource_type": "event"},
    "portland-pride": {"location_type": "physical", "resource_type": "event"},
    "first-thursday": {"location_type": "physical", "resource_type": "event"},
    "last-thursday-alberta": {"location_type": "physical", "resource_type": "event"},
    "portland-tree-lighting": {"location_type": "physical", "resource_type": "event"},
    "peacock-lane": {"location_type": "physical", "resource_type": "event"},

    # MUSEUMS & CULTURAL - physical places
    "portland-art-museum": {"location_type": "physical", "resource_type": "place"},
    "omsi": {"location_type": "physical", "resource_type": "place"},
    "oregon-historical-society": {"location_type": "physical", "resource_type": "place"},
    "oregon-jewish-museum": {"location_type": "physical", "resource_type": "place"},
    "five-oaks-museum": {"location_type": "physical", "resource_type": "place"},
    "oregon-rail-heritage": {"location_type": "physical", "resource_type": "place"},
    "naya": {"location_type": "physical", "resource_type": "organization"},
    "irco": {"location_type": "physical", "resource_type": "organization"},
    "bird-alliance-oregon": {"location_type": "physical", "resource_type": "organization"},

    # FITNESS & WELLNESS - physical places/programs
    "pier-park-disc-golf": {"location_type": "physical", "resource_type": "place"},
    "rockwood-disc-golf": {"location_type": "physical", "resource_type": "place"},
    "lunchtime-disc-golf": {"location_type": "physical", "resource_type": "place"},
    "yoga-on-yamhill": {"location_type": "physical", "resource_type": "program"},
    "bymc-portland": {"location_type": "physical", "resource_type": "program"},
    "portland-yoga-project": {"location_type": "physical", "resource_type": "program"},
    "dharma-rain": {"location_type": "hybrid", "resource_type": "organization"},
    "diamond-way-buddhist": {"location_type": "physical", "resource_type": "organization"},
    "portland-insight-meditation": {"location_type": "hybrid", "resource_type": "organization"},
    "portland-running-company": {"location_type": "physical", "resource_type": "program"},
    "lloyd-center-walking": {"location_type": "physical", "resource_type": "program"},
    "neighborwalks": {"location_type": "physical", "resource_type": "program"},
    "shift-to-bikes": {"location_type": "physical", "resource_type": "organization"},
    "portland-bicycling-club": {"location_type": "physical", "resource_type": "organization"},

    # FOOD SERVICES - physical places
    "blanchet-house": {"location_type": "physical", "resource_type": "service"},
    "sisters-of-the-road": {"location_type": "physical", "resource_type": "service"},
    "portland-rescue-mission": {"location_type": "physical", "resource_type": "service"},
    "sikh-center-langar": {"location_type": "physical", "resource_type": "service"},
    "loaves-fishes": {"location_type": "physical", "resource_type": "service"},

    # ENTERTAINMENT - physical places
    "academy-theater": {"location_type": "physical", "resource_type": "place"},
    "avalon-theatre": {"location_type": "physical", "resource_type": "place"},
    "laurelhurst-theater": {"location_type": "physical", "resource_type": "place"},
    "living-room-theaters": {"location_type": "physical", "resource_type": "place"},
    "hollywood-theatre": {"location_type": "physical", "resource_type": "place"},
    "ground-kontrol": {"location_type": "physical", "resource_type": "place"},
    "guardian-games": {"location_type": "physical", "resource_type": "place"},
    "pdx-board-games-meetup": {"location_type": "physical", "resource_type": "program"},

    # SOCIAL ACTIVITIES - programs/organizations
    "write-around-portland": {"location_type": "physical", "resource_type": "organization"},
    "friends-of-trees": {"location_type": "physical", "resource_type": "organization"},
    "solve-oregon": {"location_type": "physical", "resource_type": "organization"},
    "oregon-food-bank-volunteer": {"location_type": "physical", "resource_type": "program"},
    "multnomah-arts-center": {"location_type": "physical", "resource_type": "place"},

    # UTILITY DISCOUNTS - online services
    "pge-income-qualified": {"location_type": "online_service", "resource_type": "service"},
    "pacific-power-discount": {"location_type": "online_service", "resource_type": "service"},
    "nw-natural-discount": {"location_type": "online_service", "resource_type": "service"},
    "double-up-food-bucks": {"location_type": "physical", "resource_type": "service"},

    # LIBRARIES - physical places
    "clackamas-county-libraries": {"location_type": "physical", "resource_type": "place"},
}


def add_fields_to_yaml(input_path: str, output_path: str = None):
    """Read YAML, add type fields after category line, write back."""

    if output_path is None:
        output_path = input_path

    with open(input_path, 'r', encoding='utf-8') as f:
        content = f.read()

    lines = content.split('\n')
    new_lines = []
    current_id = None
    i = 0

    while i < len(lines):
        line = lines[i]
        new_lines.append(line)

        # Track current entry ID
        id_match = re.match(r'^- id: (.+)$', line)
        if id_match:
            current_id = id_match.group(1).strip()

        # After category line, insert type fields
        if line.strip().startswith('category:') and current_id:
            if current_id in ENTRY_TYPES:
                types = ENTRY_TYPES[current_id]
                # Get indentation from current line
                indent = '  '  # Standard 2-space indent for YAML
                new_lines.append(f"{indent}location_type: {types['location_type']}")
                new_lines.append(f"{indent}resource_type: {types['resource_type']}")

        i += 1

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(new_lines))

    print(f"Updated {len(ENTRY_TYPES)} entries with location_type and resource_type fields")
    return len(ENTRY_TYPES)


if __name__ == "__main__":
    script_dir = Path(__file__).parent
    sources_path = script_dir.parent / "data" / "sources.yaml"

    if not sources_path.exists():
        print(f"Error: {sources_path} not found")
        exit(1)

    # Backup first
    backup_path = sources_path.with_suffix('.yaml.bak')
    with open(sources_path, 'r') as f:
        backup_content = f.read()
    with open(backup_path, 'w') as f:
        f.write(backup_content)
    print(f"Backup saved to {backup_path}")

    count = add_fields_to_yaml(str(sources_path))
    print(f"Done! Added fields to {count} entries.")
