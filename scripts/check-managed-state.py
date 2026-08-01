#!/usr/bin/env python3
"""Assert the config-cli Job never prunes operator- or provider-owned resources.

keycloak-config-cli manages each resource type in FULL state by default: anything
the config files do not declare is deleted. That is what the chart wants for
realm settings, flows, scopes and mappers — Git owns them and manual edits are
meant to be overwritten. It is wrong for two resource types:

  clients  registered by maintainers by hand or through a separate GUI
  groups   created by the Scoutnet provider at login, one per kar

Both were verified destructive on a live deployment: declaring the parent group
and running with IMPORT_MANAGED_GROUP=full deleted every kar subgroup and logged
nothing at all, exiting successfully. So the env vars must be present *and*
no-delete; missing entirely is as bad as set to full, because the tool's own
default is full.

Run from the repo root:  python3 scripts/check-managed-state.py
"""

import subprocess
import sys

import yaml

CHART = "charts/scoutid-keycloak"
BASE = [
    "--set", "hostname.public=id.example.se",
    "--set", "database.cnpg.clusterName=db",
    "--set", "admin.bootstrap.existingSecret=kc-admin",
]
REQUIRED = {
    "IMPORT_MANAGED_CLIENT": "no-delete",
    "IMPORT_MANAGED_GROUP": "no-delete",
}


def job_env(*extra):
    out = subprocess.run(["helm", "template", "kc", CHART, *BASE, *extra],
                         capture_output=True, text=True)
    if out.returncode != 0:
        return None
    for doc in yaml.safe_load_all(out.stdout):
        if doc and doc.get("kind") == "Job" and doc["metadata"]["name"].endswith("-config"):
            container = doc["spec"]["template"]["spec"]["containers"][0]
            return {e["name"]: e.get("value") for e in container.get("env", [])}
    return None


def main():
    fail = 0

    env = job_env()
    if env is None:
        print("::error::the config-cli Job did not render")
        return 1

    for name, want in REQUIRED.items():
        got = env.get(name)
        if got is None:
            print(f"::error::{name} is not set; keycloak-config-cli defaults to "
                  "full and would delete undeclared resources")
            fail = 1
        elif got != want:
            print(f"::error::{name}={got!r}, expected {want!r}")
            fail = 1
        else:
            print(f"ok: {name}={got}")

    # full must be refused at render time, not quietly passed through to the Job.
    for knob in ("managedClient", "managedGroup"):
        out = subprocess.run(
            ["helm", "template", "kc", CHART, *BASE, "--set", f"configCli.{knob}=full"],
            capture_output=True, text=True)
        if out.returncode == 0:
            print(f"::error::configCli.{knob}=full rendered instead of being rejected")
            fail = 1
        else:
            print(f"ok: configCli.{knob}=full rejected")

    return fail


if __name__ == "__main__":
    sys.exit(main())
