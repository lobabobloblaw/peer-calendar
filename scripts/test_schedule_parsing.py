"""Tests for schedule parsing and audience detection.

Run: python -m pytest test_schedule_parsing.py -v
  or: python test_schedule_parsing.py
"""
import sys
import os
import unittest

# Add scripts directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from generate_calendar import parse_schedule, detect_audience, get_entry_audience, get_program_audience


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
