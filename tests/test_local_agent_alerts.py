import unittest
from pathlib import Path

from test_homebox_backup_alerts import stanza


ROOT = Path(__file__).resolve().parents[1]
ALERTS = (
    "HomelabAlert - local agent privacy violation",
    "HomelabAlert - local agent canary failed",
    "HomelabAlert - local agent silent",
)


class LocalAgentAlertsTest(unittest.TestCase):
    def setUp(self):
        self.saved = (ROOT / "default/savedsearches.conf").read_text()
        self.macros = (ROOT / "default/macros.conf").read_text()

    def test_alerts_are_disabled_and_use_the_shared_events_macro(self):
        macro = stanza(self.macros, "homelab_local_agent_events")

        self.assertIn("index=ai_usage", macro)
        self.assertIn('"resource.attributes.service.name"="local-agent"', macro)

        for name in ALERTS:
            with self.subTest(name=name):
                alert = stanza(self.saved, name)
                self.assertRegex(alert, r"(?m)^disabled = 1$")
                self.assertIn("`homelab_local_agent_events`", alert)

    def test_detectors_filter_the_requested_events(self):
        privacy = stanza(self.saved, ALERTS[0])
        canary = stanza(self.saved, ALERTS[1])

        self.assertIn("'attributes.reason'=\"privacy_violation\"", privacy)
        self.assertIn("'attributes.source'=\"canary\"", canary)
        self.assertIn("'attributes.status'=\"error\"", canary)

    def test_silence_search_handles_an_empty_event_set(self):
        silent = stanza(self.saved, ALERTS[2])

        self.assertIn("| stats count AS event_count", silent)
        self.assertIn("| where event_count=0 OR", silent)
        self.assertIn("| fields event_count, agents", silent)


if __name__ == "__main__":
    unittest.main()
