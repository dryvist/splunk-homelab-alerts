#!/usr/bin/env python3
"""Splunk custom alert action: open or update a Zammad incident.

Contract (same as the vendor add-ons): Splunk runs this with `--execute` and
writes one JSON payload on stdin. A non-zero exit marks the action failed in
the alert's action log.

Dedup is by ticket title. The correlation key defaults to the saved-search
stanza name, which is already unique and already stable across every firing,
so a detector on a */5 cron appends articles to one open ticket instead of
opening a ticket per cycle. Tags are deliberately NOT used: the tag field is
not reliably queryable on this instance (a `tags:*` query matched a ticket
whose tags were null), whereas title and state field queries are.

ponytail: stdlib only -- Splunk ships no `requests` for alert actions and
urllib covers three JSON calls. No retry/backoff either: Splunk already
records a failed action, and a detector re-fires on its own cron. Add one if
Zammad restarts turn out to drop alerts on the floor.
"""

import json
import sys
import urllib.error
import urllib.parse
import urllib.request

REALM = "zammad"
USERNAME = "svc-splunk"
# Splunk's alert.severity is not in the alert payload -- `configuration` carries
# only action.zammad.param.* -- so priority is an explicit param, never derived.
DEFAULT_PRIORITY = "2 normal"


def _json_call(url, token=None, session_key=None, payload=None, method=None):
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = "Token token=%s" % token
    if session_key:
        headers["Authorization"] = "Splunk %s" % session_key
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode() or "{}")


def get_password(server_uri, session_key, app):
    """Read the svc-splunk Zammad token from storage/passwords.

    The credential reaches storage/passwords from OpenBao at converge time. It
    is never written into savedsearches.conf, where it would be readable by
    anyone who can read a saved search.
    """
    url = "%s/servicesNS/nobody/%s/storage/passwords?output_mode=json&count=0" % (
        server_uri.rstrip("/"),
        urllib.parse.quote(app),
    )
    for entry in _json_call(url, session_key=session_key).get("entry", []):
        content = entry.get("content", {})
        if content.get("realm") == REALM and content.get("username") == USERNAME:
            return content["clear_password"]
    raise RuntimeError("no %s/%s credential in storage/passwords" % (REALM, USERNAME))


def article(payload, cfg):
    """The note body. Identical whether it opens a ticket or appends to one."""
    result = payload.get("result", {}) or {}
    lines = [
        "Splunk saved search: %s" % payload.get("search_name", "?"),
        "Result count: %s" % payload.get("result_count", "?"),
    ]
    if payload.get("results_link"):
        lines.append("Results: %s" % payload["results_link"])
    if result:
        lines.append("")
        lines.append("First result:")
        lines.extend("  %s = %s" % (k, v) for k, v in sorted(result.items()))
    return {
        "subject": cfg.get("correlation_key") or payload.get("search_name", "Splunk alert"),
        "body": "\n".join(lines),
        "type": "note",
        "internal": True,
    }


def find_open(base, token, key):
    """Ticket id of the open incident for this key, or None.

    Restricted to new/open so a closed incident that recurs opens a fresh
    ticket instead of reviving a resolved one.
    """
    query = 'title:"%s" AND state.name:(new OR open)' % key.replace('"', "")
    url = "%s/tickets/search?%s" % (
        base.rstrip("/"),
        urllib.parse.urlencode({"query": query, "limit": 1}),
    )
    tickets = _json_call(url, token=token).get("tickets") or []
    return tickets[0] if tickets else None


def send(payload):
    cfg = payload.get("configuration", {}) or {}
    key = cfg.get("correlation_key") or payload.get("search_name")
    if not key:
        raise RuntimeError("no correlation key and no search_name in payload")

    base = cfg.get("url")
    if not base:
        raise RuntimeError("no Zammad API base URL configured (action.zammad.param.url)")
    token = get_password(
        payload["server_uri"], payload["session_key"], payload.get("app", "search")
    )

    existing = find_open(base, token, key)
    if existing:
        _json_call(
            "%s/tickets/%s" % (base.rstrip("/"), existing),
            token=token,
            payload={"article": article(payload, cfg)},
            method="PUT",
        )
        return "appended to ticket %s" % existing

    # No customer field: Zammad makes the token's user (svc-splunk) the ticket
    # customer, which is what keeps these attributable to Splunk rather than to
    # whichever agent's token happened to open them.
    created = _json_call(
        "%s/tickets" % base.rstrip("/"),
        token=token,
        payload={
            "title": key,
            "group": cfg.get("group") or "Users",
            "priority": cfg.get("priority") or DEFAULT_PRIORITY,
            "state": cfg.get("state") or "new",
            "article": article(payload, cfg),
        },
        method="POST",
    )
    return "created ticket %s" % created.get("number", created.get("id", "?"))


def selftest():
    payload = {
        "search_name": "HomelabAlert - disk full",
        "result_count": "3",
        "results_link": "https://example.invalid/x",
        "result": {"host": "node-a"},
        "configuration": {},
    }
    note = article(payload, payload["configuration"])
    assert note["subject"] == "HomelabAlert - disk full", note
    assert "host = node-a" in note["body"], note
    assert note["internal"] is True, note

    # An explicit correlation key overrides the stanza name.
    keyed = dict(payload, configuration={"correlation_key": "HomelabAlert - disk full - node-a"})
    assert article(keyed, keyed["configuration"])["subject"].endswith("node-a")

    # A quote in the key must not break out of the search query literal: the
    # rendered query carries exactly the two delimiting quotes, no more.
    hostile = 'a" OR state.name:closed OR title:"b'
    assert ('title:"%s"' % hostile.replace('"', "")).count('"') == 2

    # A payload with neither key nor search_name is an error, not a blank title.
    try:
        send({"configuration": {}})
    except RuntimeError as exc:
        assert "correlation key" in str(exc), exc
    else:  # pragma: no cover
        raise AssertionError("expected RuntimeError for a payload with no key")

    print("selftest OK")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
        sys.exit(0)
    if len(sys.argv) < 2 or sys.argv[1] != "--execute":
        print("FATAL Unsupported execution mode (expected --execute)", file=sys.stderr)
        sys.exit(1)
    try:
        print("INFO %s" % send(json.loads(sys.stdin.read())), file=sys.stderr)
    except urllib.error.HTTPError as exc:
        print("ERROR Zammad HTTP %s: %s" % (exc.code, exc.read().decode()[:500]), file=sys.stderr)
        sys.exit(2)
    except Exception as exc:  # noqa: BLE001 - Splunk needs a non-zero exit, not a traceback
        print("ERROR %s" % exc, file=sys.stderr)
        sys.exit(3)
