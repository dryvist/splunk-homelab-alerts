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
        self.macros = (ROOT / "default/macros.conf").read_text()

    def test_homebox_backup_and_check_units_use_shared_cadence_macros(self):
        daily = stanza(self.macros, "homelab_daily_backup_units")
        weekly = stanza(self.macros, "homelab_weekly_backup_units")

        self.assertIn('"homebox-backup@"', daily)
        self.assertIn('"homebox-check@"', weekly)

    def test_generic_detectors_replace_duplicate_homebox_alerts(self):
        failures = stanza(self.saved, "HomelabAlert - backup unit failed")
        daily = stanza(self.saved, "HomelabAlert - nightly backup silent")

        self.assertIn("homelab_backup_units", failures)
        self.assertIn("homelab_daily_backup_units", daily)
        self.assertNotIn("[HomelabAlert - homebox backup failed]", self.saved)
        self.assertNotIn("[HomelabAlert - homebox backup silent]", self.saved)


if __name__ == "__main__":
    unittest.main()
