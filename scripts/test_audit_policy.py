#!/usr/bin/env python3
"""Tests for risk-based audit policy and workload reporting."""

import json
import subprocess
import sys
import unittest
from datetime import date
from pathlib import Path

from audit_policy import audit_priority, audit_queue, cadence_deadline, validate_audit_policy, workload_summary
from audit_complete import calculate_next_audit
from migrate_audit_cadence import MIGRATION_IDS, PRESERVE_DUE_IDS, migrate
from utils import load_sources, validate_all_entries


ROOT = Path(__file__).resolve().parent.parent


def entry(entry_id="sample", **overrides):
    value = {
        "id": entry_id,
        "name": entry_id,
        "category": "events",
        "location_type": "varies",
        "resource_type": "event",
        "source_urls": ["https://example.org"],
        "last_verified": date(2026, 1, 31),
        "next_audit": date(2026, 2, 28),
        "audit_frequency": "monthly",
    }
    value.update(overrides)
    return value


class TestAuditPolicy(unittest.TestCase):
    def test_month_end_and_leap_year_deadlines(self):
        self.assertEqual(cadence_deadline("monthly", date(2026, 1, 31)), date(2026, 2, 28))
        self.assertEqual(cadence_deadline("annually", date(2024, 2, 29)), date(2025, 2, 28))

    def test_unknown_cadence_raises(self):
        with self.assertRaises(ValueError):
            cadence_deadline("whenever", date(2026, 1, 1))
        with self.assertRaises(ValueError):
            calculate_next_audit("whenever", date(2026, 1, 1))

    def test_earlier_custom_due_date_is_allowed(self):
        value = entry(next_audit=date(2026, 2, 10))
        self.assertEqual(validate_audit_policy(value, date(2026, 8, 13)), [])

    def test_later_legacy_custom_date_is_not_schema_invalid(self):
        value = entry(next_audit=date(2026, 3, 1))
        self.assertEqual(validate_audit_policy(value, date(2026, 8, 13)), [])

    def test_reversed_and_future_dates_are_rejected(self):
        reversed_value = entry(last_verified=date(2026, 2, 1), next_audit=date(2026, 1, 1))
        self.assertTrue(any("before last_verified" in warning for warning in validate_audit_policy(reversed_value, date(2026, 8, 13))))
        future_value = entry(last_verified=date(2027, 1, 1), next_audit=date(2027, 2, 1))
        self.assertTrue(any("in the future" in warning for warning in validate_audit_policy(future_value, date(2026, 8, 13))))

    def test_closed_entry_is_exempt(self):
        self.assertEqual(validate_audit_policy({"id": "closed", "status": "CLOSED"}), [])

    def test_queue_prioritizes_flags_then_priority_then_date(self):
        entries = [
            entry("low", resource_type="place", next_audit=date(2026, 1, 1)),
            entry("high", category="peer_support", next_audit=date(2026, 1, 2)),
            entry("flagged", resource_type="place", next_audit=date(2026, 1, 3), flags=["⚠️ VERIFY"]),
        ]
        self.assertEqual([row["id"] for row in audit_queue(entries, date(2026, 8, 13))], ["flagged", "high", "low"])

    def test_priority_is_derived_without_new_per_entry_metadata(self):
        self.assertEqual(audit_priority(entry(category="peer_support")), "critical")
        self.assertEqual(audit_priority(entry(category="transportation")), "high")
        self.assertEqual(audit_priority(entry(resource_type="place", audit_frequency="annually")), "low")

    def test_workload_capacity_math(self):
        entries = [
            entry("monthly"),
            entry("annual", audit_frequency="annually", next_audit=date(2027, 1, 31)),
        ]
        summary = workload_summary(entries, capacity_per_week=1, as_of=date(2026, 8, 13))
        self.assertEqual(summary["audits_per_year"], 13)
        self.assertTrue(summary["backlog_recoverable"])
        self.assertGreater(summary["weekly_surplus"], 0)

    def test_reviewed_migration_inventory_is_locked(self):
        self.assertEqual(len(MIGRATION_IDS), 53)
        self.assertEqual(
            PRESERVE_DUE_IDS,
            {"thprd-financial-aid", "gresham-music-parks", "jade-night-market",
             "portland-sunday-parkways", "portland-memory-garden",
             "ops-fest-shakespeare", "multnomah-days", "first-thursday",
             "hollywood-farmers-market", "lynwood-community-farm",
             "portland-saturday-market"},
        )


class TestCorpusAuditPolicy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries = load_sources(ROOT / "data" / "sources.yaml")

    def test_corpus_has_valid_policy_metadata(self):
        self.assertEqual(validate_all_entries(self.entries, quiet=True), [])

    def test_cadence_migration_does_not_reverify_entries(self):
        source = """---
- id: sample
  name: Sample
  category: events
  location_type: varies
  resource_type: event
  source_urls:
  - https://example.org
  last_verified: 2026-01-31
  next_audit: 2026-04-30
  audit_frequency: quarterly
"""
        migrated, changes = migrate(source, {"sample"}, set())
        self.assertIn("last_verified: 2026-01-31", migrated)
        self.assertIn("next_audit: 2027-01-31", migrated)
        self.assertIn("audit_frequency: annually", migrated)
        self.assertEqual(len(changes), 1)

    def test_migration_is_now_applied_to_exact_inventory(self):
        by_id = {value["id"]: value for value in self.entries}
        self.assertTrue(all(by_id[entry_id]["audit_frequency"] == "annually" for entry_id in MIGRATION_IDS))
        active = [value for value in self.entries if value.get("status") != "CLOSED"]
        counts = {frequency: sum(value.get("audit_frequency") == frequency for value in active)
                  for frequency in ("monthly", "quarterly", "annually")}
        self.assertEqual(counts, {"monthly": 15, "quarterly": 128, "annually": 129})
        priorities = {priority: sum(audit_priority(value) == priority for value in active)
                      for priority in ("critical", "high", "standard", "low")}
        # juanita-pohl-center moved low -> high when its programs were converted
        # from an unreadable mapping into a list: one of them is an open-ended
        # recurring support group, which the policy rates higher precisely
        # because it now publishes to subscribers. The cadence inventory this
        # test locks is unchanged; only the derived priority moved.
        self.assertEqual(priorities, {"critical": 61, "high": 71, "standard": 12, "low": 128})
        summary = workload_summary(active, capacity_per_week=5, as_of=date(2026, 8, 13))
        self.assertEqual(summary["backlog"], 131)
        self.assertEqual(summary["audits_per_year"], 821)
        self.assertFalse(summary["backlog_recoverable"])

    def test_migration_is_idempotent_after_application(self):
        content = (ROOT / "data" / "sources.yaml").read_text(encoding="utf-8")
        migrated, changes = migrate(content)
        self.assertEqual(migrated, content)
        self.assertEqual(changes, [])

    def test_workload_cli_json_is_reproducible(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "audit_check.py"), "--workload", "--as-of", "2026-08-13", "--format", "json"],
            cwd=ROOT / "scripts",
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout)
        self.assertEqual(payload["as_of"], "2026-08-13")
        self.assertEqual(payload["active_entries"], 272)


if __name__ == "__main__":
    unittest.main(verbosity=2)
