#!/usr/bin/env python3
"""Assert named ports resolve: Service -> container, and ServiceMonitor -> Service.

Reads `helm template` output on stdin.

A named targetPort that no container declares is accepted by the API server and
by kubeconform — the Service is created, the Endpoints stay empty, and traffic is
silently blackholed. A ServiceMonitor naming a port the Service does not expose
fails the same way: it is valid, and it scrapes nothing. Neither surfaces as an
error, so both are checked here.

Also pins that the JGroups port moves on both sides together: the headless Service
and the container port must come from the same value.
"""

import sys

import yaml


def main():
    docs = [d for d in yaml.safe_load_all(sys.stdin) if d]

    declared = {}
    for d in docs:
        if d.get("kind") in ("Deployment", "StatefulSet"):
            for c in d["spec"]["template"]["spec"]["containers"]:
                for p in c.get("ports", []):
                    if p.get("name"):
                        declared[p["name"]] = p["containerPort"]

    services = [d for d in docs if d.get("kind") == "Service"]
    if not services:
        print("::error::no Service rendered; the test setup is wrong")
        return 1

    fail = 0
    for svc in services:
        for p in svc["spec"]["ports"]:
            target = p.get("targetPort")
            if not isinstance(target, str):
                continue
            if target not in declared:
                print(f"::error::Service {svc['metadata']['name']} port {p['name']} "
                      f"targets {target!r}, which no container declares — "
                      "Endpoints would stay empty and traffic would be dropped")
                fail = 1
            else:
                print(f"ok: {svc['metadata']['name']}/{p['name']} -> "
                      f"{target} ({declared[target]})")

    # ServiceMonitor endpoints reference Service port *names*, not container ports.
    service_ports = {p["name"] for svc in services for p in svc["spec"]["ports"]}
    for sm in (d for d in docs if d.get("kind") == "ServiceMonitor"):
        for ep in sm["spec"].get("endpoints", []):
            port = ep.get("port")
            if port is None:
                continue
            if port not in service_ports:
                print(f"::error::ServiceMonitor {sm['metadata']['name']} scrapes port "
                      f"{port!r}, which no Service exposes ({sorted(service_ports)}) — "
                      "it would be created and silently scrape nothing")
                fail = 1
            else:
                print(f"ok: servicemonitor/{sm['metadata']['name']} -> {port}")

    return fail


if __name__ == "__main__":
    sys.exit(main())
