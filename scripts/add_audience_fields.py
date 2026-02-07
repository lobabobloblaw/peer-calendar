#!/usr/bin/env python3
"""
Add audience fields to entries in sources.yaml based on pattern matching.

Audience tags:
- children: Ages 3-12
- teens: Ages 13-17
- young_adults: Ages 18-35
- seniors: Ages 55+/62+/65+
- women: Women-only spaces
- lgbtq: LGBTQ+ community
- trans_nonbinary: Trans, nonbinary, gender-diverse
- bipoc: Black, Indigenous, People of Color
- spanish_speaking: Spanish-language services

This script scans eligibility, notes, names, and programs to detect audience patterns.
Run with --preview to see what would be changed without modifying files.
"""

import re
import sys
import argparse
from pathlib import Path
import yaml

from utils import load_sources as _load_sources_shared

# Pattern definitions for each audience tag
AUDIENCE_PATTERNS = {
    'children': [
        r'children',
        r'ages?\s*3[\s-]*12',
        r'ages?\s*\d[\s-]*12\b',
        r'kids?\b',
    ],
    'teens': [
        r'teens?\b',
        r'ages?\s*13[\s-]*1[78]',
        r'adolescen',
        r'grades?\s*[6-9][\s-]*12',
        r'middle\s*school',
        r'high\s*school',
    ],
    'young_adults': [
        r'young\s*adults?',
        r'ages?\s*18[\s-]*35',
        r'ages?\s*14[\s-]*35',
        r'ages?\s*19[\s-]*25',
        r'ages?\s*18[\s-]*25',
        r'ages?\s*26[\s-]*40',
        r'\(18-35\)',
    ],
    'seniors': [
        r'seniors?\b',
        r'65\+',
        r'62\+',
        r'55\+',
        r'older\s*adults?',
        r'senior\s*tuition',
        r'senior\s*center',
    ],
    'women': [
        r'\bwomen\b',
        r"women's",
        r'female[\s-]*identif',
        r'women[\s-]*only',
        r'\(women\)',
    ],
    'lgbtq': [
        r'lgbtq',
        r'queer\b',
        r'lgbtqia',
        r'lgbtq2sia',
        r'pride\b',
        r'lgbtqia2s',
    ],
    'trans_nonbinary': [
        r'\btrans\b',
        r'nonbinary',
        r'non-binary',
        r'gender[\s-]*diverse',
        r'gender[\s-]*fabulous',
        r'agender',
        r'trans\s*pdx',
        r'qtibipoc',  # Includes trans/intersex
    ],
    'bipoc': [
        r'\bbipoc\b',
        r'black,?\s*indigenous',
        r'people\s*of\s*color',
        r'qtibipoc',
    ],
    'spanish_speaking': [
        r'spanish[\s-]*speaking',
        r'en\s*espa[nñ]ol',
        r'esperanza',
        r'spanish[\s-]*language',
    ],
}

# Entries with known audience mappings (for manual overrides or complex cases)
MANUAL_MAPPINGS = {
    # Entry-level audience (applies to whole resource)
    'trail-sisters-portland': {'audience': ['women']},
    'mhcc-senior-tuition': {'audience': ['seniors']},
    'gresham-senior-center': {'audience': ['seniors']},

    # Entries with program-level audiences (handled separately)
    'nami-multnomah': {'programs': {
        'LGBTQ2SIA+ Support': ['lgbtq'],
        'Young Adult (18-35)': ['young_adults'],
        'BIPOC Peer Support': ['bipoc'],
    }},
    'nami-clackamas': {'programs': {
        'Women (18+) Only Support Group': ['women'],
        'Spanish-Speaking Support Group': ['spanish_speaking'],
        'LGBTQ+ Support Group': ['lgbtq'],
    }},
    'dbsa-portland': {'programs': {
        'LGBTQIA+ Support Group': ['lgbtq'],
        'Mental Healthcare Professionals': [],  # Not a demographic
    }},
    'q-center-portland': {'programs': {
        'Trans PDX Support Group': ['trans_nonbinary'],
        'LGBTQIA2S+ Mental Health Support': ['lgbtq'],
        'QTIBIPOC Community Space': ['lgbtq', 'trans_nonbinary', 'bipoc'],
    }},
    'dougy-center': {'programs': {
        "Children's Grief Support (ages 3-12)": ['children'],
        'Teen Grief Support (ages 13-18)': ['teens'],
        'Young Adult Groups (19-25, 26-40)': ['young_adults'],
        'Esperanza (Spanish-language)': ['spanish_speaking'],
    }},
    '4d-recovery': {'audience': ['young_adults']},
    'flow-yoga': {'programs': {
        'Queer and Trans Yoga': ['lgbtq', 'trans_nonbinary'],
    }},
    'refuge-recovery': {'programs': {
        'LGBTQ+ Refuge Recovery': ['lgbtq'],
    }},
}


