import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def stanza(text, name):
    start = text.index(f"[{name}]\n")
    end = text.find("\n[", start + 1)
    return text[start:] if end == -1 else text[start:end]


class CapacityAndRouterAlertsTest(unittest.TestCase):
    def setUp(self):
        self.saved = (ROOT / "default/savedsearches.conf").read_text()
        self.macros = (ROOT / "default/macros.conf").read_text()

    def test_object_store_fill_uses_its_shared_threshold_macro(self):
        body = stanza(self.saved, "HomelabAlert - object store volume fill")

        self.assertIn("latest(node_filesystem_avail_bytes) as available", body)
        self.assertIn("latest(node_filesystem_size_bytes) as total", body)
        self.assertIn('mountpoint="/srv/object-storage"', body)
        self.assertIn("where used_pct >= `homelab_object_store_fill_threshold_pct`", body)
        self.assertIn("alert.suppress.fields = host,mountpoint", body)

    def test_router_digest_uses_shared_error_and_database_connection_macros(self):
        body = stanza(self.saved, "HomelabAlert - router database unreachable")

        self.assertIn("search = index=llm sourcetype=litellm:proxy", body)
        self.assertIn("`homelab_database_connection_terms`", body)
        self.assertIn("`homelab_error_terms`", body)
        self.assertIn(
            "where failure_count >= `homelab_router_database_failure_threshold`",
            body,
        )
        self.assertEqual(self.macros.count("[homelab_error_terms]"), 1)
        self.assertIn("alert.suppress = 1\nalert.suppress.period = 30m", body)
        self.assertIn(
            "stats count AS failure_count dc(host) AS affected_router_count by _time",
            body,
        )
        self.assertNotIn("lower(_raw)", body)
        self.assertNotIn("match(", body)

    def test_arc_pressure_uses_its_shared_threshold_macro(self):
        body = stanza(self.saved, "HomelabAlert - ZFS ARC pressure")

        self.assertIn("latest(node_zfs_arc_memory_available_bytes) as available", body)
        self.assertIn("latest(node_zfs_arc_memory_all_bytes) as total", body)
        self.assertIn("where available_pct < `homelab_zfs_arc_available_pct_threshold`", body)
        self.assertIn("alert.suppress.fields = host", body)

    def test_thresholds_and_database_terms_have_one_macro_definition_each(self):
        for name, expected in (
            ("homelab_database_connection_terms", "database OR postgresql"),
            ("homelab_router_database_failure_threshold", "1"),
            ("homelab_object_store_fill_threshold_pct", "85"),
            ("homelab_zfs_arc_available_pct_threshold", "10"),
        ):
            matches = re.findall(
                rf"(?m)^\[{re.escape(name)}\]\ndefinition = (.+)$",
                self.macros,
            )
            self.assertEqual(len(matches), 1)
            self.assertIn(expected, matches[0])

        self.assertIn("reach", stanza(self.macros, "homelab_database_connection_terms"))

    def test_new_detectors_inherit_the_apps_disabled_default(self):
        defaults = stanza(self.saved, "default")
        self.assertIn("\ndisabled = 1\n", defaults)
        for name in (
            "HomelabAlert - object store volume fill",
            "HomelabAlert - router database unreachable",
            "HomelabAlert - ZFS ARC pressure",
        ):
            self.assertNotIn("\ndisabled = 0\n", stanza(self.saved, name))


if __name__ == "__main__":
    unittest.main()
