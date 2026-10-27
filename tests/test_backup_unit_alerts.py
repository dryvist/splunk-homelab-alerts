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

    def test_daily_and_weekly_unit_families_are_shared(self):
        daily = stanza(self.macros, "homelab_daily_backup_units")
        weekly = stanza(self.macros, "homelab_weekly_backup_units")
        every = stanza(self.macros, "homelab_backup_units")

        for unit in (
            "restic-backup@",
            "nautobot-backup@",
            "homebox-backup@",
            "pg-backup.service",
            "pgbackrest-backup@incr.service",
            "postgres-standby.service",
            "pve-config-backup.service",
            "hindsight-bank-export.service",
            "llamaindex-index.service",
            "llamaindex-agent-sessions.service",
            "object-storage-offsite@",
            "openbao-secret-age.service",
        ):
            with self.subTest(unit=unit):
                self.assertIn(f'"{unit}"', daily)

        for unit in (
            "restic-check@",
            "nautobot-check@",
            "homebox-check@",
            "pgbackrest-backup@full.service",
            "hindsight-bank-dr-drill.service",
        ):
            with self.subTest(unit=unit):
                self.assertIn(f'"{unit}"', weekly)
                self.assertNotIn(f'"{unit}"', daily)

        self.assertIn("homelab_daily_backup_units", every)
        self.assertIn("homelab_weekly_backup_units", every)

    def test_failure_alert_covers_shared_units_per_host_and_is_enabled(self):
        body = stanza(self.saved, "HomelabAlert - backup unit failed")

        self.assertIn("homelab_backup_units", body)
        self.assertIn('"Failed with result"', body)
        self.assertIn("BY host, unit", body)
        self.assertIn("cron_schedule = */15 * * * *", body)
        self.assertIn("\ndisabled = 0\n", body)
        self.assertIn("alert.suppress.fields = host,unit", body)
        self.assertIn(
            "action.zammad.param.correlation_key = $name$ - $result.host$ - $result.unit$",
            body,
        )

    def test_daily_silence_alert_uses_26_hours_after_the_window(self):
        body = stanza(self.saved, "HomelabAlert - nightly backup silent")

        self.assertIn("homelab_daily_backup_units", body)
        self.assertIn('"Deactivated successfully"', body)
        self.assertIn("minutes_silent > 26*60", body)
        self.assertIn("cron_schedule = 15 10 * * *", body)
        self.assertIn("allow_skew = 0", body)
        self.assertIn("appendpipe", body)
        self.assertIn("BY host, unit", body)
        self.assertIn("\ndisabled = 0\n", body)
        self.assertNotIn("36*60", body)

if __name__ == "__main__":
    unittest.main()
