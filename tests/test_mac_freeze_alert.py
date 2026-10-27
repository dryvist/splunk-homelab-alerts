import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def stanza(text, name):
    start = text.index(f"[{name}]\n")
    end = text.find("\n[", start + 1)
    return text[start:] if end == -1 else text[start:end]


class MacFreezeAlertTest(unittest.TestCase):
    def test_freeze_alert_covers_all_three_sources(self):
        saved = (ROOT / "default/savedsearches.conf").read_text()
        body = stanza(saved, "HomelabAlert - macOS freeze or WindowServer watchdog")

        self.assertIn("(index=mac_perf sourcetype=ws-monitor severity=FREEZE)", body)
        self.assertIn("(index=os source=*DiagnosticReports* \\", body)
        self.assertIn("source=*WindowServer* OR source=*.spin OR source=*.hang", body)
        self.assertIn('(index=os "synchronize timed out")', body)
        self.assertIn("| fields _time host gap_s top_processes source sourcetype", body)

    def test_freeze_alert_uses_five_minute_cadence_and_per_host_throttle(self):
        saved = (ROOT / "default/savedsearches.conf").read_text()
        body = stanza(saved, "HomelabAlert - macOS freeze or WindowServer watchdog")

        self.assertIn("\ndispatch.earliest_time = -6m\n", body)
        self.assertIn("\ncron_schedule = */5 * * * *\n", body)
        self.assertIn("\ndisabled = 0\n", body)
        self.assertIn(
            "\nalert.suppress = 1\nalert.suppress.period = 15m\n"
            "alert.suppress.fields = host\n",
            body,
        )
        self.assertIn(
            "\naction.zammad.param.correlation_key = $name$ - $result.host$\n",
            body,
        )
        self.assertIn(
            "\ncounttype = number of events\nrelation = greater than\nquantity = 0\n",
            body,
        )


if __name__ == "__main__":
    unittest.main()
