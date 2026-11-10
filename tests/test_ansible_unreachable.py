import re
import unittest
from pathlib import Path

from test_homebox_backup_alerts import stanza


ROOT = Path(__file__).resolve().parents[1]
ALERT = "HomelabAlert - host unreachable in scheduled Ansible converges"


class AnsibleUnreachableAlertTest(unittest.TestCase):
    def setUp(self):
        self.saved = (ROOT / "default/savedsearches.conf").read_text()
        self.alert = stanza(self.saved, ALERT)

    def test_search_counts_converge_runs_per_host_over_26_hours(self):
        self.assertIn(
            'index=ansible sourcetype="ansible:converge:unreachable"', self.alert
        )
        self.assertIn("stats dc(converge_id) AS converge_runs BY host", self.alert)
        self.assertIn("| where converge_runs >= 2", self.alert)
        self.assertRegex(self.alert, r"(?m)^dispatch\.earliest_time = -26h$")
        self.assertRegex(self.alert, r"(?m)^dispatch\.latest_time = now$")

    def test_throttles_per_host_for_24_hours(self):
        self.assertRegex(self.alert, r"(?m)^alert\.suppress = 1$")
        self.assertRegex(self.alert, r"(?m)^alert\.suppress\.period = 24h$")
        self.assertRegex(self.alert, r"(?m)^alert\.suppress\.fields = host$")

    def test_routes_through_the_zammad_action_one_ticket_per_host(self):
        default = stanza(self.saved, "default")
        # Scheduling and delivery come from the app's [default] stanza.
        self.assertIn("action.zammad = 1", default)
        self.assertIn("enableSched = 1", default)
        self.assertRegex(
            self.alert,
            r"(?m)^action\.zammad\.param\.correlation_key = \$name\$ - \$result\.host\$$",
        )

    def test_message_names_the_host_and_count_and_advises_ssh_checks(self):
        message = re.search(
            r"(?m)^action\.zammad\.param\.message = (.+)$", self.alert
        ).group(1)
        self.assertIn("$result.host$", message)
        self.assertIn("$result.converge_runs$", message)
        self.assertIn("SSH host keys", message)
        self.assertIn("reachability", message)
        # The dashboard link itself is enforced on every alerting stanza by
        # test_dashboard_links.
        self.assertIn("/app/splunk-homelab-alerts/homelab_ansible?", message)

    def test_arrives_disabled_like_every_new_detector(self):
        # No explicit disabled override: the stanza inherits disabled = 1 from
        # the app's [default] stanza until its own enabling change.
        self.assertNotRegex(self.alert, r"(?m)^disabled =")


if __name__ == "__main__":
    unittest.main()
