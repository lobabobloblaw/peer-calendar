"""Tests for schedule parsing and audience detection.

Run: python -m pytest test_schedule_parsing.py -v
  or: python test_schedule_parsing.py
"""
import os
import re
import sys
import unittest
from datetime import date, datetime
from pathlib import Path

# Add scripts directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from generate_calendar import (
    build_recurring_event,
    detect_audience,
    get_entry_audience,
    get_program_audience,
    entry_to_events,
    generate_event_description,
    generate_json_feed,
    is_closed,
    parse_date_string,
    parse_schedule,
    resolve_fixed_schedule,
    resolve_recurring_schedule,
)
from utils import load_sources


class TestParseSchedule(unittest.TestCase):
    """Test the Python parse_schedule() function."""

    # --- Basic day detection ---

    def test_every_tuesday(self):
        result = parse_schedule("Every Tuesday 6-7pm")
        self.assertEqual(result["day"], "TU")
        self.assertTrue(result.get("weekly"))
        self.assertEqual(result["start_time"], "18:00")
        self.assertEqual(result["end_time"], "19:00")

    def test_every_friday(self):
        result = parse_schedule("Every Friday 6-7pm")
        self.assertEqual(result["day"], "FR")
        self.assertEqual(result["start_time"], "18:00")
        self.assertEqual(result["end_time"], "19:00")

    def test_plural_day(self):
        result = parse_schedule("Wednesdays 2-3:30pm")
        self.assertEqual(result["day"], "WE")
        self.assertEqual(result["start_time"], "14:00")
        self.assertEqual(result["end_time"], "15:30")

    # --- Multiple days ---

    def test_tuesdays_and_thursdays(self):
        result = parse_schedule("Tuesdays & Thursdays noon-1pm")
        self.assertIn("TU", result["day"])
        self.assertIn("TH", result["day"])
        self.assertEqual(result["start_time"], "12:00")
        self.assertEqual(result["end_time"], "13:00")

    def test_tue_thu_slash(self):
        result = parse_schedule("Tue/Thu 8-9am")
        self.assertIn("TU", result["day"])
        self.assertIn("TH", result["day"])
        self.assertEqual(result["start_time"], "08:00")
        self.assertEqual(result["end_time"], "09:00")

    # --- AM/PM inference ---

    def test_same_period_inference(self):
        """'2-10pm' should mean 2pm-10pm (both PM)."""
        result = parse_schedule("Every Saturday 2-10pm")
        self.assertEqual(result["start_time"], "14:00")
        self.assertEqual(result["end_time"], "22:00")

    def test_cross_period_inference(self):
        """'10-7pm' should mean 10am-7pm (AM to PM)."""
        result = parse_schedule("Every Monday 10-7pm")
        self.assertEqual(result["start_time"], "10:00")
        self.assertEqual(result["end_time"], "19:00")

    def test_explicit_am_pm(self):
        result = parse_schedule("Every Wednesday 10am-2pm")
        self.assertEqual(result["start_time"], "10:00")
        self.assertEqual(result["end_time"], "14:00")

    def test_both_am(self):
        result = parse_schedule("Every Sunday 8am-11am")
        self.assertEqual(result["start_time"], "08:00")
        self.assertEqual(result["end_time"], "11:00")

    def test_both_pm(self):
        result = parse_schedule("Every Friday 1pm-3pm")
        self.assertEqual(result["start_time"], "13:00")
        self.assertEqual(result["end_time"], "15:00")

    # --- Noon and midnight ---

    def test_noon(self):
        result = parse_schedule("Every Saturday noon-3pm")
        self.assertEqual(result["start_time"], "12:00")
        self.assertEqual(result["end_time"], "15:00")

    def test_noon_to_1pm(self):
        result = parse_schedule("Every Wednesday noon-1pm")
        self.assertEqual(result["start_time"], "12:00")
        self.assertEqual(result["end_time"], "13:00")

    # --- Ordinal weeks ---

    def test_1st_and_3rd_wednesday(self):
        result = parse_schedule("1st and 3rd Wednesday 2-3:30pm")
        self.assertEqual(result["week_of_month"], [1, 3])
        self.assertEqual(result["day"], "WE")
        self.assertEqual(result["start_time"], "14:00")
        self.assertEqual(result["end_time"], "15:30")

    def test_2nd_and_4th_monday(self):
        result = parse_schedule("2nd and 4th Monday 6-7:30pm")
        self.assertEqual(result["week_of_month"], [2, 4])
        self.assertEqual(result["day"], "MO")

    def test_1st_friday(self):
        result = parse_schedule("1st Friday 5-9pm")
        self.assertEqual(result["week_of_month"], [1])
        self.assertEqual(result["day"], "FR")
        self.assertEqual(result["start_time"], "17:00")
        self.assertEqual(result["end_time"], "21:00")

    # --- Minutes parsing ---

    def test_half_hour(self):
        result = parse_schedule("Every Thursday 6:30-8pm")
        self.assertEqual(result["start_time"], "18:30")
        self.assertEqual(result["end_time"], "20:00")

    def test_quarter_hour(self):
        result = parse_schedule("Every Monday 11:30am-12:45pm")
        self.assertEqual(result["start_time"], "11:30")
        self.assertEqual(result["end_time"], "12:45")

    # --- Edge cases ---

    def test_empty_string(self):
        result = parse_schedule("")
        self.assertEqual(result, {})

    def test_none_input(self):
        result = parse_schedule(None)
        self.assertEqual(result, {})

    def test_no_time(self):
        """Schedule with day but no time should still extract day."""
        result = parse_schedule("Every Saturday")
        self.assertEqual(result["day"], "SA")
        self.assertTrue(result.get("weekly"))
        self.assertNotIn("start_time", result)

    def test_12pm(self):
        """12pm should remain 12:00, not become 24:00."""
        result = parse_schedule("Every Monday 12pm-1pm")
        self.assertEqual(result["start_time"], "12:00")
        self.assertEqual(result["end_time"], "13:00")

    def test_12am(self):
        """12am (midnight) should become 00:00."""
        result = parse_schedule("Every Friday 12am-2am")
        self.assertEqual(result["start_time"], "00:00")
        self.assertEqual(result["end_time"], "02:00")

    def test_weekdays(self):
        """'Weekdays' should expand to Monday-Friday."""
        result = parse_schedule("Weekdays noon-12:30pm")
        self.assertEqual(result["day"], "MO,TU,WE,TH,FR")
        self.assertEqual(result["start_time"], "12:00")
        self.assertEqual(result["end_time"], "12:30")


    # --- Day ranges ---

    def test_mon_fri_range(self):
        """'Mon-Fri 6:30am-9:30pm' should expand to all weekdays."""
        result = parse_schedule("Mon-Fri 6:30am-9:30pm")
        self.assertEqual(result["day"], "MO,TU,WE,TH,FR")
        self.assertEqual(result["start_time"], "06:30")
        self.assertEqual(result["end_time"], "21:30")

    def test_sat_sun_range(self):
        """'Sat-Sun 2:30-4:30pm' should expand to SA,SU."""
        result = parse_schedule("Sat-Sun 2:30-4:30pm")
        self.assertEqual(result["day"], "SA,SU")
        self.assertEqual(result["start_time"], "14:30")
        self.assertEqual(result["end_time"], "16:30")

    def test_wed_sat_range(self):
        """'Wed-Sat 6:30-7:45am' should expand to WE,TH,FR,SA."""
        result = parse_schedule("Wed-Sat 6:30-7:45am")
        self.assertEqual(result["day"], "WE,TH,FR,SA")
        self.assertEqual(result["start_time"], "06:30")
        self.assertEqual(result["end_time"], "07:45")

    def test_explicit_days_override_range(self):
        """When full day names are present, they should take priority over range."""
        result = parse_schedule("Tuesdays and Thursdays 5-6pm")
        self.assertIn("TU", result["day"])
        self.assertIn("TH", result["day"])

    # --- Last of month ---

    def test_last_sunday(self):
        """'Last Sunday of each month 4-6pm' should set last_of_month."""
        result = parse_schedule("Last Sunday of each month 4-6pm")
        self.assertTrue(result.get("last_of_month"))
        self.assertEqual(result["day"], "SU")
        self.assertEqual(result["start_time"], "16:00")
        self.assertEqual(result["end_time"], "18:00")

    def test_last_wednesday(self):
        """'Last Wednesday 12-12am' should set last_of_month."""
        result = parse_schedule("Last Wednesday 12-12am")
        self.assertTrue(result.get("last_of_month"))
        self.assertIn("WE", result["day"])

    def test_last_friday_of_month(self):
        """'Last Friday of month, signups 6:30pm, show 7pm' should detect last + day."""
        result = parse_schedule("Last Friday of month, signups 6:30pm, show 7pm")
        self.assertTrue(result.get("last_of_month"))
        self.assertEqual(result["day"], "FR")

    # --- Every other / bi-weekly ---

    def test_every_other_monday(self):
        """'Every other Monday 1-3pm' should set interval=2."""
        result = parse_schedule("Every other Monday 1-3pm")
        self.assertEqual(result.get("interval"), 2)
        self.assertEqual(result["day"], "MO")
        self.assertEqual(result["start_time"], "13:00")
        self.assertEqual(result["end_time"], "15:00")

    def test_every_other_wednesday(self):
        """'Every other Wednesday 6:30-8:30pm' should set interval=2."""
        result = parse_schedule("Every other Wednesday 6:30-8:30pm")
        self.assertEqual(result.get("interval"), 2)
        self.assertIn("WE", result["day"])


