import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def stanza(text, name):
    start = text.index(f"[{name}]\n")
    end = text.find("\n[", start + 1)
    return text[start:] if end == -1 else text[start:end]


class BackupUnitAlertsTest(unittest.TestCase):
    def setUp(self):
        self.saved = (ROOT / "default/savedsearches.conf").read_text()
        self.macros = (ROOT / "default/macros.conf").read_text()

    def test_unit_lists_are_shared_macros(self):
        daily = stanza(self.macros, "homelab_daily_backup_units")
        every = stanza(self.macros, "homelab_backup_units")

        self.assertIn('"pg-backup.service"', daily)
        self.assertIn('"nautobot-backup@b2.service"', daily)
        self.assertIn("`homelab_daily_backup_units`", every)
        self.assertIn('"pgbackrest-backup@"', every)
        self.assertIn('"nautobot-check@"', every)
        self.assertNotIn("nautobot-check@", daily)

    def test_failure_alert_covers_every_backup_unit_per_host_and_is_enabled(self):
        body = stanza(self.saved, "HomelabAlert - backup unit failed")

        self.assertIn(
            'search = `homelab_os_log_indexes` `homelab_backup_units` "Failed with result"',
            body,
        )
        self.assertIn("BY host, unit", body)
        self.assertIn("\ndisabled = 0\n", body)
        self.assertIn("alert.suppress.fields = host,unit", body)
        self.assertIn(
            "action.zammad.param.correlation_key = $name$ - $result.host$ - $result.unit$",
            body,
        )

    def test_silence_alert_checks_36_hours_on_the_nightly_macro_and_is_enabled(self):
        body = stanza(self.saved, "HomelabAlert - nightly backup silent")

        self.assertIn("`homelab_os_log_indexes` `homelab_daily_backup_units`", body)
        self.assertIn('"Deactivated successfully"', body)
        self.assertIn("minutes_silent > 36*60", body)
        self.assertIn("appendpipe", body)
        self.assertIn("BY host, unit", body)
        self.assertIn("\ndisabled = 0\n", body)


if __name__ == "__main__":
    unittest.main()
