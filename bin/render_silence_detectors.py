#!/usr/bin/env python3
"""Render ansible-splunk's per-index silence detectors into this app.

Detectors are defined once, as a loop, in ansible-splunk's
roles/splunk_docker/defaults/main/11-silence-detectors.yml and rendered by
roles/splunk_docker/templates/savedsearches/07-generic-silence-detectors.j2.
This script renders the SAME template against the SAME data (using Jinja2
with Ansible's own defaults -- see ansible-splunk's tests/templates/_render_env.py,
which this mirrors) so the packaged copy cannot silently diverge from the
generator's loop: adding a detector to the YAML and re-running this script
picks it up automatically. A hand-written stanza per detector would not.

The packaged copies are always forced `disabled = 1` regardless of the
source value -- this app is not the live delivery path yet (see README:
"They migrate here one at a time; each arrives disabled = 1"). Ansible's
homelab_alerts app remains the one actually firing until a detector is
promoted in its own reviewed change.

Usage:
    python3 bin/render_silence_detectors.py [path-to-ansible-splunk-checkout]

Requires: jinja2, pyyaml (present in ansible-splunk's own devshell).
"""

import sys
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader

GENERATED_HEADER = "# --- BEGIN generated: bin/render_silence_detectors.py (do not hand-edit below) ---\n"
GENERATED_FOOTER = "# --- END generated ---\n"


def load_defaults(defaults_dir: Path) -> dict:
    merged: dict = {}
    for path in sorted(defaults_dir.glob("*.yml")):
        merged.update(yaml.safe_load(path.read_text()) or {})
    return merged


def render(ansible_splunk_root: Path) -> str:
    defaults = load_defaults(ansible_splunk_root / "roles/splunk_docker/defaults/main")
    detectors = defaults["splunk_docker_silence_detectors"]
    # Force disabled=1 on every packaged copy -- see module docstring.
    detectors = [{**d, "disabled": 1} for d in detectors]

    template_dir = ansible_splunk_root / "roles/splunk_docker/templates/savedsearches"
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        trim_blocks=True,
        lstrip_blocks=False,
        keep_trailing_newline=True,
    )
    template = env.get_template("07-generic-silence-detectors.j2")
    return template.render(
        splunk_docker_silence_detectors=detectors,
        splunk_docker_silence_lookback_multiplier=defaults["splunk_docker_silence_lookback_multiplier"],
    )


def main() -> int:
    ansible_splunk_root = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else Path(__file__).resolve().parents[2] / "ansible-splunk"
    )
    if not ansible_splunk_root.is_dir():
        print(f"ERROR: ansible-splunk checkout not found at {ansible_splunk_root}", file=sys.stderr)
        return 1

    rendered = render(ansible_splunk_root)

    target = Path(__file__).resolve().parents[1] / "default" / "savedsearches.conf"
    text = target.read_text()
    start = text.find(GENERATED_HEADER)
    end = text.find(GENERATED_FOOTER)
    block = GENERATED_HEADER + rendered.rstrip("\n") + "\n" + GENERATED_FOOTER
    if start != -1 and end != -1:
        text = text[:start] + block + text[end + len(GENERATED_FOOTER):]
    else:
        text = text.rstrip("\n") + "\n\n" + block
    target.write_text(text)
    stanza_count = rendered.count("\n[")
    print(f"Wrote {stanza_count} stanza(s) to {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