class TestDetectAudience(unittest.TestCase):
    """Test the audience detection pattern matching."""

    def test_seniors(self):
        self.assertIn("seniors", detect_audience("Senior center activities for 65+"))

    def test_seniors_older_adults(self):
        self.assertIn("seniors", detect_audience("Programs for older adults"))

    def test_children(self):
        self.assertIn("children", detect_audience("Children's art classes ages 3-12"))

    def test_adult_children_false_positive(self):
        """'Adult Children of Alcoholics' should NOT detect children."""
        result = detect_audience("Adult Children of Alcoholics support group")
        self.assertNotIn("children", result)

    def test_teens(self):
        self.assertIn("teens", detect_audience("Teen support group ages 13-17"))

    def test_young_adults(self):
        self.assertIn("young_adults", detect_audience("Young Adult peer group (18-35)"))

    def test_lgbtq(self):
        self.assertIn("lgbtq", detect_audience("LGBTQ+ support and social group"))

    def test_pride(self):
        self.assertIn("lgbtq", detect_audience("Portland Pride Festival"))

    def test_trans_nonbinary(self):
        self.assertIn("trans_nonbinary", detect_audience("Trans and nonbinary support group"))

    def test_women(self):
        self.assertIn("women", detect_audience("Women's peer support circle"))

    def test_bipoc(self):
        self.assertIn("bipoc", detect_audience("BIPOC mental health support"))

    def test_spanish(self):
        self.assertIn("spanish_speaking", detect_audience("Grupo de apoyo en Espanol"))

    def test_no_audience(self):
        result = detect_audience("Free community yoga in the park")
        self.assertEqual(result, [])

    def test_empty(self):
        self.assertEqual(detect_audience(""), [])

    def test_none(self):
        self.assertEqual(detect_audience(None), [])

    def test_multiple_audiences(self):
        result = detect_audience("LGBTQ+ youth group for teens and young adults")
        self.assertIn("lgbtq", result)
        self.assertIn("teens", result)
        self.assertIn("young_adults", result)


