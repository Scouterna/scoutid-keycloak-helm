#!/usr/bin/env python3
"""Assert the config-cli Job never emits an empty annotations map.

Reads `helm template` output on stdin. With configCli.existingConfigMap set there
is no realm ConfigMap to checksum, so the annotations block has nothing to emit —
a bare `annotations:` key then parses as null rather than a map, which strict
validators and server-side-apply merges reject.
"""

import sys

import yaml


def main():
    jobs = [d for d in yaml.safe_load_all(sys.stdin) if d and d.get("kind") == "Job"]
    if not jobs:
        print("::error::no Job rendered; the test setup is wrong")
        return 1

    fail = 0
    for job in jobs:
        name = job["metadata"]["name"]
        meta = job["spec"]["template"]["metadata"]
        if "annotations" in meta and not meta["annotations"]:
            print(f"::error::Job {name} has an empty pod-template annotations map")
            fail = 1
        else:
            print(f"ok: {name}")
    return fail


if __name__ == "__main__":
    sys.exit(main())
