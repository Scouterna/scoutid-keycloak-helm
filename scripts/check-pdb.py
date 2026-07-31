#!/usr/bin/env python3
"""Assert the PodDisruptionBudget renders exactly one budget field.

The API server rejects a PDB carrying both minAvailable and maxUnavailable
("minAvailable and maxUnavailable cannot be both set"), and a PDB with neither
defaults to minAvailable: 0 — a budget that permits every eviction, which looks
configured but protects nothing. Both failures land at apply time, not at
render time, so they are pinned here.

A zero is a real setting: maxUnavailable: 0 blocks every voluntary eviction.
Helm's `with` treats 0 as empty and would silently drop it, so the zero cases are
the ones that matter most below.

Run from the repo root:  python3 scripts/check-pdb.py
"""

import subprocess
import sys

import yaml

CHART = "charts/scoutid-keycloak"
BASE = [
    "--set", "hostname.public=id.example.se",
    "--set", "database.cnpg.clusterName=db",
    "--set", "admin.bootstrap.existingSecret=kc-admin",
    "--set", "podDisruptionBudget.enabled=true",
]

# (extra --set args) -> expected spec field, or None when the render must be rejected
CASES = [
    ([], {"minAvailable": 1}),
    (["--set", "podDisruptionBudget.minAvailable=0"], {"minAvailable": 0}),
    (["--set", "podDisruptionBudget.minAvailable=",
      "--set", "podDisruptionBudget.maxUnavailable=0"], {"maxUnavailable": 0}),
    (["--set", "podDisruptionBudget.minAvailable=",
      "--set", "podDisruptionBudget.maxUnavailable=1"], {"maxUnavailable": 1}),
    (["--set", "podDisruptionBudget.minAvailable=50%"], {"minAvailable": "50%"}),
    # Both set: rejected.
    (["--set", "podDisruptionBudget.maxUnavailable=1"], None),
    # Neither set: rejected.
    (["--set", "podDisruptionBudget.minAvailable="], None),
]


def main():
    fail = 0
    for extra, expected in CASES:
        label = " ".join(extra) or "(defaults)"
        out = subprocess.run(["helm", "template", "kc", CHART, *BASE, *extra],
                             capture_output=True, text=True)
        if expected is None:
            if out.returncode == 0:
                print(f"::error::{label} should have been rejected but rendered")
                fail = 1
            else:
                print(f"ok: {label} -> rejected")
            continue

        if out.returncode != 0:
            print(f"::error::{label} failed to render: {out.stderr.strip()}")
            fail = 1
            continue

        pdbs = [d for d in yaml.safe_load_all(out.stdout)
                if d and d.get("kind") == "PodDisruptionBudget"]
        if not pdbs:
            print(f"::error::{label} rendered no PodDisruptionBudget")
            fail = 1
            continue

        spec = {k: v for k, v in pdbs[0]["spec"].items() if k != "selector"}
        if spec != expected:
            print(f"::error::{label} rendered {spec}, expected {expected}")
            fail = 1
        else:
            print(f"ok: {label} -> {spec}")

    return fail


if __name__ == "__main__":
    sys.exit(main())