class TestGetEntryAudience(unittest.TestCase):
    """Test entry-level audience resolution."""

    def test_explicit_audience(self):
        entry = {"audience": ["seniors", "women"]}
        self.assertEqual(get_entry_audience(entry), ["seniors", "women"])

    def test_detected_from_name(self):
        entry = {"name": "Senior Lunch Program"}
        result = get_entry_audience(entry)
        self.assertIn("seniors", result)

    def test_detected_from_eligibility(self):
        entry = {"name": "Support Group", "eligibility": "Adults 65+"}
        result = get_entry_audience(entry)
        self.assertIn("seniors", result)

    def test_detected_from_practical_tips_dict(self):
        entry = {
            "name": "Community Center",
            "practical_tips": {"good_to_know": "Popular with LGBTQ+ community"}
        }
        result = get_entry_audience(entry)
        self.assertIn("lgbtq", result)

    def test_no_audience(self):
        entry = {"name": "Free Yoga", "notes": "Open to all"}
        self.assertEqual(get_entry_audience(entry), [])


class TestGetProgramAudience(unittest.TestCase):
    """Test program-level audience resolution with fallback."""

    def test_explicit_program_audience(self):
        program = {"name": "Support Group", "audience": ["women"]}
        entry = {"name": "NAMI"}
        self.assertEqual(get_program_audience(program, entry), ["women"])

    def test_detected_from_program_name(self):
        program = {"name": "BIPOC Support Group"}
        entry = {"name": "NAMI Multnomah"}
        result = get_program_audience(program, entry)
        self.assertIn("bipoc", result)

    def test_falls_back_to_entry(self):
        program = {"name": "General Support"}
        entry = {"name": "Senior Center Activities", "eligibility": "Adults 55+"}
        result = get_program_audience(program, entry)
        self.assertIn("seniors", result)


class TestDayRanges(unittest.TestCase):
    """Day ranges must expand fully and coexist with standalone day names."""

    def test_full_name_range(self):
        """'Monday-Friday' must expand, not collapse to the two endpoints."""
        self.assertEqual(parse_schedule("Monday-Friday 8am-5pm")["day"], "MO,TU,WE,TH,FR")

    def test_range_plus_standalone_day(self):
        """'Fri ...; Sat-Sun ...' keeps Friday alongside the weekend range."""
        result = parse_schedule("Fri 11am-1pm & 4-7pm; Sat-Sun 2:30-4:30pm")
        self.assertEqual(result["day"], "FR,SA,SU")

    def test_wrap_around_range(self):
        self.assertEqual(parse_schedule("Sat-Tue 9-10am")["day"], "MO,TU,SA,SU")

    def test_days_are_ordered_monday_first(self):
        self.assertEqual(parse_schedule("Thursdays and Tuesdays 6-7pm")["day"], "TU,TH")

    def test_daily_does_not_override_explicit_days(self):
        """'daily' inside prose must not widen a specific range to all week."""
        result = parse_schedule("Fri-Sun (check Facebook for daily schedule)")
        self.assertEqual(result["day"], "FR,SA,SU")
        self.assertNotIn("daily", result)

    def test_daily_still_expands_when_alone(self):
        result = parse_schedule("Daily 2-10pm")
        self.assertEqual(result["day"], "MO,TU,WE,TH,FR,SA,SU")
        self.assertTrue(result.get("daily"))


