#!/usr/bin/env python3
"""Generate resource guides from sources.yaml.

Produces markdown guides organized by category from the master data source,
eliminating drift between sources.yaml and manually-maintained guides.

Usage:
    python generate_guides.py                    # Generate all guides
    python generate_guides.py --category peer_support  # Single category
    python generate_guides.py --output ./my-guides     # Custom output dir
    python generate_guides.py --sources /path/to/sources.yaml
"""

import argparse
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

from utils import load_sources, get_default_sources_path, format_date


# Category display config: order, titles, and intro paragraphs
CATEGORY_CONFIG = {
    "peer_support": {
        "title": "Peer Support: Mental Health & Recovery",
        "intro": (
            "Free peer-led support groups, drop-in centers, and warmlines for adults "
            "living with mental health conditions. All programs listed are free and "
            "led by people with lived experience."
        ),
    },
    "fitness_wellness": {
        "title": "Fitness & Wellness: Accessible Programs for All Abilities",
        "intro": (
            "Community centers with sliding-scale fees, free yoga and meditation, "
            "running groups, and adaptive recreation. Many programs accept the "
            "Portland Parks Access Discount (up to 90% off, no proof of income required)."
        ),
    },
    "parks_nature": {
        "title": "Parks & Nature: Free Outdoor Spaces",
        "intro": (
            "Portland's parks system offers hundreds of free natural areas, trails, "
            "and green spaces. No fees, no memberships required."
        ),
    },
    "arts_culture": {
        "title": "Arts & Culture: Museums, Galleries, and Performances",
        "intro": (
            "Discounted museum admission through Arts for All ($5 with Oregon Trail Card), "
            "free gallery walks, library programs, and community theater."
        ),
    },
    "food_farms": {
        "title": "Food & Farms: Community Meals, U-Pick, and Markets",
        "intro": (
            "Free community meals served with dignity, u-pick farms accepting SNAP/EBT, "
            "farmers markets, and food assistance programs."
        ),
    },
    "events": {
        "title": "Events & Festivals: Free Community Celebrations",
        "intro": (
            "Free festivals, seasonal events, concerts, and community gatherings "
            "throughout the Portland metro area."
        ),
    },
    "social_activities": {
        "title": "Social Activities: Connection and Community",
        "intro": (
            "Board game groups, craft nights, writing workshops, volunteer opportunities, "
            "and other low-pressure ways to connect with people."
        ),
    },
    "discount_programs": {
        "title": "Discount Programs: Maximize Your Access",
        "intro": (
            "Programs that dramatically reduce the cost of transit, utilities, recreation, "
            "and cultural activities. Many require only an Oregon Trail Card or self-declaration "
            "of income."
        ),
    },
    "transportation": {
        "title": "Transportation: Getting Around Portland",
        "intro": (
            "Low-income transit fares, bike programs, and transportation assistance."
        ),
    },
}

# Display order for categories
CATEGORY_ORDER = [
    "peer_support",
    "fitness_wellness",
    "parks_nature",
    "arts_culture",
    "food_farms",
    "events",
    "social_activities",
    "discount_programs",
    "transportation",
]

SOCIAL_LABELS = {
    "solo": "Do alone",
    "drop_in": "Drop-in (come and go freely)",
    "casual_group": "Casual group",
    "structured_group": "Structured group",
    "one_on_one": "One-on-one",
}

GOOD_FOR_LABELS = {
    "anxiety_friendly": "Anxiety-friendly",
    "grief": "Grief support",
    "isolation": "Good for isolation",
    "new_to_area": "Newcomer-friendly",
    "low_energy": "Low energy",
    "active": "Active/physical",
    "creative": "Creative",
    "outdoor": "Outdoor",
    "indoor": "Indoor",
    "family_friendly": "Family-friendly",
}

AUDIENCE_LABELS = {
    "children": "Children (3-12)",
    "teens": "Teens (13-17)",
    "young_adults": "Young adults (18-35)",
    "seniors": "Seniors (55+)",
    "women": "Women",
    "lgbtq": "LGBTQ+",
    "trans_nonbinary": "Trans/nonbinary",
    "bipoc": "BIPOC",
    "spanish_speaking": "Spanish-speaking",
}