def detect_audience_from_text(text: str) -> list:
    """Detect audience tags from a text string using pattern matching."""
    if not text:
        return []

    text_lower = text.lower()
    detected = set()

    for audience_tag, patterns in AUDIENCE_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                detected.add(audience_tag)
                break  # Found match for this tag, move to next

    return sorted(list(detected))


def analyze_entry(entry: dict) -> dict:
    """Analyze an entry and return detected audience info."""
    entry_id = entry.get('id', 'unknown')
    result = {
        'id': entry_id,
        'name': entry.get('name', ''),
        'entry_level_audience': [],
        'program_audiences': {},
        'detection_sources': [],
    }

    # Check for manual mapping first
    if entry_id in MANUAL_MAPPINGS:
        mapping = MANUAL_MAPPINGS[entry_id]
        if 'audience' in mapping:
            result['entry_level_audience'] = mapping['audience']
            result['detection_sources'].append('manual_mapping')
        if 'programs' in mapping:
            result['program_audiences'] = mapping['programs']
            result['detection_sources'].append('manual_program_mapping')
        return result

    # Combine text fields for entry-level detection
    text_fields = [
        entry.get('name', ''),
        entry.get('eligibility', ''),
        entry.get('notes', ''),
    ]
    combined_text = ' '.join(str(t) for t in text_fields if t)

    entry_audience = detect_audience_from_text(combined_text)
    if entry_audience:
        result['entry_level_audience'] = entry_audience
        result['detection_sources'].append('text_pattern')

    # Check programs for program-level audiences
    programs = entry.get('programs', [])
    for program in programs:
        if isinstance(program, dict):
            program_name = program.get('name', '')
            program_text = ' '.join([
                program_name,
                str(program.get('eligibility', '')),
                str(program.get('notes', '')),
            ])
            program_audience = detect_audience_from_text(program_text)
            if program_audience:
                result['program_audiences'][program_name] = program_audience

    return result


def load_sources(path: Path) -> list:
    """Load all entries from sources.yaml (multi-document YAML)."""
    return _load_sources_shared(path)