class TestParseDateString(unittest.TestCase):
    """Date strings for one-time events."""

    TODAY = date(2026, 7, 24)

    def parse(self, text):
        return parse_date_string(text, today=self.TODAY)

    def test_same_month_range(self):
        start, end = self.parse("July 17-19, 2026 (46th annual)")
        self.assertEqual((start.date(), end.date()), (date(2026, 7, 17), date(2026, 7, 19)))

    def test_cross_month_range_keeps_stated_year(self):
        """'May 22 - June 28, 2026' used to collapse to a single day in 2027."""
        start, end = self.parse("May 22 - June 28, 2026")
        self.assertEqual((start.date(), end.date()), (date(2026, 5, 22), date(2026, 6, 28)))

    def test_month_span_without_days(self):
        start, end = self.parse("June through August 2026")
        self.assertEqual((start.date(), end.date()), (date(2026, 6, 1), date(2026, 8, 31)))

    def test_year_less_date_uses_next_occurrence(self):
        """No year written: December is still ahead of us in July, so this year."""
        start, end = self.parse("December 15-31, 6-11pm nightly")
        self.assertEqual((start.date(), end.date()), (date(2026, 12, 15), date(2026, 12, 31)))

    def test_year_less_past_date_rolls_forward(self):
        start, _ = self.parse("February 6")
        self.assertEqual(start.date(), date(2027, 2, 6))

    def test_single_date(self):
        start, end = self.parse("November 27, 2026 (day after Thanksgiving), 5:30-6:45pm")
        self.assertEqual(start.date(), date(2026, 11, 27))
        self.assertIsNone(end)

    def test_unparseable(self):
        self.assertEqual(self.parse("Various dates"), (None, None))


