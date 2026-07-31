#!/usr/bin/env python3
"""Assert both Jobs opt out of the Kubernetes service account token.

Reads `helm template` output on stdin, rendered with both Jobs enabled.

Neither Job talks to the Kubernetes API: config-cli and kcadm both authenticate to
Keycloak over HTTP. Kubernetes mounts a service account token by default, so
without an explicit opt-out each Job carries an API credential it never uses.
"""

import sys

import yaml

EXPECTED_JOBS = 2


def main():
    jobs = [d for d in yaml.safe_load_all(sys.stdin) if d and d.get("kind") == "Job"]
    if len(jobs) < EXPECTED_JOBS:
        print(f"::error::expected {EXPECTED_JOBS} Jobs, rendered {len(jobs)}; the test setup is wrong")
        return 1

    fail = 0
    for job in jobs:
        name = job["metadata"]["name"]
        spec = job["spec"]["template"]["spec"]
        if spec.get("automountServiceAccountToken") is not False:
            print(f"::error::Job {name} does not set automountServiceAccountToken: false")
            fail = 1
        else:
            print(f"ok: {name}")
    return fail


if __name__ == "__main__":
    sys.exit(main())