def apply_audience_to_yaml(input_path: Path, results: list, output_path: Path = None) -> int:
    """Apply audience fields to YAML file by text manipulation."""
    if output_path is None:
        output_path = input_path

    with open(input_path, 'r', encoding='utf-8') as f:
        content = f.read()

    lines = content.split('\n')
    new_lines = []
    current_id = None
    current_program_name = None
    results_by_id = {r['id']: r for r in results}
    modified_count = 0
    i = 0

    while i < len(lines):
        line = lines[i]

        # Track current entry ID
        id_match = re.match(r'^- id: (.+)$', line)
        if id_match:
            current_id = id_match.group(1).strip()
            current_program_name = None

        # Track current program name
        program_match = re.match(r'^  - name: (.+)$', line)
        if program_match:
            current_program_name = program_match.group(1).strip().strip('"\'')

        new_lines.append(line)

        # After good_for section, add entry-level audience
        if line.strip().startswith('good_for:') and current_id:
            result = results_by_id.get(current_id)
            if result and result['entry_level_audience']:
                # Find the end of the good_for section
                j = i + 1
                while j < len(lines) and (lines[j].startswith('    -') or lines[j].strip() == ''):
                    new_lines.append(lines[j])
                    j += 1

                # Add audience field
                audience_tags = result['entry_level_audience']
                new_lines.append('  audience:')
                for tag in audience_tags:
                    new_lines.append(f'    - {tag}')
                modified_count += 1
                i = j - 1  # Continue from after good_for items

        # After program format/eligibility, add program-level audience
        if current_program_name and line.strip().startswith(('format:', 'eligibility:')):
            result = results_by_id.get(current_id)
            if result and current_program_name in result.get('program_audiences', {}):
                # Check if audience already added for this program
                program_audience = result['program_audiences'][current_program_name]
                if program_audience:
                    # Look ahead to see if there's already an audience field
                    next_i = i + 1
                    if next_i < len(lines) and not lines[next_i].strip().startswith('audience:'):
                        # Add audience for this program
                        indent = '      '  # Program-level indent
                        new_lines.append(f'{indent}audience:')
                        for tag in program_audience:
                            new_lines.append(f'{indent}  - {tag}')

        i += 1

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(new_lines))

    return modified_count


def main():
    parser = argparse.ArgumentParser(
        description='Add audience fields to sources.yaml entries'
    )
    parser.add_argument(
        '--preview', '-p',
        action='store_true',
        help='Preview changes without modifying files'
    )
    parser.add_argument(
        '--sources',
        type=Path,
        default=None,
        help='Path to sources.yaml (default: data/sources.yaml)'
    )
    parser.add_argument(
        '--output',
        type=Path,
        default=None,
        help='Output path (default: modify in place, or sources-audience.yaml in preview)'
    )
    args = parser.parse_args()

    # Find sources.yaml
    script_dir = Path(__file__).parent
    if args.sources:
        sources_path = args.sources
    else:
        sources_path = script_dir.parent / 'data' / 'sources.yaml'

    if not sources_path.exists():
        print(f"Error: {sources_path} not found")
        sys.exit(1)

    # Load and analyze entries
    print(f"Loading entries from {sources_path}...")
    entries = load_sources(sources_path)
    print(f"Found {len(entries)} entries")

    # Analyze each entry
    results = []
    for entry in entries:
        result = analyze_entry(entry)
        if result['entry_level_audience'] or result['program_audiences']:
            results.append(result)

    # Report findings
    print(f"\n=== Audience Detection Results ===")
    print(f"Entries with detected audiences: {len(results)}")
    print()

    for result in results:
        if result['entry_level_audience'] or result['program_audiences']:
            print(f"  {result['id']}: {result['name']}")
            if result['entry_level_audience']:
                print(f"    Entry audience: {', '.join(result['entry_level_audience'])}")
            if result['program_audiences']:
                for prog, audience in result['program_audiences'].items():
                    print(f"    Program '{prog}': {', '.join(audience)}")
            print()

    # Summary by tag
    print("\n=== Tag Summary ===")
    tag_counts = {}
    for result in results:
        for tag in result['entry_level_audience']:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
        for prog_audience in result['program_audiences'].values():
            for tag in prog_audience:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

    for tag, count in sorted(tag_counts.items(), key=lambda x: -x[1]):
        print(f"  {tag}: {count}")

    if args.preview:
        print("\n[Preview mode - no changes made]")
        if args.output:
            output_path = args.output
        else:
            output_path = sources_path.with_name('sources-audience.yaml')
        print(f"To apply changes, run without --preview")
        print(f"Output would be written to: {output_path}")
    else:
        # Backup first
        backup_path = sources_path.with_suffix('.yaml.bak')
        with open(sources_path, 'r') as f:
            backup_content = f.read()
        with open(backup_path, 'w') as f:
            f.write(backup_content)
        print(f"\nBackup saved to {backup_path}")

        # Apply changes
        output_path = args.output if args.output else sources_path
        modified = apply_audience_to_yaml(sources_path, results, output_path)
        print(f"Modified {modified} entries in {output_path}")


if __name__ == '__main__':
    main()
