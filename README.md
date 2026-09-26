# splunk-homelab-alerts

A Splunk app providing the `zammad` custom alert action, plus the delivery
defaults every homelab detector inherits.

## Why a `[default]` stanza and not a stanza-name prefix

`savedsearches.conf` has **no prefix-based stanza inheritance**. A stanza named
`[HomelabAlert - foo]` inherits nothing from a `[HomelabAlert]` stanza — this
was measured against Splunk 10.2.0, where a child stanza read back the global
default severity and an empty cron rather than the parent's values. `[default]`
is the only inheritance mechanism the file offers.

`[default]` is scoped to the app that declares it. Also measured: a `[default]`
in a throwaway app reached its own searches and none of the 787 owned by the
other 24 apps on the instance.

So the `HomelabAlert` prefix is organizational, not mechanical. It groups
alerts in the UI, and because the stanza name is the Zammad ticket title, it
namespaces Splunk's incidents away from the ones Hermes opens.

## Installation

No new mechanism: tar the app, publish it to the `splunk-addons` bucket, and
add one line to `roles/splunk_docker/vars/addons.yml` in `ansible-splunk` — the
same path the Slack add-on already uses.

```sh
tar -cf splunk-homelab-alerts.tar splunk-homelab-alerts
```

The `svc-splunk` Zammad token is provisioned separately by
`ansible-proxmox-apps` (`roles/zammad`) and delivered to Splunk's
`storage/passwords` at converge. The action stays inert until it arrives.

## Usage

Saved searches in this app inherit both delivery and scheduling from the
`[default]` stanza in `default/savedsearches.conf`. A new detector needs only
its own search and cron:

```ini
[HomelabAlert - indexer queue blocked]
search = <the detector search>
cron_schedule = */5 * * * *
disabled = 0
```

Everything else — the Zammad action, group, priority, correlation key,
`allow_skew` — comes from `[default]`. Override any of them by setting the same
key in the stanza; the stanza wins.

Detectors live in `ansible-splunk`'s `homelab_alerts` app today. They migrate
here one at a time; each arrives `disabled = 1` and is enabled in its own
reviewed change.

## The `zammad` alert action

`bin/zammad.py` opens a Zammad incident, or appends an article to the open one
carrying the same correlation key. Splunk invokes it with `--execute` and one
JSON payload on stdin; a non-zero exit marks the action failed.

**Dedup is by ticket title.** The correlation key defaults to `$name$`, the
saved-search name — already unique, already stable across firings, and already
the title, so there is no second identifier to drift. A detector on a `*/5`
cron appends to one open ticket instead of opening one per cycle. Only `new`
and `open` tickets match, so a recurrence after closure opens a fresh incident.

Tags are deliberately not used: the tag field is not reliably queryable on this
instance (a `tags:*` query matched a ticket whose tags were `null`), whereas
title and state field queries are.

### Credentials

The action authenticates as **`svc-splunk`**, its own Zammad service account,
so incidents opened by a deterministic saved search are attributable to Splunk
rather than to Hermes. The token reaches `storage/passwords` under realm
`zammad`, username `svc-splunk`. It is never written into `savedsearches.conf`.

Authorization rides the **token's** `preferences` scopes, not the user's roles:
a token whose preferences omit a scope is rejected however privileged its user
is. The `svc-splunk` token carries `ticket.agent` only.

### Why a Python handler in a repo that avoids scripts

A modular alert action is Splunk's only extension point for outbound
integrations — scripted alerts are deprecated in favour of exactly this. There
is no native Zammad action, so the app *is* the native path rather than glue
routing around one. The handler is kept to the contract: read payload, resolve
credential, search, create-or-append.

## API

The handler speaks three Zammad REST calls, all under `/api/v1`:

| Call | Purpose |
| --- | --- |
| `GET /tickets/search?query=...` | find the open incident for this correlation key |
| `POST /tickets` | open a new incident when none matches |
| `PUT /tickets/{id}` | append an article to the matching open incident |

Authentication is an `Authorization: Token token=<value>` header — a Zammad API
token, not a username/password pair.

## Layout

```text
default/app.conf                     app registration
default/alert_actions.conf           [zammad] action contract
default/savedsearches.conf           [default] delivery block
default/data/ui/alerts/zammad.html   alert-action setup UI
bin/zammad.py                        the handler (stdlib only)
metadata/default.meta                exports the action to system scope
```

`metadata/default.meta` is load-bearing. The action is defined here but enabled
from another app's `savedsearches.conf` (`ansible-splunk`'s `homelab_alerts`),
and cross-app use requires `export = system` — without it `action.zammad = 1`
over there resolves to nothing and the alert fires with no incident.

## Tests

```sh
python3 bin/zammad.py --selftest
```

Covers article construction, correlation-key override, query-literal quoting,
and the missing-key error path. No framework, no network.

```sh
python3 tests/test_hindsight_bank_dr_alerts.py
```

Guards the four hand-written `hindsight_*` detector stanzas: each one's
`search` line still carries its index/sourcetype/event/result/threshold/
zero-row-guard phrases, and each stays `disabled = 1` until promoted.

## Contributing

Conventional-commit subjects. Keep the handler thin — logic that is not part of
the Splunk alert-action contract belongs in a saved search, not in `bin/`.

## License

Same terms as the rest of the homelab infrastructure repositories.
