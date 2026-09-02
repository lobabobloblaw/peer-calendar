#!/usr/bin/env python3
"""Tests for guide generation.

The guide is a published artifact that CI regenerates and commits, so its
content must depend only on the data, never on when it ran.

Run: python test_generate_guides.py
"""
import os
import re
import sys
import unittest
from datetime import date
from pathlib import Path

# Add scripts directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from generate_guides import generate_guide
from utils import load_sources


def entry(**overrides):
    """A minimal entry the guide generator will render."""
    base = {
        "id": "test-entry",
        "name": "Test Resource",
        "category": "peer_support",
        "location_type": "physical",
        "resource_type": "program",
        "pricing": "FREE",
        "last_verified": date(2026, 3, 1),
        "next_audit": date(2026, 6, 1),
        "audit_frequency": "quarterly",
    }
    base.update(overrides)
    return base


class TestDeterministicHeader(unittest.TestCase):
    """The header must be dated from the data, not the clock."""

    ENTRIES = [
        entry(id="older", name="Older Entry", last_verified=date(2026, 3, 1)),
        entry(id="newest", name="Newest Entry", last_verified=date(2026, 7, 14)),
        entry(id="middle", name="Middle Entry", last_verified=date(2026, 5, 2)),
    ]

    def header_of(self, guide):
        match = re.search(r"^\*Generated from data verified through (.+?)\. ", guide, re.M)
        self.assertIsNotNone(match, "guide is missing its generated-through line")
        return match.group(1)

    def test_repeated_generation_is_identical(self):
        self.assertEqual(generate_guide(self.ENTRIES), generate_guide(self.ENTRIES))

    def test_header_uses_newest_last_verified(self):
        self.assertEqual(self.header_of(generate_guide(self.ENTRIES)), "July 14, 2026")

    def test_header_does_not_use_today(self):
        """Guard the exact regression: a today() stamp made CI commit weekly."""
        self.assertNotIn(date.today().strftime("%B %d, %Y"), generate_guide(self.ENTRIES))

    def test_header_changes_only_when_data_does(self):
        reverified = self.ENTRIES + [entry(id="fresh", last_verified=date(2026, 9, 30))]
        self.assertEqual(self.header_of(generate_guide(reverified)), "September 30, 2026")

    def test_missing_dates_do_not_crash(self):
        undated = [entry(id="undated", last_verified=None)]
        self.assertIn("an unrecorded date", generate_guide(undated))


class TestActiveCount(unittest.TestCase):
    """Closed resources stay in the guide's history but not in the count."""

    def test_closed_entries_are_excluded_from_the_count(self):
        entries = [
            entry(id="open-one"),
            entry(id="open-two"),
            entry(id="shut", status="CLOSED", closed_date=date(2025, 4, 1)),
        ]
        self.assertIn("2 active resources", generate_guide(entries))


class TestCorpusGuide(unittest.TestCase):
    """The real data must generate a stable guide."""

    @classmethod
    def setUpClass(cls):
        sources = Path(__file__).resolve().parents[1] / "data" / "sources.yaml"
        cls.entries = load_sources(sources)

    def test_corpus_generation_is_repeatable(self):
        self.assertEqual(generate_guide(self.entries), generate_guide(self.entries))

    def test_corpus_header_matches_newest_verification(self):
        newest = max(
            e["last_verified"] for e in self.entries if e.get("last_verified")
        )
        expected = newest.strftime("%B %d, %Y")
        self.assertIn(f"verified through {expected}.", generate_guide(self.entries))


if __name__ == "__main__":
    unittest.main(verbosity=2)
