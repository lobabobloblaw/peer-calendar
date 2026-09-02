#!/usr/bin/env python3
"""Tests for entry shape validation.

These guard shapes that parse as valid YAML but are dropped silently by the
consumers, which is how a resource ends up listed with none of its content.

Run: python test_validate_entry.py
"""
import os
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from utils import load_sources, validate_entry


def entry(**overrides):
    base = {
        "id": "test-entry",
        "name": "Test Resource",
        "category": "peer_support",
        "location_type": "physical",
        "resource_type": "program",
        "source_urls": ["https://example.org"],
        "last_verified": date(2026, 3, 1),
        "next_audit": date(2026, 6, 1),
        "audit_frequency": "quarterly",
    }
    base.update(overrides)
    return base


def program_warnings(**overrides):
    return [w for w in validate_entry(entry(**overrides)) if "program" in w.lower()]


class TestProgramShape(unittest.TestCase):
    """`programs` must be a list of mappings, each with a name."""

    def test_valid_program_passes(self):
        self.assertEqual(
            program_warnings(programs=[{"name": "Drop-in", "schedule": "Mondays 5-6pm"}]),
            [],
        )

    def test_bare_string_program_is_rejected(self):
        """A string program can never carry a schedule, so it never reaches a calendar."""
        warnings = program_warnings(programs=["Drop-in peer support"])
        self.assertEqual(len(warnings), 1)
        self.assertIn("must be a mapping", warnings[0])
        self.assertIn("- name: Drop-in peer support", warnings[0])

    def test_mapping_instead_of_list_is_rejected(self):
        """The site reads programs.length, which is undefined for an object.

        juanita-pohl-center stored 23 activities this way, including a Spanish
        women's support group, and none of them rendered anywhere.
        """
        warnings = program_warnings(programs={"fitness": ["Tai Chi"]})
        self.assertEqual(len(warnings), 1)
        self.assertIn("must be a list", warnings[0])

    def test_program_without_a_name_is_rejected(self):
        warnings = program_warnings(programs=[{"schedule": "Mondays 5-6pm"}])
        self.assertTrue(any("missing its 'name'" in w for w in warnings), warnings)

    def test_absent_programs_is_fine(self):
        self.assertEqual(program_warnings(), [])


class TestCorpusProgramShape(unittest.TestCase):
    """The real data must satisfy the shape the consumers assume."""

    @classmethod
    def setUpClass(cls):
        sources = Path(__file__).resolve().parents[1] / "data" / "sources.yaml"
        cls.entries = load_sources(sources)

    def test_every_program_is_a_named_mapping(self):
        offenders = [
            (e.get("id"), p)
            for e in self.entries
            for p in (e.get("programs") or [])
            if not isinstance(p, dict) or not p.get("name")
        ]
        self.assertEqual(offenders, [])

    def test_no_entry_stores_programs_as_a_mapping(self):
        offenders = [
            e.get("id") for e in self.entries if isinstance(e.get("programs"), dict)
        ]
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
