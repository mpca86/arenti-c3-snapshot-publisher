"""Standalone tests for fixed-time and legacy systemd timer generation."""
import unittest

from install_timer import timer_schedule


class TimerScheduleTests(unittest.TestCase):
    def test_hybe_default(self):
        self.assertEqual(
            timer_schedule(5),
            "OnCalendar=*-*-* *:04/5:00\n"
            "AccuracySec=1s\nRandomizedDelaySec=0\n",
        )

    def test_custom_offset(self):
        self.assertIn("OnCalendar=*-*-* *:00/5:00", timer_schedule(5, minute_offset=0))

    def test_hourly(self):
        self.assertIn("OnCalendar=*-*-* *:00:00", timer_schedule(60))

    def test_other_calendar_intervals(self):
        self.assertIn("OnCalendar=*-*-* *:00/10:00", timer_schedule(10))

    def test_legacy_interval(self):
        self.assertEqual(
            timer_schedule(5, schedule="interval"),
            "OnBootSec=1min\nOnUnitInactiveSec=5min\nAccuracySec=15s\n",
        )

    def test_invalid_calendar_interval(self):
        with self.assertRaises(ValueError):
            timer_schedule(7)

    def test_invalid_offset(self):
        with self.assertRaises(ValueError):
            timer_schedule(5, minute_offset=5)

    def test_interval_rejects_calendar_offset(self):
        with self.assertRaises(ValueError):
            timer_schedule(5, schedule="interval", minute_offset=4)


if __name__ == "__main__":
    unittest.main()
