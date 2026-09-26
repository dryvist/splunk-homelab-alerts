#!/usr/bin/env python3
"""
Test the Hindsight bank-DR alert contract in default/savedsearches.conf.

No framework, no network -- same spirit as bin/zammad.py --selftest. This
file is the literal, final config Splunk loads (no Jinja/Ansible render
step in this repo), so reading it is equivalent to what ships.

What this guards: each stanza's `search` line carries the exact index,
sourcetype, event name, result value, and (for the two absence detectors)
the threshold that makes it detect what its description claims. Drop any of
these and the alert still exists, still runs on schedule, and still returns
zero results forever -- indistinguishable from "everything is healthy".

Run from repo root:
    python3 tests/test_hindsight_bank_dr_alerts.py
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
CONF = ROOT / "default" / "savedsearches.conf"

# stanza -> phrase -> what its absence would stop detecting
REQUIRED_PHRASES = {
    "hindsight_bank_export_failed": {
        "index=hindsight": "scoping to the wrong (or no) index",
        "sourcetype=hindsight:app": "matching unrelated events sharing the index",
        'event="hindsight_bank_export"': "matching the drill's events too",
        'result="fail"': "the actual failure condition",
    },
    "hindsight_dr_drill_failed": {
        "index=hindsight": "scoping to the wrong (or no) index",
        "sourcetype=hindsight:app": "matching unrelated events sharing the index",
        'event="hindsight_dr_drill"': "matching the export's events too",
        'result="fail"': "the actual failure condition",
    },
    "hindsight_bank_export_no_pass": {
        "index=hindsight": "scoping to the wrong (or no) index",
        'event="hindsight_bank_export"': "matching the drill's pass events too",
        'result="pass"': "the absence-of-success condition",
        "hours_since_pass > 26": "the 26h dead-man's-switch window",
        "_rows == 0": "the zero-row (fully silent) blind spot guard",
    },
    "hindsight_dr_drill_no_pass": {
        "index=hindsight": "scoping to the wrong (or no) index",
        'event="hindsight_dr_drill"': "matching the export's pass events too",
        'result="pass"': "the absence-of-success condition",
        "days_since_pass > 8": "the 8-day dead-man's-switch window",
        "_rows == 0": "the zero-row (fully silent) blind spot guard",
    },
}

errors = []
body = CONF.read_text()

for stanza_name, phrases in REQUIRED_PHRASES.items():
    stanza = re.search(rf"^\[{re.escape(stanza_name)}\]$(.*?)(?=^\[|\Z)", body, re.M | re.S)
    if not stanza:
        errors.append(f"FAIL: [{stanza_name}] stanza not found")
        continue

    search_line = next(
        (ln for ln in stanza.group(1).splitlines() if ln.startswith("search = ")), ""
    )
    if not search_line:
        errors.append(f"FAIL: [{stanza_name}] has no search line")
        continue

    for phrase, why in phrases.items():
        if phrase not in search_line:
            errors.append(f"FAIL: [{stanza_name}] search lost {phrase!r} — stops detecting {why}")

    if "_index_earliest" not in search_line or "_index_latest" not in search_line:
        errors.append(f"FAIL: [{stanza_name}] does not bound on index time (_index_earliest/_index_latest)")

    keys = dict(re.findall(r"^(\w[\w.]*)\s*=\s*(.*)$", stanza.group(1), re.M))
    if keys.get("disabled") != "1":
        errors.append(
            f"FAIL: [{stanza_name}] is not disabled=1 -- every detector in this app is staged, "
            "not live, until explicitly promoted (see README)"
        )

if errors:
    for err in errors:
        print(err)
    sys.exit(1)

print("PASS: all four Hindsight bank-DR alert stanzas cover their fail/absence conditions, "
      "index-time bounds, and staged (disabled=1) state")
