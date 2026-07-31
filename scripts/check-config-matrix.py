#!/usr/bin/env python3
"""Assert how the chart renders across every combination of the config-source flags.

`scoutid.enabled`, `configCli.enabled`, `configCli.configDir` and
`configCli.existingConfigMap` interact: they decide whether a ConfigMap is built,
whether the config-cli Job runs, and which ConfigMap that Job mounts. Getting a
combination wrong tends to fail silently — a Job that applies nothing, or a
configDir that is quietly ignored — so each of the 16 combinations is pinned here.

Run from the repo root:  python3 scripts/check-config-matrix.py
"""

import itertools
import subprocess
import sys

import yaml

CHART = "charts/scoutid-keycloak"
BASE = [
    "--set", "hostname.public=id.example.se",
    "--set", "database.cnpg.clusterName=db",
    "--set", "admin.bootstrap.existingSecret=kc-admin",
]

# (scoutid, cli, configDir, existingConfigMap) -> expectation.
#   renders:   does `helm template` succeed?
#   configmap: does the chart build a ConfigMap?
#   job:       is the config-cli Job created?
#   mounts:    which ConfigMap name the Job mounts (None when there is no Job)
#
# configDir points at the chart's own scoutid-config/ directory. That keeps the test
# free of extra fixtures shipped in the release, but it means the filenames DO collide
# with the bundled config, so scoutid.enabled + configDir is expected to be rejected.
BUNDLED = "kc-scoutid-keycloak-realm-config"
EXPECTED = {
    # scoutid on + a configDir whose filenames collide with the bundled ones: rejected.
    (True, True, True, False): dict(renders=False),
    (True, False, True, False): dict(renders=True, configmap=True, job=True, mounts=BUNDLED),
    # scoutid on + existingConfigMap: rejected, the bundled config would be replaced.
    (True, True, True, True): dict(renders=False),
    (True, True, False, True): dict(renders=False),
    (True, False, True, True): dict(renders=False),
    (True, False, False, True): dict(renders=False),
    # configCli.enabled with neither source: nothing to apply.
    (True, True, False, False): dict(renders=False),
    # scoutid on, configCli off: the bundled config is applied.
    (True, False, False, False): dict(renders=True, configmap=True, job=True, mounts=BUNDLED),
    # scoutid off, configCli on: the operator's own config.
    (False, True, True, True): dict(renders=False),   # configDir would be ignored
    (False, True, True, False): dict(renders=True, configmap=True, job=True, mounts=BUNDLED),
    (False, True, False, True): dict(renders=True, configmap=False, job=True, mounts="mine"),
    (False, True, False, False): dict(renders=False),  # nothing to apply
    # Everything off: a plain Keycloak, no realm config at all.
    (False, False, True, True): dict(renders=False),   # still mutually exclusive
    (False, False, True, False): dict(renders=True, configmap=False, job=False, mounts=None),
    (False, False, False, True): dict(renders=True, configmap=False, job=False, mounts=None),
    (False, False, False, False): dict(renders=True, configmap=False, job=False, mounts=None),
}


def render(scoutid, cli, configdir, existingcm):
    args = ["helm", "template", "kc", CHART] + BASE
    args += ["--set", f"scoutid.enabled={str(scoutid).lower()}"]
    args += ["--set", f"configCli.enabled={str(cli).lower()}"]
    if configdir:
        args += ["--set", "configCli.configDir=scoutid-config"]
    if existingcm:
        args += ["--set", "configCli.existingConfigMap=mine"]
    proc = subprocess.run(args, capture_output=True, text=True)
    return proc.returncode == 0, proc.stdout


def observe(stdout):
    docs = [d for d in yaml.safe_load_all(stdout) if d]
    jobs = [d for d in docs if d.get("kind") == "Job" and d["metadata"]["name"].endswith("-config")]
    mounts = None
    if jobs:
        volumes = jobs[0]["spec"]["template"]["spec"].get("volumes", [])
        names = [v["configMap"]["name"] for v in volumes if "configMap" in v]
        mounts = names[0] if names else None
    return {
        "configmap": any(d.get("kind") == "ConfigMap" for d in docs),
        "job": bool(jobs),
        "mounts": mounts,
    }


def main():
    failed = 0
    for combo in itertools.product([True, False], repeat=4):
        want = EXPECTED[combo]
        label = "scoutid={} cli={} dir={} ecm={}".format(*combo)
        ok, stdout = render(*combo)

        if ok != want["renders"]:
            print(f"::error::{label}: expected renders={want['renders']}, got {ok}")
            failed += 1
            continue
        if not ok:
            print(f"ok: {label} -> rejected, as expected")
            continue

        got = observe(stdout)
        mismatched = [key for key in ("configmap", "job", "mounts") if got[key] != want[key]]
        for key in mismatched:
            print(f"::error::{label}: expected {key}={want[key]!r}, got {got[key]!r}")
        if mismatched:
            failed += 1
        else:
            print(f"ok: {label} -> configmap={got['configmap']} job={got['job']} mounts={got['mounts']}")

    print()
    if failed:
        print(f"{failed} matrix expectation(s) failed")
        return 1
    print(f"all {len(EXPECTED)} config-source combinations behave as specified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
