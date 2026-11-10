"""Every alerting search's message must link a dashboard that shows its signal.

Stanzas inherit `action.zammad = 1` from the app's [default] stanza, so every
stanza with a search is alerting unless it explicitly turns the action off
(`hermes_cron_delivered_run_rate` and `llm_token_usage_by_tier` are reports).
The message link must point at a view packaged in this app, carry form time
tokens equal to the stanza's dispatch window (so the dashboard covers the
alert window), select the alerting entity with a non-time form token, and
throttle its first suppressed field through $result.<field>$.
"""

import re
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from test_dashboard_views import view_input_tokens
from test_homebox_backup_alerts import stanza


ROOT = Path(__file__).resolve().parents[1]
APP_ID = "splunk-homelab-alerts"
VIEWS = ROOT / "default/data/ui/views"


def alerting_stanzas(saved):
    for name in re.findall(r"(?m)^\[([^\]]+)\]", saved):
        body = stanza(saved, name)
        if name == "default" or not re.search(r"(?m)^search =", body):
            continue
        if re.search(r"(?m)^action\.zammad = 0$", body):
            continue
        yield name, body


def message_link(body):
    message = re.search(r"(?m)^action\.zammad\.param\.message = (.+)$", body)
    if not message:
        return None
    link = re.search(r"/app/%s/(\S+)" % APP_ID, message.group(1))
    return link.group(1) if link else None


def dispatch_value(body, key):
    return re.search(r"(?m)^%s = (.+)$" % key, body).group(1).strip()


class AlertDashboardLinkTest(unittest.TestCase):
    def setUp(self):
        self.saved = (ROOT / "default/savedsearches.conf").read_text()
        self.alerts = dict(alerting_stanzas(self.saved))

    def test_every_alerting_search_links_a_packaged_dashboard(self):
        self.assertTrue(self.alerts)
        for name, body in self.alerts.items():
            link = message_link(body)
            self.assertIsNotNone(
                link, "%s carries no dashboard link in its message" % name
            )
            view = link.split("?")[0]
            self.assertTrue(
                (VIEWS / ("%s.xml" % view)).exists(),
                "%s links %s, which is not a view in this app" % (name, view),
            )

    def test_link_time_tokens_match_the_dispatch_window(self):
        for name, body in self.alerts.items():
            query = parse_qs(urlsplit(message_link(body)).query)
            self.assertEqual(
                query.get("form.time.earliest"),
                [dispatch_value(body, "dispatch.earliest_time")],
                name,
            )
            self.assertEqual(
                query.get("form.time.latest"),
                [dispatch_value(body, "dispatch.latest_time")],
                name,
            )

    def test_link_filters_select_the_alerting_entity(self):
        for name, body in self.alerts.items():
            query = parse_qs(urlsplit(message_link(body)).query)
            entity = {k: v[0] for k, v in query.items() if not k.startswith("form.time")}
            self.assertTrue(entity, "%s links no entity filter" % name)
            view = message_link(body).split("?")[0]
            tokens = view_input_tokens(VIEWS / ("%s.xml" % view))
            for key, value in entity.items():
                token = key[len("form."):]
                self.assertIn(token, tokens, "%s: no %s input on %s" % (name, token, view))
                field = re.fullmatch(r"\$result\.(\w+)\$", value)
                if field:
                    self.assertRegex(
                        body, r"\b%s\b" % re.escape(field.group(1)),
                        "%s: %s is not a field of the search" % (name, field.group(1)),
                    )

    def test_throttled_entity_is_selected_in_the_link(self):
        for name, body in self.alerts.items():
            fields = re.search(r"(?m)^alert\.suppress\.fields = (\S+)$", body)
            if not fields:
                continue
            first = fields.group(1).split(",")[0]
            self.assertIn(
                "$result.%s$" % first, message_link(body),
                "%s throttles %s but its link does not select it" % (name, first),
            )


if __name__ == "__main__":
    unittest.main()