ACCESSIBILITY_LABELS = {
    "wheelchair_accessible": "Wheelchair accessible",
    "transit_nearby": "Near transit",
    "elevator": "Elevator",
    "asl_available": "ASL available",
    "hearing_loop": "Hearing loop",
    "scent_free": "Scent-free",
    "low_vision_friendly": "Low-vision friendly",
    "gender_neutral_restroom": "Gender-neutral restroom",
    "sliding_scale": "Sliding scale",
}


def format_pricing(pricing) -> str:
    """Format pricing info into a readable string."""
    if not pricing:
        return ""
    if isinstance(pricing, str):
        return pricing
    desc = pricing.get("description", "")
    notes = pricing.get("notes", "")
    parts = []
    if desc:
        parts.append(str(desc))
    if notes:
        parts.append(str(notes))
    return ". ".join(parts) if parts else ""


def format_tags(tags, label_map) -> str:
    """Format a list of tags into human-readable labels."""
    if not tags:
        return ""
    labels = [label_map.get(t, t.replace("_", " ").title()) for t in tags]
    return ", ".join(labels)


def format_entry(entry) -> str:
    """Format a single entry as markdown."""
    lines = []
    name = entry.get("name", "Unknown")
    status = entry.get("status", "")

    lines.append(f"### {name}")
    lines.append("")

    # Contact/location block
    details = []
    if entry.get("address"):
        details.append(f"**Address:** {entry['address']}")
    if entry.get("phone"):
        details.append(f"**Phone:** {entry['phone']}")
    if entry.get("website"):
        details.append(f"**Website:** {entry['website']}")

    pricing_str = format_pricing(entry.get("pricing"))
    if pricing_str:
        details.append(f"**Cost:** {pricing_str}")

    if entry.get("hours"):
        hours = entry["hours"]
        if isinstance(hours, dict):
            hours_parts = [f"{k.replace('_', ' ').title()}: {v}" for k, v in hours.items()]
            details.append(f"**Hours:** {'; '.join(hours_parts)}")
        else:
            details.append(f"**Hours:** {hours}")
    if entry.get("schedule"):
        details.append(f"**Schedule:** {entry['schedule']}")
    if entry.get("dates"):
        dates = entry["dates"]
        if isinstance(dates, list):
            details.append(f"**Dates:** {', '.join(str(d) for d in dates)}")
        else:
            details.append(f"**Dates:** {dates}")
    if entry.get("season"):
        details.append(f"**Season:** {entry['season']}")
    if entry.get("eligibility"):
        details.append(f"**Eligibility:** {entry['eligibility']}")
    if entry.get("transit"):
        details.append(f"**Transit:** {entry['transit']}")

    if details:
        for d in details:
            lines.append(f"- {d}")
        lines.append("")

    # Notes / description
    if entry.get("notes"):
        lines.append(f"{entry['notes']}")
        lines.append("")

    # Practical tips
    tips = entry.get("practical_tips", {})
    if tips:
        if isinstance(tips, str):
            lines.append(f"**Tips:** {tips}")
            lines.append("")
            tips = {}
        good_to_know = tips.get("good_to_know", "") if tips else ""
        first_visit = tips.get("first_visit", "") if tips else ""
        registration = tips.get("registration", "") if tips else ""
        what_to_bring = tips.get("what_to_bring", "") if tips else ""

        if good_to_know:
            lines.append(f"**What to know:** {good_to_know}")
            lines.append("")
        if first_visit:
            lines.append(f"**First visit:** {first_visit}")
            lines.append("")
        if registration and registration != first_visit:
            lines.append(f"**Registration:** {registration}")
            lines.append("")
        if what_to_bring:
            lines.append(f"**What to bring:** {what_to_bring}")
            lines.append("")

    # Programs
    programs = entry.get("programs", [])
    if programs:
        lines.append("**Programs:**")
        lines.append("")
        for prog in programs:
            if isinstance(prog, str):
                lines.append(f"- {prog}")
                continue
            pname = prog.get("name", "")
            parts = []
            if prog.get("schedule"):
                parts.append(prog["schedule"])
            if prog.get("cost"):
                parts.append(prog["cost"])
            if prog.get("format"):
                parts.append(prog["format"])
            if prog.get("location"):
                parts.append(prog["location"])
            detail = " | ".join(parts) if parts else ""
            if detail:
                lines.append(f"- **{pname}:** {detail}")
            else:
                lines.append(f"- **{pname}**")
            # Program notes
            if prog.get("notes"):
                lines.append(f"  {prog['notes']}")
            # Program audience
            prog_audience = prog.get("audience")
            if prog_audience:
                lines.append(f"  *For: {format_tags(prog_audience, AUDIENCE_LABELS)}*")
        lines.append("")

    # Features
    features = entry.get("features", [])
    if features:
        lines.append("**Features:** " + ", ".join(str(f) for f in features))
        lines.append("")

    # Tags line (compact)
    tag_parts = []

    social = entry.get("social_intensity")
    if social:
        tag_parts.append(SOCIAL_LABELS.get(social, social))

    good_for = entry.get("good_for", [])
    if good_for:
        tag_parts.append(format_tags(good_for, GOOD_FOR_LABELS))

    audience = entry.get("audience", [])
    if audience:
        tag_parts.append(f"For: {format_tags(audience, AUDIENCE_LABELS)}")

    accessibility = entry.get("accessibility", [])
    if accessibility:
        tag_parts.append(format_tags(accessibility, ACCESSIBILITY_LABELS))

    if tag_parts:
        lines.append(f"*{' · '.join(tag_parts)}*")
        lines.append("")

    # Accessibility notes (if present and adds info beyond tags)
    if entry.get("accessibility_notes"):
        lines.append(f"**Accessibility:** {entry['accessibility_notes']}")
        lines.append("")

    # Audience notes
    if entry.get("audience_notes"):
        lines.append(f"**Who it's for:** {entry['audience_notes']}")
        lines.append("")

    return "\n".join(lines)


