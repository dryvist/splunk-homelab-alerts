import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class OsLogIndexesTest(unittest.TestCase):
    def test_macro_covers_every_event_index_used_for_os_logs(self):
        macros = (ROOT / "default/macros.conf").read_text()
        match = re.search(
            r"^\[homelab_os_log_indexes\]\n"
            r"definition = (.+)\n"
            r"iseval = false$",
            macros,
            re.MULTILINE,
        )

        self.assertIsNotNone(match)
        self.assertEqual(
            match.group(1),
            "(index=os OR index=os_proxmox OR index=os_ai)",
        )

    def test_macro_is_exported_for_the_cross_app_alert(self):
        metadata = (ROOT / "metadata/default.meta").read_text()
        self.assertRegex(
            metadata,
            r"(?m)^\[macros/homelab_os_log_indexes\]\nexport = system$",
        )


if __name__ == "__main__":
    unittest.main()
