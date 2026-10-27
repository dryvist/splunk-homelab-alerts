import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKUP_DETECTORS = (
    "HomelabAlert - backup vzdump task failed",
    "HomelabAlert - backup vzdump task missed",
    "HomelabAlert - backup vzdump task stuck",
    "HomelabAlert - backup PBS status failed",
    "HomelabAlert - backup PBS task failed",
)


def stanza(text, name):
    start = text.index(f"[{name}]\n")
    end = text.find("\n[", start + 1)
    return text[start:] if end == -1 else text[start:end]


def python_regex(spl_rex):
    return spl_rex.replace("?<", "?P<").replace("\\\\", "\\")


def must_search(pattern, text) -> re.Match[str]:
    found = re.search(pattern, text)
    assert found, f"{pattern!r} did not match {text!r}"
    return found


class MaintenanceWindowAlertsTest(unittest.TestCase):
    def setUp(self):
        self.saved = (ROOT / "default/savedsearches.conf").read_text()
        self.macros = (ROOT / "default/macros.conf").read_text()

    def test_backup_detectors_are_enabled_and_match_the_hermes_name_filter(self):
        # Hermes reads fired alerts with savedsearch_name="HomelabAlert - *backup*".
        for name in BACKUP_DETECTORS:
            with self.subTest(alert=name):
                self.assertIn("backup", name)
                self.assertIn("\ndisabled = 0\n", stanza(self.saved, name))

    def test_upid_extraction_parses_a_vzdump_task_file_name(self):
        rexes = re.findall(r'rex field=\w+ "([^"]+)"', stanza(self.macros, "homelab_pve_task_fields"))
        raw = "pve-task: /var/log/pve/tasks/3/UPID:pve-a:0001:0002:6720AB00:vzdump::root@pam: TASK OK"
        upid = must_search(python_regex(rexes[0]), raw).group("upid")
        fields = must_search(python_regex(rexes[1]), upid).groupdict()
        self.assertEqual((fields["node"], fields["task_type"]), ("pve-a", "vzdump"))

    def test_pbs_status_extraction_parses_a_status_line(self):
        rex = must_search(r'rex field=_raw "([^"]+)"', stanza(self.macros, "homelab_pbs_status_fields")).group(1)
        raw = "pbs-status: 2026-10-27T06:00:00Z pbs.example pbs verify-pve-backups-verify P2 fail -1"
        fields = must_search(python_regex(rex), raw).groupdict()
        self.assertEqual(
            fields,
            {"job": "verify-pve-backups-verify", "class": "P2", "outcome": "fail", "age_seconds": "-1"},
        )

    def test_expected_node_macro_is_empty_safe(self):
        self.assertIn('definition = ""', stanza(self.macros, "homelab_vzdump_expected_nodes"))
        self.assertIn(
            "where len(`homelab_vzdump_expected_nodes`) > 0",
            stanza(self.saved, "HomelabAlert - backup vzdump task missed"),
        )


if __name__ == "__main__":
    unittest.main()