class TestRecurrenceRules(unittest.TestCase):
    """DTSTART must be a real occurrence of the RRULE it carries.

    Every fixture that carries a ``schedule_end_date`` builds against
    ``FROZEN_TODAY`` rather than the wall clock. The generator drops a
    recurrence whose window has already closed, so a fixture window dated in
    the past would make these tests start failing on a calendar date rather
    than on a code change -- which is what happened on 2026-09-01, when the
    weekly publish stopped because the test suite runs before generation.
    """

    FROZEN_TODAY = date(2026, 8, 1)

    def build(self, schedule_str, entry=None):
        return build_recurring_event(
            schedule=parse_schedule(schedule_str),
            entry=entry or {},
            summary="Test", description="d", html_desc="d", location="",
            uid="uid@test", website="", category="events", platform="google",
            today=self.FROZEN_TODAY,
        )

    def rrule_of(self, vevent):
        return next(line for line in vevent.split("\r\n") if line.startswith("RRULE:"))

    def dtstart_of(self, vevent):
        line = next(line for line in vevent.split("\r\n") if line.startswith("DTSTART"))
        return datetime.strptime(line.split(":")[1][:8], "%Y%m%d").date()

    def test_nth_weekday_uses_prefixed_byday(self):
        """BYSETPOS over multiple days means 'first of either', not 'both firsts'."""
        vevent = self.build("1st Tuesday and 1st Saturday 6-7pm")
        self.assertIn("BYDAY=1TU,1SA", self.rrule_of(vevent))
        self.assertNotIn("BYSETPOS", self.rrule_of(vevent))

    def test_dtstart_matches_monthly_rule(self):
        """The 1st/3rd Sunday rule must not start on a 4th Sunday."""
        vevent = self.build("1st and 3rd Sunday 2-3pm", {"schedule_start_date": "2026-07-24"})
        dtstart = self.dtstart_of(vevent)
        self.assertEqual(dtstart.weekday(), 6)
        self.assertIn((dtstart.day - 1) // 7 + 1, (1, 3))

    def test_last_of_month_rule(self):
        vevent = self.build("Last Wednesday of each month 12-1pm",
                            {"schedule_start_date": "2026-07-01"})
        self.assertIn("BYDAY=-1WE", self.rrule_of(vevent))
        self.assertEqual(self.dtstart_of(vevent), date(2026, 7, 29))

    def test_weekly_dtstart_is_soonest_listed_day(self):
        vevent = self.build("Tue/Thu 8-9am", {"schedule_start_date": "2026-07-24"})
        self.assertEqual(self.dtstart_of(vevent), date(2026, 7, 28))

    def test_overnight_event_ends_after_it_starts(self):
        """'12-12am' is noon to midnight, so DTEND belongs on the next day."""
        vevent = self.build("Last Wednesday 12-12am", {"schedule_start_date": "2026-07-01"})
        lines = dict(line.split(":", 1) for line in vevent.split("\r\n") if ":" in line)
        dtstart = next(v for k, v in lines.items() if k.startswith("DTSTART"))
        dtend = next(v for k, v in lines.items() if k.startswith("DTEND"))
        self.assertGreater(dtend, dtstart)

    def test_until_is_utc(self):
        """RFC 5545: UNTIL must be UTC when DTSTART carries a TZID."""
        vevent = self.build("Every Tuesday 6-7pm", {
            "schedule_start_date": "2026-07-01", "schedule_end_date": "2026-08-31",
        })
        until = self.rrule_of(vevent).split("UNTIL=")[1].split(";")[0]
        self.assertTrue(until.endswith("Z"), until)
        self.assertEqual(until, "20260901T065959Z")  # 23:59:59 PDT

    def test_expired_window_produces_no_event(self):
        """A program whose end date has passed must not be published at all."""
        self.assertIsNone(self.build("Every Tuesday 6-7pm", {"schedule_end_date": "2020-03-01"}))

    def test_bounded_fixtures_are_independent_of_the_wall_clock(self):
        """A closed fixture window must still build, because today is frozen.

        The UNTIL fixture above ends 2026-08-31, a date that is now in the
        past and recedes further every day. This test fails the moment
        ``build()`` stops passing ``FROZEN_TODAY``, which is the only reason
        that fixture still resolves.
        """
        self.assertLess(date(2026, 8, 31), date.today())
        self.assertIsNotNone(self.build("Every Tuesday 6-7pm", {
            "schedule_start_date": "2026-07-01", "schedule_end_date": "2026-08-31",
        }))


class TestResolvedScheduleContract(unittest.TestCase):
    """The web feed receives the same normalized recurrence used by ICS."""

    TODAY = date(2026, 8, 1)

    def event(self, entry):
        return generate_json_feed([entry], today=self.TODAY)["events"][0]

    def test_feed_declares_schema_version(self):
        feed = generate_json_feed([], today=self.TODAY)
        self.assertEqual(feed["schedule_schema_version"], 1)

    def test_biweekly_schedule_has_stable_anchor(self):
        resolved = resolve_recurring_schedule(
            parse_schedule("Every other Tuesday 6:30-8:30pm"),
            {"schedule_start_date": "2026-08-01"},
            today=self.TODAY,
        )
        self.assertEqual(resolved, {
            "type": "recurring",
            "frequency": "weekly",
            "interval": 2,
            "weekdays": ["TU"],
            "month_weeks": [],
            "anchor_date": "2026-08-04",
            "until_date": None,
            "start_time": "18:30",
            "end_time": "20:30",
            "end_day_offset": 0,
        })

    def test_second_biweekly_anchor_regression(self):
        resolved = resolve_recurring_schedule(
            parse_schedule("Every other Wednesday 6-8pm"),
            {"schedule_start_date": "2026-08-12"},
            today=self.TODAY,
        )
        self.assertEqual(resolved["anchor_date"], "2026-08-12")
        self.assertEqual(resolved["interval"], 2)

    def test_ordinal_monthly_schedule(self):
        resolved = resolve_recurring_schedule(
            parse_schedule("1st & 3rd Mondays, 1pm"),
            {"schedule_start_date": "2026-08-01"},
            today=self.TODAY,
        )
        self.assertEqual(resolved["frequency"], "monthly")
        self.assertEqual(resolved["month_weeks"], [1, 3])
        self.assertEqual(resolved["weekdays"], ["MO"])
        self.assertEqual(resolved["anchor_date"], "2026-08-03")
        self.assertEqual((resolved["start_time"], resolved["end_time"]), ("13:00", "14:00"))

    def test_last_of_month_normalizes_to_negative_one(self):
        resolved = resolve_recurring_schedule(
            parse_schedule("Last Sunday of each month 4-6pm"),
            {"schedule_start_date": "2026-08-01"},
            today=self.TODAY,
        )
        self.assertEqual(resolved["month_weeks"], [-1])
        self.assertEqual(resolved["anchor_date"], "2026-08-30")

    def test_daily_normalizes_to_weekly_all_days(self):
        resolved = resolve_recurring_schedule(
            parse_schedule("Daily 2-10pm"), {}, today=self.TODAY,
        )
        self.assertEqual(resolved["frequency"], "weekly")
        self.assertEqual(resolved["weekdays"], ["MO", "TU", "WE", "TH", "FR", "SA", "SU"])

    def test_bounds_are_inclusive_and_anchor_is_valid(self):
        resolved = resolve_recurring_schedule(
            parse_schedule("Mondays 6-7pm"),
            {"schedule_start_date": "2026-08-05", "schedule_end_date": "2026-09-07"},
            today=self.TODAY,
        )
        self.assertEqual(resolved["anchor_date"], "2026-08-10")
        self.assertEqual(resolved["until_date"], "2026-09-07")

    def test_overnight_schedule_carries_end_day_offset(self):
        resolved = resolve_recurring_schedule(
            parse_schedule("Fridays 10pm-2am"),
            {"schedule_start_date": "2026-08-01"},
            today=self.TODAY,
        )
        self.assertEqual((resolved["start_time"], resolved["end_time"]), ("22:00", "02:00"))
        self.assertEqual(resolved["end_day_offset"], 1)

    def test_fixed_entry_occurrences_are_all_day(self):
        event = self.event({
            "id": "festival", "name": "Festival", "category": "events",
            "dates": ["August 15, 2026", "September 4-6, 2026"],
        })
        self.assertEqual(event["resolved_schedule"], {
            "type": "fixed",
            "occurrences": [
                {
                    "start_date": "2026-08-15", "end_date": "2026-08-15",
                    "all_day": True, "start_time": None, "end_time": None,
                    "end_day_offset": 0,
                },
                {
                    "start_date": "2026-09-04", "end_date": "2026-09-06",
                    "all_day": True, "start_time": None, "end_time": None,
                    "end_day_offset": 0,
                },
            ],
        })

    def test_fixed_program_can_be_timed_and_overnight(self):
        resolved = resolve_fixed_schedule(
            "August 15, 2026", "10pm-2am", today=self.TODAY,
        )
        self.assertEqual(resolved["occurrences"][0], {
            "start_date": "2026-08-15", "end_date": "2026-08-15",
            "all_day": False, "start_time": "22:00", "end_time": "02:00",
            "end_day_offset": 1,
        })

    def test_fixed_date_range_stays_all_day_even_with_times(self):
        resolved = resolve_fixed_schedule(
            "August 15-16, 2026", "6-8pm", today=self.TODAY,
        )
        occurrence = resolved["occurrences"][0]
        self.assertTrue(occurrence["all_day"])
        self.assertIsNone(occurrence["start_time"])

    def test_vague_or_incomplete_schedules_resolve_to_null(self):
        for raw in ("Call for schedule", "Every Saturday", None):
            entry = {
                "id": "vague", "name": "Vague", "category": "events",
                "schedule": raw,
            }
            self.assertIsNone(self.event(entry)["resolved_schedule"])
        self.assertIsNone(resolve_fixed_schedule("Various dates", today=self.TODAY))

    def test_program_bounds_inherit_and_override_independently(self):
        event = self.event({
            "id": "bounded", "name": "Bounded", "category": "events",
            "schedule_start_date": "2026-08-01",
            "schedule_end_date": "2026-12-31",
            "programs": [
                {"name": "Inherited", "schedule": "Mondays 6-7pm"},
                {
                    "name": "Overridden", "schedule": "Mondays 6-7pm",
                    "schedule_start_date": "2026-09-01",
                    "schedule_end_date": "2026-10-31",
                },
            ],
        })
        inherited, overridden = [program["resolved_schedule"] for program in event["programs"]]
        self.assertEqual((inherited["anchor_date"], inherited["until_date"]),
                         ("2026-08-03", "2026-12-31"))
        self.assertEqual((overridden["anchor_date"], overridden["until_date"]),
                         ("2026-09-07", "2026-10-31"))

    def test_entry_schedule_is_suppressed_when_programs_exist(self):
        event = self.event({
            "id": "parent", "name": "Parent", "category": "events",
            "schedule": "Sundays 9-10am",
            "programs": [{"name": "Child", "schedule": "Tuesdays 6-7pm"}],
        })
        self.assertIsNone(event["resolved_schedule"])
        self.assertEqual(event["programs"][0]["resolved_schedule"]["weekdays"], ["TU"])

    def test_dates_take_precedence_over_entry_schedule(self):
        event = self.event({
            "id": "one-off", "name": "One-off", "category": "events",
            "dates": "August 20, 2026", "schedule": "Thursdays 6-7pm",
        })
        self.assertEqual(event["resolved_schedule"]["type"], "fixed")
        self.assertTrue(event["resolved_schedule"]["occurrences"][0]["all_day"])

    def test_entry_dates_and_programs_both_resolve(self):
        event = self.event({
            "id": "mixed", "name": "Mixed", "category": "events",
            "dates": "August 20, 2026",
            "programs": [{"name": "Child", "schedule": "Tuesdays 6-7pm"}],
        })
        self.assertEqual(event["resolved_schedule"]["type"], "fixed")
        self.assertEqual(event["programs"][0]["resolved_schedule"]["type"], "recurring")

    def test_program_cost_overrides_entry_pricing(self):
        description, html_description = generate_event_description(
            {"category": "events", "pricing": {"description": "FREE admission"}},
            {"name": "Fundraiser", "cost": "$50"},
        )
        self.assertIn("Cost: $50", description)
        self.assertNotIn("FREE admission", description)
        self.assertIn("<strong>Cost:</strong> $50", html_description)


class TestDeterministicOutput(unittest.TestCase):
    """Regenerating unchanged data must produce byte-identical feeds.

    DTSTART used to be anchored to the wall clock, so every CI run rewrote all
    three platform feeds and buried real changes in a ~2,900-line diff.
    """

    ENTRY = {
        "id": "test-group", "name": "Test Group", "category": "peer_support",
        "schedule": "1st and 3rd Wednesday 2-3:30pm", "last_verified": date(2026, 3, 1),
    }

    def test_repeated_generation_is_identical(self):
        self.assertEqual(entry_to_events(self.ENTRY), entry_to_events(self.ENTRY))

    def test_dtstamp_comes_from_last_verified(self):
        vevent = entry_to_events(self.ENTRY)[0]
        self.assertIn("DTSTAMP:20260301T000000Z", vevent)

    def test_dtstamp_changes_only_when_data_does(self):
        reverified = dict(self.ENTRY, last_verified=date(2026, 7, 1))
        self.assertNotEqual(entry_to_events(self.ENTRY), entry_to_events(reverified))

    def test_anchor_is_a_valid_occurrence(self):
        """A fixed anchor still has to satisfy the rule it is attached to."""
        vevent = entry_to_events(self.ENTRY)[0]
        line = next(l for l in vevent.split("\r\n") if l.startswith("DTSTART"))
        dtstart = datetime.strptime(line.split(":")[1][:8], "%Y%m%d").date()
        self.assertEqual(dtstart.weekday(), 2)
        self.assertIn((dtstart.day - 1) // 7 + 1, (1, 3))


class TestFeedCarriesAccessFields(unittest.TestCase):
    """Fields the feed used to drop, which the site therefore could not show."""

    TODAY = date(2026, 8, 1)

    def feed_entry(self, **overrides):
        entry = {
            "id": "fields-test", "name": "Fields Test", "category": "food_farms",
            "last_verified": date(2026, 3, 1),
        }
        entry.update(overrides)
        return generate_json_feed([entry], today=self.TODAY)["events"][0]

    def test_branch_locations_reach_the_feed(self):
        """Several entries keep every real address here and leave address null."""
        locations = [{"name": "Northeast", "address": "4837 NE Couch St", "hours": "Mon 10am-2pm"}]
        self.assertEqual(self.feed_entry(locations=locations)["locations"], locations)

    def test_services_transit_parking_and_season_reach_the_feed(self):
        entry = self.feed_entry(
            services=["Food pantry", "Clothing closet"],
            transit="Bus 72", parking="Free on weekends", season="June-August",
        )
        self.assertEqual(entry["services"], ["Food pantry", "Clothing closet"])
        self.assertEqual(entry["transit"], "Bus 72")
        self.assertEqual(entry["parking"], "Free on weekends")
        self.assertEqual(entry["season"], "June-August")

    def test_temporarily_closed_status_reaches_the_feed(self):
        self.assertEqual(self.feed_entry(status="TEMPORARILY CLOSED")["status"], "TEMPORARILY CLOSED")

    def test_absent_fields_stay_empty(self):
        entry = self.feed_entry()
        self.assertEqual(entry["locations"], [])
        self.assertEqual(entry["services"], [])
        self.assertIsNone(entry["transit"])
        self.assertIsNone(entry["status"])


class TestLanguageAudience(unittest.TestCase):
    """A Spanish-language service serves Spanish speakers even if no prose says so."""

    def test_languages_string_implies_the_tag(self):
        self.assertEqual(
            get_entry_audience({"languages": "English, Spanish, Russian"}),
            ["spanish_speaking"],
        )

    def test_languages_list_implies_the_tag(self):
        self.assertIn(
            "spanish_speaking",
            get_entry_audience({"languages": ["English", "Spanish (Linea de Esperanza)"]}),
        )

    def test_explicit_audience_is_kept_and_extended(self):
        """An author's own tags must survive, in their own order."""
        audience = get_entry_audience({"audience": ["seniors"], "languages": "Spanish"})
        self.assertEqual(audience, ["seniors", "spanish_speaking"])

    def test_other_languages_do_not_imply_the_tag(self):
        self.assertEqual(get_entry_audience({"languages": "Arabic, Vietnamese"}), [])

    def test_spanish_language_prose_is_detected(self):
        self.assertIn(
            "spanish_speaking",
            get_entry_audience({"notes": "Spanish-language support group available."}),
        )

    def test_no_duplicate_when_prose_and_languages_agree(self):
        audience = get_entry_audience(
            {"languages": "Spanish", "notes": "Spanish-speaking group available."}
        )
        self.assertEqual(audience.count("spanish_speaking"), 1)


class TestTemporarilyClosedDescription(unittest.TestCase):
    """A resource that is shut must say so on any event it still publishes."""

    def test_warning_leads_the_description(self):
        text, html_text = generate_event_description(
            {"id": "x", "name": "X", "category": "food_farms", "status": "TEMPORARILY CLOSED"}
        )
        self.assertTrue(text.startswith("TEMPORARILY CLOSED - check before travelling"), text[:60])
        self.assertIn("TEMPORARILY CLOSED", html_text)

    def test_open_resources_carry_no_warning(self):
        text, _ = generate_event_description({"id": "x", "name": "X", "category": "food_farms"})
        self.assertNotIn("check before travelling", text)


class TestEntryScheduleFallback(unittest.TestCase):
    """An entry-level schedule is used unless a program supplies its own timing.

    Suppressing it whenever `programs` was merely non-empty meant an entry whose
    programs are a list of offerings published nothing at all, even with a
    perfectly good schedule of its own.
    """

    BASE = {
        "id": "fallback-test", "name": "Fallback Test", "category": "social_activities",
        "schedule": "Every Monday 6-7pm", "last_verified": date(2026, 3, 1),
    }

    def test_offering_list_does_not_suppress_the_entry_schedule(self):
        entry = dict(self.BASE, programs=[{"name": "Drawing"}, {"name": "Painting"}])
        self.assertEqual(len(entry_to_events(entry)), 1)

    def test_a_scheduled_program_still_takes_precedence(self):
        """Otherwise the entry and its program would both publish the same slot."""
        entry = dict(self.BASE, programs=[{"name": "Class", "schedule": "Every Tuesday 6-7pm"}])
        vevents = entry_to_events(entry)
        self.assertEqual(len(vevents), 1)
        self.assertIn("BYDAY=TU", vevents[0])

    def test_a_dated_program_also_takes_precedence(self):
        entry = dict(self.BASE, programs=[{"name": "One-off", "dates": "August 15, 2026"}])
        self.assertEqual(len(entry_to_events(entry)), 1)

    def test_no_programs_behaves_as_before(self):
        self.assertEqual(len(entry_to_events(dict(self.BASE))), 1)

    def test_json_feed_agrees_with_the_ics_feed(self):
        """A divergence here is exactly the class of bug the parity test exists for."""
        entry = dict(self.BASE, programs=[{"name": "Drawing"}])
        feed_entry = generate_json_feed([entry], today=date(2026, 8, 1))["events"][0]
        self.assertIsNotNone(feed_entry["resolved_schedule"])
        self.assertEqual(feed_entry["resolved_schedule"]["weekdays"], ["MO"])

    def test_json_feed_omits_entry_schedule_when_a_program_has_one(self):
        entry = dict(self.BASE, programs=[{"name": "Class", "schedule": "Every Tuesday 6-7pm"}])
        feed_entry = generate_json_feed([entry], today=date(2026, 8, 1))["events"][0]
        self.assertIsNone(feed_entry["resolved_schedule"])


class TestClosedEntries(unittest.TestCase):
    """Permanently closed resources must not reach the published feeds."""

    def test_status_field(self):
        self.assertTrue(is_closed({"id": "x", "status": "CLOSED"}))

    def test_closed_flag(self):
        self.assertTrue(is_closed({"id": "x", "flags": ["❌ CLOSED - funding cuts"]}))

    def test_open_entry(self):
        self.assertFalse(is_closed({"id": "x", "flags": ["🔄 SEASONAL"]}))


class TestPublishedUidUniqueness(unittest.TestCase):
    """Calendar clients use UID as identity; every VEVENT needs its own."""

    def test_all_generated_vevents_have_unique_uids(self):
        sources_path = Path(__file__).resolve().parents[1] / "data" / "sources.yaml"
        vevents = [
            vevent
            for entry in load_sources(sources_path)
            if not is_closed(entry)
            for vevent in entry_to_events(entry, platform="google")
        ]
        uids = [
            re.search(r"^UID:(.+)$", vevent, re.MULTILINE).group(1).rstrip("\r")
            for vevent in vevents
        ]
        duplicates = sorted({uid for uid in uids if uids.count(uid) > 1})
        self.assertEqual(duplicates, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
