import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def stanza(text, name):
    start = text.index(f"[{name}]\n")
    end = text.find("\n[", start + 1)
    return text[start:] if end == -1 else text[start:end]


class HomeboxBackupAlertsTest(unittest.TestCase):
    def setUp(self):
        self.saved = (ROOT / "default/savedsearches.conf").read_text()

    def test_failure_alert_uses_the_shared_os_macro_and_is_enabled(self):
        body = stanza(self.saved, "HomelabAlert - homebox backup failed")

        self.assertIn(
            'search = `homelab_os_log_indexes` "homebox-backup@" "Failed with result"',
            body,
        )
        self.assertIn("\ndisabled = 0\n", body)
        self.assertIn("action.zammad.param.correlation_key = $name$ - $result.unit$", body)

    def test_silence_alert_checks_26_hours_and_is_enabled(self):
        body = stanza(self.saved, "HomelabAlert - homebox backup silent")

        self.assertIn("`homelab_os_log_indexes`", body)
        self.assertIn('"Deactivated successfully"', body)
        self.assertIn("minutes_silent > 26*60", body)
        self.assertIn("appendpipe", body)
        self.assertIn("\ndisabled = 0\n", body)
        self.assertNotIn("Ships disabled", body)


if __name__ == "__main__":
    unittest.main()
