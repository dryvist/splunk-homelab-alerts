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

## Backup and data-protection alerts

- `HomelabAlert - backup unit failed`: checks daily and weekly systemd backup
  units every 15 minutes.
- `HomelabAlert - nightly backup silent`: checks daily backup success within 26
  hours at 10:15 UTC.
- `HomelabAlert - weekly backup silent`: checks weekly backup success within 8
  days at 10:20 UTC.
- `HomelabAlert - backup vzdump task failed`: reports Proxmox VE (PVE) task
  errors every 15 minutes.
- `HomelabAlert - backup vzdump task missed`: reports expected PVE nodes without
  a successful vzdump task in 26 hours at 10:25 UTC.
- `HomelabAlert - backup vzdump task stuck`: reports tasks without an end line
  after 4 hours at 10:30 UTC.
- Proxmox Backup Server (PBS) status (`HomelabAlert - backup PBS status
  failed`): reports failures, snapshots or daily prunes older than 26 hours, and
  weekly verification or garbage collection older than 8 days. Checks every 15
  minutes.
- `HomelabAlert - backup PBS task failed`: reports PBS task errors every 15
  minutes.

The vzdump expected-node macro is empty until nodes are configured, so the
missed-run alert returns no rows by default. The PBS alerts require `pbs-status`
and `pbs-task` events in the shared OS log indexes. Splunk cron uses the search
head's configured time zone, which must be UTC. See [Splunk's alert scheduling
docs](https://help.splunk.com/en/splunk-enterprise/alert-and-respond/alerting-manual/10.2/create-alerts/use-cron-expressions-for-alert-scheduling).

Everything else — the Zammad action, group, priority, correlation key,
`allow_skew` — comes from `[default]`. Override any of them by setting the same
key in the stanza; the stanza wins.

## Storage alerts

- `HomelabAlert - ZFS pool fill warning`, `HomelabAlert - ZFS pool fill high`,
  and `HomelabAlert - ZFS pool fill critical`: report the latest pool capacity
  in the 70-80%, 80-90%, and 90%+ bands, with severities 3, 4, and 5. Only one
  band fires per pool.
- `HomelabAlert - ZFS pool days to full`: fits a linear trend to seven days of
  free space and reports a projected fill under 30 days; flat or growing free
  space is skipped.
- `HomelabAlert - ZFS pool health`: reports any pool state other than `ONLINE`
  or a nonzero error count from the latest scan.
- `HomelabAlert - drive SMART unhealthy`: reports a SMART health value of zero.
- `HomelabAlert - drive SMART attributes rising`: reports pending-sector,
  reallocated-sector, or offline-uncorrectable raw counts that are positive and
  higher than the value from 24 hours earlier.

Detectors live in `ansible-splunk`'s `homelab_alerts` app today. They migrate
here one at a time. The app default disables searches; a detector stanza
overrides it when the detector is intentionally enabled.

The `llm_token_usage_by_tier` saved search is an informational report. It groups
daily input, output, and cached-input token totals by registry tier, billing
class, model, and provider. It overrides the app defaults with scheduling and
the Zammad action disabled, so it can be opened manually without dispatching an
alert.

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
| `GET /tickets/search?query=...` | find the open ticket |
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
default/macros.conf                  shared search macros
bin/zammad.py                        the handler (stdlib only)
metadata/default.meta                exports the action to system scope
```

`metadata/default.meta` is load-bearing. The action is defined here but enabled
from another app's `savedsearches.conf` (`ansible-splunk`'s `homelab_alerts`),
and cross-app use requires `export = system` — without it `action.zammad = 1`
over there resolves to nothing and the alert fires with no incident.

The `homelab_os_log_indexes` macro is also exported to system scope for the
OS silence detector in `ansible-splunk`.

## Tests

```sh
python3 bin/zammad.py --selftest
python3 -m unittest discover -s tests -p 'test_*.py'
```

Covers the alert-action contract and the shared OS log index macro. No network.

## Contributing

Conventional-commit subjects. Keep the handler thin — logic that is not part of
the Splunk alert-action contract belongs in a saved search, not in `bin/`.

## License

Same terms as the rest of the homelab infrastructure repositories.
