#!/usr/bin/env python3
"""Assert the root-redirect route outranks a catch-all path route.

Reads `helm template` output on stdin, rendered with ingress.type=ingressroute,
rootRedirect enabled and "/" among the public paths.

Traefik derives a route's priority from its rule length when none is set, and
PathPrefix(`/`) is longer than Path(`/`) — so without explicit priorities the
catch-all wins and the redirect silently never fires.
"""

import sys

import yaml


def main():
    docs = [d for d in yaml.safe_load_all(sys.stdin) if d]
    routes = [d for d in docs if d.get("kind") == "IngressRoute"]
    if not routes:
        print("::error::no IngressRoute rendered")
        return 1

    rules = routes[0]["spec"]["routes"]
    redirect = [r for r in rules if "Path(`/`)" in r["match"] and "PathPrefix" not in r["match"]]
    catchall = [r for r in rules if "PathPrefix(`/`)" in r["match"]]

    if not redirect:
        print("::error::no root-redirect route found")
        return 1
    if not catchall:
        print("::error::no catch-all route found; the test setup is wrong")
        return 1

    redirect_priority = redirect[0].get("priority", 0)
    catchall_priority = catchall[0].get("priority", 0)

    if redirect_priority <= catchall_priority:
        print(
            f"::error::root redirect priority {redirect_priority} does not exceed "
            f"catch-all priority {catchall_priority}; Traefik would serve the "
            "catch-all and the redirect would never fire"
        )
        return 1

    print(f"ok: redirect priority {redirect_priority} > catch-all {catchall_priority}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
