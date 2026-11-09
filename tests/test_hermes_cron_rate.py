import re
import unittest
from pathlib import Path

from test_homebox_backup_alerts import stanza


ROOT = Path(__file__).resolve().parents[1]
REPORT = "hermes_cron_delivered_run_rate"


class HermesCronDeliveredRunRateTest(unittest.TestCase):
    def setUp(self):
        self.saved = (ROOT / "default/savedsearches.conf").read_text()
        self.macros = (ROOT / "default/macros.conf").read_text()

    def test_report_is_enabled_hourly_at_an_odd_minute(self):
        report = stanza(self.saved, REPORT)

        self.assertRegex(report, r"(?m)^disabled = 0$")
        self.assertRegex(report, r"(?m)^cron_schedule = \d+ \* \* \* \*$")
        minute = int(re.search(r"(?m)^cron_schedule = (\d+) \* ", report).group(1))
        self.assertNotEqual(minute % 15, 0)
        self.assertEqual(minute % 2, 1)
        # Scheduling itself is inherited from the app's [default] stanza.
        self.assertIn("enableSched = 1", stanza(self.saved, "default"))

    def test_report_does_not_open_a_ticket(self):
        report = stanza(self.saved, REPORT)

        self.assertRegex(report, r"(?m)^action\.zammad = 0$")
        self.assertRegex(report, r"(?m)^dispatch\.earliest_time = -24h$")

    def test_macros_carry_the_index_filter_and_line_extractions(self):
        events = stanza(self.macros, "homelab_hermes_cron_events")
        fields = stanza(self.macros, "homelab_hermes_cron_fields")

        self.assertIn("index=hermes", events)
        # Run lines quote the job name with no colon after the closing quote.
        self.assertIn(
            r"Running job '(?<cron_start_name>[^']+)' \(ID: (?<cron_start_id>[^\)]+)\)",
            fields,
        )
        self.assertIn(r"Job '(?<cron_success_name>[^']+)' completed successfully", fields)
        self.assertIn(r"Job '(?<cron_fail_name>[^']+)' failed:", fields)
        self.assertIn(r"Job '(?<cron_suppressed_name>[^']+)':.*delivery suppressed", fields)
        # Delivery lines quote the job id followed by a colon.
        self.assertIn(r"Job '(?<cron_delivered_id>[^']+)': delivered to ", fields)
        self.assertIn(r"Job '(?<cron_delivery_failed_id>[^']+)': delivery to .* failed:", fields)

    def test_report_joins_start_to_delivery_by_job_id(self):
        report = stanza(self.saved, REPORT)

        self.assertIn("`homelab_hermes_cron_events`", report)
        self.assertIn("`homelab_hermes_cron_fields`", report)
        self.assertIn("eventstats max(cron_start_name) AS cron_job_name BY cron_run_id", report)
        self.assertIn("coalesce(cron_line_name, cron_job_name)", report)

    def test_delivered_counts_one_per_job_id_per_hour_bucket(self):
        report = stanza(self.saved, REPORT)

        self.assertIn("bin _time AS cron_hour span=1h", report)
        self.assertIn('cron_run_id."@".cron_hour', report)
        self.assertIn("dc(cron_delivery) AS delivered", report)

    def test_report_counts_runs_deliveries_and_a_total_row(self):
        report = stanza(self.saved, REPORT)

        for aggregation in (
            'count(eval(cron_event="started")) AS started',
            'count(eval(cron_event="completed")) AS completed',
            'count(eval(cron_event="failed")) AS failed',
            'count(eval(cron_event="delivery_failed")) AS delivery_failed',
            'count(eval(cron_event="suppressed")) AS suppressed',
        ):
            self.assertIn(aggregation, report)
        self.assertIn('eval job="TOTAL"', report)
        self.assertEqual(report.count("round(delivered/started, 2)"), 2)
        self.assertIn("| table job, started, completed, failed, delivered, delivery_failed, suppressed, delivered_rate", report)


if __name__ == "__main__":
    unittest.main()