def generate_category_section(category, entries) -> str:
    """Generate a full markdown section for one category."""
    config = CATEGORY_CONFIG.get(category, {})
    title = config.get("title", category.replace("_", " ").title())
    intro = config.get("intro", "")

    lines = []
    lines.append(f"## {title}")
    lines.append("")
    if intro:
        lines.append(intro)
        lines.append("")

    # Sort: active entries first (alphabetically), then closed at bottom
    active = sorted(
        [e for e in entries if e.get("status") != "CLOSED"],
        key=lambda e: e.get("name", "").lower(),
    )
    closed = sorted(
        [e for e in entries if e.get("status") == "CLOSED"],
        key=lambda e: e.get("name", "").lower(),
    )

    for entry in active:
        lines.append(format_entry(entry))

    if closed:
        lines.append("### Permanently Closed")
        lines.append("")
        for entry in closed:
            name = entry.get("name", "Unknown")
            closed_date = entry.get("closed_date", "")
            note = f"**{name}**"
            if closed_date:
                note += f" (closed {format_date(closed_date)})"
            if entry.get("notes"):
                note += f" — {entry['notes']}"
            lines.append(f"- {note}")
        lines.append("")

    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def generate_guide(entries, categories=None) -> str:
    """Generate the full guide markdown from entries."""
    # Group by category
    by_category = defaultdict(list)
    for entry in entries:
        cat = entry.get("category", "unknown")
        by_category[cat].append(entry)

    # Determine which categories to include
    if categories:
        cats_to_generate = [c for c in CATEGORY_ORDER if c in categories]
    else:
        cats_to_generate = [c for c in CATEGORY_ORDER if c in by_category]

    lines = []

    # Header
    lines.append("# Free and Low-Cost Resources for Portland Metro Adults")
    lines.append("")
    lines.append(
        "A comprehensive guide to free and affordable activities, services, and resources "
        "in the Portland metro area, with special attention to accessibility and mental health support."
    )
    lines.append("")
    today = date.today().strftime("%B %d, %Y")
    total_active = sum(
        1 for e in entries if e.get("status") != "CLOSED"
    )
    lines.append(
        f"*Generated from verified data on {today}. "
        f"{total_active} active resources across {len(cats_to_generate)} categories.*"
    )
    lines.append("")

    # Table of contents
    lines.append("## Contents")
    lines.append("")
    for cat in cats_to_generate:
        config = CATEGORY_CONFIG.get(cat, {})
        title = config.get("title", cat.replace("_", " ").title())
        count = len([e for e in by_category[cat] if e.get("status") != "CLOSED"])
        anchor = title.lower().replace(" ", "-").replace("&", "").replace(":", "").replace(",", "")
        anchor = anchor.replace("--", "-").strip("-")
        lines.append(f"- [{title}](#{anchor}) ({count} resources)")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Quick-start box
    lines.append("## Three Programs That Change Everything")
    lines.append("")
    lines.append(
        "1. **Portland Parks Access Discount** — Up to 90% off all parks programs. "
        "No proof of income required. [portland.gov/parks/discount](https://portland.gov/parks/discount)"
    )
    lines.append(
        "2. **Arts for All** — $5 tickets at 100+ cultural venues with Oregon Trail Card. "
        "[racc.org/artsforall](https://racc.org/artsforall)"
    )
    lines.append(
        "3. **TriMet Low-Income Fare** — $28/month unlimited transit. "
        "[trimet.org/fares/reduced](https://trimet.org/fares/reduced)"
    )
    lines.append("")
    lines.append("---")
    lines.append("")

    # Category sections
    for cat in cats_to_generate:
        if by_category[cat]:
            lines.append(generate_category_section(cat, by_category[cat]))

    # Tips section
    lines.append("## Tips for Those with Social Anxiety")
    lines.append("")
    lines.append(
        "Many resources in this guide are marked as **anxiety-friendly**. Look for these qualities:"
    )
    lines.append("")
    lines.append("- **Drop-in format** — arrive and leave when you want, no commitment")
    lines.append("- **Solo activities** — parks, trails, libraries, museums")
    lines.append("- **Quiet times** — early mornings, weekday afternoons")
    lines.append("- **Low-pressure groups** — craft nights, walking groups where conversation is optional")
    lines.append("- **Online options** — Zoom support groups let you participate with camera off")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Footer
    lines.append("## About This Guide")
    lines.append("")
    lines.append(
        "Maintained by [FolkTime](https://folktime.org) for peer support programs in the "
        "Portland metro area. Resources are verified on a regular audit schedule."
    )
    lines.append("")
    lines.append(
        "**Report corrections or suggest new resources:** avoigt@folktime.org"
    )
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Generate resource guides from sources.yaml"
    )
    parser.add_argument(
        "--sources",
        type=Path,
        default=get_default_sources_path(),
        help="Path to sources.yaml",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).parent.parent / "guides",
        help="Output directory for generated guides",
    )
    parser.add_argument(
        "--category",
        type=str,
        help="Generate guide for a single category only",
    )
    args = parser.parse_args()

    entries = load_sources(args.sources)
    print(f"Loaded {len(entries)} entries from {args.sources}", file=sys.stderr)

    categories = None
    if args.category:
        categories = {args.category}
        matching = [e for e in entries if e.get("category") == args.category]
        if not matching:
            print(f"Error: No entries found for category '{args.category}'", file=sys.stderr)
            sys.exit(1)
        print(f"Filtering to category '{args.category}' ({len(matching)} entries)", file=sys.stderr)

    guide_content = generate_guide(entries, categories)

    args.output.mkdir(parents=True, exist_ok=True)
    if args.category:
        output_file = args.output / f"{args.category}-guide.md"
    else:
        output_file = args.output / "resources-guide.md"

    output_file.write_text(guide_content, encoding="utf-8")
    line_count = guide_content.count("\n") + 1
    print(f"Generated {output_file} ({line_count} lines)", file=sys.stderr)


if __name__ == "__main__":
    main()
