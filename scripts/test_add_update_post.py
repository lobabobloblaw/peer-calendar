"""Tests for add_update_post.py (Updates-section posts).

Run: python -m pytest test_add_update_post.py -v
  or: python test_add_update_post.py
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))

from add_update_post import (
    LIST_ANCHOR,
    insert_post,
    main,
    summarize,
    today_label,
    top_post_date,
)

PAGE = """<html><body>
                    <ul class="updates-list">
                        <li><span class="update-date">Jul 24</span> An older post</li>
                    </ul>
</body></html>
"""

AUG6 = datetime(2026, 8, 6)


def tmp_page(content: str = PAGE) -> Path:
    f = tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8")
    f.write(content)
    f.close()
    return Path(f.name)


def tmp_json(obj) -> Path:
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(obj, f)
    f.close()
    return Path(f.name)


def feed(*ids):
    return [{"id": i, "title": i.title()} for i in ids]


class TestCuratedInsert(unittest.TestCase):
    def test_lands_directly_after_anchor_with_date(self):
        page = tmp_page()
        insert_post(page, "Hello Portland", now=AUG6)
        lines = page.read_text(encoding="utf-8").splitlines()
        anchor_idx = next(i for i, l in enumerate(lines) if LIST_ANCHOR in l)
        self.assertEqual(
            lines[anchor_idx + 1],
            '                        <li><span class="update-date">Aug 6</span> Hello Portland</li>',
        )
        # previous top entry still follows on its own line
        self.assertIn("An older post", lines[anchor_idx + 2])

    def test_escapes_html(self):
        page = tmp_page()
        insert_post(page, "A & B <test>", now=AUG6)
        self.assertIn("A &amp; B &lt;test&gt;", page.read_text(encoding="utf-8"))

    def test_date_format_matches_existing_style(self):
        self.assertEqual(today_label(AUG6), "Aug 6")
        self.assertEqual(today_label(datetime(2026, 12, 25)), "Dec 25")


class TestTopPostDate(unittest.TestCase):
    def test_reads_top_date(self):
        self.assertEqual(top_post_date(PAGE), "Jul 24")

    def test_empty_list(self):
        page = f"<body>\n                    {LIST_ANCHOR}\n                    </ul>\n</body>"
        self.assertIsNone(top_post_date(page))


class TestAutoMode(unittest.TestCase):
    def run_auto(self, page: Path, before, after, today: datetime):
        b, a = tmp_json(before), tmp_json(after)
        argv = ["add_update_post.py", "--auto", "--before", str(b), "--after", str(a), "--index", str(page)]
        with mock.patch("sys.argv", argv), mock.patch("add_update_post.datetime") as md:
            md.now.return_value = today
            md.strftime = datetime.strftime
            main()

    def test_dedupes_when_today_already_posted(self):
        page = tmp_page(PAGE.replace("Jul 24", "Aug 6"))
        self.run_auto(page, feed("a"), feed("a", "b"), AUG6)
        self.assertEqual(page.read_text(encoding="utf-8").count("Aug 6"), 1)

    def test_posts_summary_when_new_day(self):
        page = tmp_page()  # top entry is Jul 24
        self.run_auto(page, feed("a"), feed("a", "b"), AUG6)
        text = page.read_text(encoding="utf-8")
        self.assertIn("Aug 6", text)
        self.assertIn("New: B", text)


class TestSummarize(unittest.TestCase):
    def test_added_removed_changed(self):
        before = {"a": {"id": "a", "title": "Alpha"}, "b": {"id": "b", "title": "Beta"},
                  "c": {"id": "c", "title": "Gamma", "x": 1}}
        after = {"a": {"id": "a", "title": "Alpha"}, "d": {"id": "d", "title": "Delta"},
                 "c": {"id": "c", "title": "Gamma", "x": 2}}
        s = summarize(before, after)
        self.assertIn("New: Delta", s)
        self.assertIn("Removed: Beta", s)
        self.assertIn("Updated data for 1 resource", s)
        self.assertTrue(s.endswith("Calendar now at 3 resources"))

    def test_caps_names(self):
        before = {}
        after = {str(i): {"id": str(i), "title": f"T{i}"} for i in range(5)}
        self.assertIn("and 2 more", summarize(before, after))

    def test_no_changes(self):
        same = {"a": {"id": "a", "title": "Alpha"}}
        self.assertEqual(summarize(same, same), "Calendar feeds refreshed")


if __name__ == "__main__":
    unittest.main()
