"""The MLX cluster guard alert, its message dashboard link, and the view.

The stanza inherits the Zammad routing from the app's [default] stanza, fires
when the 20-minute window holds at least one guard hold or refusal, throttles
per host and reason, and its message names the signal, links the packaged
dashboard over the alert window with the host preselected, and carries the
operational instruction. Like every new detector it arrives disabled.
"""

import re
import unittest
import xml.etree.ElementTree as ElementTree
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from test_homebox_backup_alerts import stanza


ROOT = Path(__file__).resolve().parents[1]
ALERT = "HomelabAlert - MLX cluster guard hold or refusal"
VIEW = "homelab_mlx_cluster"
BASE_FILTER = (
    'index=llm sourcetype="mlx:cluster" '
    '("cluster-schedule: guard=" "decision=hold") OR "REFUSE reason="'
)


class MlxClusterGuardAlertTest(unittest.TestCase):
    def setUp(self):
        self.saved = (ROOT / "default/savedsearches.conf").read_text()
        self.macros = (ROOT / "default/macros.conf").read_text()
        self.alert = stanza(self.saved, ALERT)
        self.view_path = ROOT / "default/data/ui/views" / ("%s.xml" % VIEW)

    def message_link(self):
        message = re.search(
            r"(?m)^action\.zammad\.param\.message = (.+)$", self.alert
        ).group(1)
        return re.search(r"/app/splunk-homelab-alerts/(\S+)", message).group(1)

    def test_search_counts_guard_holds_and_refusals_by_host_and_guard(self):
        self.assertIn("search = %s" % BASE_FILTER, self.alert)
        self.assertIn("`homelab_mlx_cluster_fields`", self.alert)
        self.assertIn(
            "stats count, latest(decision) AS decision, latest(reason) AS reason, "
            "latest(_time) AS latest_time BY host, guard",
            self.alert,
        )
        self.assertIn("| table host, guard, decision, reason, count, latest_time", self.alert)
        self.assertRegex(self.alert, r"(?m)^dispatch\.earliest_time = -20m@m$")
        self.assertRegex(self.alert, r"(?m)^dispatch\.latest_time = now$")

    def test_fires_on_the_first_result_and_runs_every_15_minutes_offset(self):
        self.assertRegex(self.alert, r"(?m)^cron_schedule = 4-59/15 \* \* \* \*$")
        self.assertRegex(self.alert, r"(?m)^counttype = number of events$")
        self.assertRegex(self.alert, r"(?m)^relation = greater than$")
        self.assertRegex(self.alert, r"(?m)^quantity = 0$")
        # Scheduling itself is inherited from the app's [default] stanza.
        self.assertIn("enableSched = 1", stanza(self.saved, "default"))

    def test_guard_decision_and_reason_extractions_live_in_one_macro(self):
        fields = stanza(self.macros, "homelab_mlx_cluster_fields")
        self.assertIn(r'rex field=_raw "guard=(?<guard>\S+)"', fields)
        self.assertIn(r'rex field=_raw "decision=(?<decision>\S+)"', fields)
        self.assertIn(r'rex field=_raw "reason=(?<reason>\S+)"', fields)
        # Refusal lines carry no decision= or guard= token; the macro fills
        # both in so a refusal still groups and renders as a decision.
        self.assertIn('coalesce(decision, "refuse")', fields)
        self.assertIn('coalesce(guard, "unknown")', fields)
        self.assertIn('coalesce(reason, "unspecified")', fields)

    def test_throttles_per_host_and_reason_for_six_hours(self):
        self.assertRegex(self.alert, r"(?m)^alert\.suppress = 1$")
        self.assertRegex(self.alert, r"(?m)^alert\.suppress\.period = 6h$")
        self.assertRegex(self.alert, r"(?m)^alert\.suppress\.fields = host,reason$")
        self.assertRegex(
            self.alert,
            r"(?m)^action\.zammad\.param\.correlation_key = "
            r"\$name\$ - \$result\.host\$ - \$result\.reason\$$",
        )

    def test_routes_through_the_apps_zammad_delivery_default(self):
        default = stanza(self.saved, "default")
        self.assertIn("action.zammad = 1", default)
        self.assertIn("action.zammad.param.group = Homelab Infrastructure", default)
        self.assertNotRegex(self.alert, r"(?m)^action\.zammad = ")

    def test_message_names_the_signal_and_advises_against_manual_joins(self):
        message = re.search(
            r"(?m)^action\.zammad\.param\.message = (.+)$", self.alert
        ).group(1)
        for token in (
            "$result.host$",
            "$result.guard$",
            "$result.decision$",
            "$result.reason$",
            "$result.count$",
        ):
            self.assertIn(token, message)
        self.assertIn("no one should join the cluster by hand", message)

    def test_message_links_the_packaged_dashboard_over_the_alert_window(self):
        link = self.message_link()
        view = link.split("?")[0]
        self.assertTrue(
            self.view_path.exists(), "%s is not a view in this app" % view
        )
        query = parse_qs(urlsplit(link).query)
        self.assertEqual(query.get("form.time.earliest"), ["-20m@m"])
        self.assertEqual(query.get("form.time.latest"), ["now"])
        # The throttled host is the entity the link preselects.
        self.assertEqual(query.get("form.host"), ["$result.host$"])

    def test_view_is_a_form_with_time_and_host_inputs_and_bounded_panels(self):
        root = ElementTree.parse(self.view_path).getroot()
        self.assertEqual(root.tag, "form", self.view_path.name)
        self.assertIsNotNone(root.find("label"), self.view_path.name)
        tokens = {
            element.get("token")
            for element in root.iter("input")
            if element.get("token")
        }
        self.assertEqual(tokens, {"time", "host"})
        searches = list(root.iter("search"))
        self.assertEqual(len(searches), 2, self.view_path.name)
        for search in searches:
            self.assertIn(BASE_FILTER, search.find("query").text)
            self.assertIn("`homelab_mlx_cluster_fields`", search.find("query").text)
            self.assertIn('host="$host$"', search.find("query").text)
            self.assertEqual(search.find("earliest").text, "$time.earliest$")
            self.assertEqual(search.find("latest").text, "$time.latest$")
        tags = {element.tag for element in root.iter() if element.tag in ("chart", "table")}
        self.assertEqual(tags, {"chart", "table"}, self.view_path.name)

    def test_arrives_disabled_like_every_new_detector(self):
        self.assertRegex(self.alert, r"(?m)^disabled = 1$")


if __name__ == "__main__":
    unittest.main()
