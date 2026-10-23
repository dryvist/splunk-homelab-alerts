import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def stanza(text, name):
    start = text.index(f"[{name}]\n")
    end = text.find("\n[", start + 1)
    return text[start:] if end == -1 else text[start:end]


class UnifiNetworkCefSilenceAlertTest(unittest.TestCase):
    def test_product_silence_alert_uses_shared_cadence_and_safe_empty_result(self):
        saved = (ROOT / "default/savedsearches.conf").read_text()
        body = stanza(saved, "unifi_network_cef_silence_detector")

        self.assertIn(
            'search = index=unifi sourcetype="ubiquiti:unifi" '
            '"Ubiquiti|UniFi Network|" | stats count | where count=0',
            body,
        )
        self.assertIn("\ndispatch.earliest_time = -2h\n", body)
        self.assertIn("\ncron_schedule = */5 * * * *\n", body)
        self.assertIn("\ndisabled = 0\n", body)
        self.assertIn("\nalert.suppress = 1\nalert.suppress.period = 60m\n", body)
        self.assertIn(
            "\ncounttype = number of events\nrelation = greater than\nquantity = 0\n",
            body,
        )

        defaults = stanza(saved, "default")
        self.assertIn("\naction.zammad = 1\n", defaults)
        self.assertIn("\naction.zammad.param.correlation_key = $name$\n", defaults)


if __name__ == "__main__":
    unittest.main()
