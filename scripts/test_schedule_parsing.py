"""Tests for schedule parsing and audience detection.

Run: python -m pytest test_schedule_parsing.py -v
  or: python test_schedule_parsing.py
"""
import sys
import os
import unittest
from datetime import date, datetime

# Add scripts directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from generate_calendar import (
    build_recurring_event,
    detect_audience,
    get_entry_audience,
    get_program_audience,
    is_closed,
    parse_date_string,
    parse_schedule,
)


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
    """DTSTART must be a real occurrence of the RRULE it carries."""

    def build(self, schedule_str, entry=None):
        return build_recurring_event(
            schedule=parse_schedule(schedule_str),
            entry=entry or {},
            summary="Test", description="d", html_desc="d", location="",
            uid="uid@test", website="", category="events", platform="google",
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


class TestClosedEntries(unittest.TestCase):
    """Permanently closed resources must not reach the published feeds."""

    def test_status_field(self):
        self.assertTrue(is_closed({"id": "x", "status": "CLOSED"}))

    def test_closed_flag(self):
        self.assertTrue(is_closed({"id": "x", "flags": ["❌ CLOSED - funding cuts"]}))

    def test_open_entry(self):
        self.assertFalse(is_closed({"id": "x", "flags": ["🔄 SEASONAL"]}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
