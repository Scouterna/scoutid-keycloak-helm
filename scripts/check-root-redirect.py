#!/usr/bin/env python3
"""Assert ingress.public.rootRedirect works in both Traefik modes, or is rejected.

Every way this breaks is silent: a regex that misses the root (Traefik then
forwards "/" to Keycloak), a router ranked below a catch-all "/" Prefix (the
redirect never fires), a middleware reference that names nothing (Traefik drops
the router), or a cert-manager annotation on the extra Ingress (two owners of one
TLS secret). Each rejection is matched on its message.

Run from the repo root:  python3 scripts/check-root-redirect.py
"""

import json
import re
import subprocess
import sys
import tempfile

import yaml

CHART = "charts/scoutid-keycloak"
NS = "myns"
HOST = "id.example.se"
BASE = {
    "hostname": {"public": HOST},
    "database": {"credentials": {"existingSecret": "db"}},
    "admin": {"bootstrap": {"existingSecret": "a"}},
}
ON = {"enabled": True}

failed = 0


def error(msg):
    global failed
    failed += 1
    print(f"::error::{msg}")


def render(ingress):
    with tempfile.NamedTemporaryFile("w", suffix=".yaml") as f:
        json.dump({**BASE, "ingress": ingress}, f)
        f.flush()
        return subprocess.run(["helm", "template", "kc", CHART, "-n", NS, "-f", f.name],
                              capture_output=True, text=True)


def objects(stdout):
    return [d for d in yaml.safe_load_all(stdout) if d]


def check_regex(desc, mw):
    regex = mw["spec"]["redirectRegex"]["regex"]
    for url, want in [(f"https://{HOST}", True), (f"https://{HOST}/", True),
                      (f"https://{HOST}/?x=1", True), (f"https://{HOST}/realms", False),
                      (f"https://{HOST}/realms/scoutid", False),
                      (f"https://{HOST}/?x=1/realms", True),   # all query, still the root
                      ("https://idXexample.se/", False)]:     # dots must be escaped
        if bool(re.match(regex, url)) != want:
            error(f"{desc}: regex {regex!r} {'missed' if want else 'matched'} {url}")
            return
    if not mw["spec"]["redirectRegex"].get("permanent"):
        error(f"{desc}: redirect is not permanent")
        return
    print(f"ok: {desc}: regex matches the root with or without query, nothing else")


def main():
    # Plain Ingress (Traefik class) with a catch-all "/" and a user cert-manager annotation.
    proc = render({"public": {"paths": ["/"], "rootRedirect": ON},
                   "annotations": {"cert-manager.io/cluster-issuer": "mine",
                                   "traefik.ingress.kubernetes.io/router.entrypoints": "websecure"}})
    if proc.returncode != 0:
        error(f"ingress mode: render failed: {proc.stderr.strip()}")
    else:
        docs = objects(proc.stdout)
        mws = [d for d in docs if d["kind"] == "Middleware" and d["metadata"]["name"].endswith("-root-redirect")]
        ings = {d["metadata"]["name"]: d for d in docs if d["kind"] == "Ingress"}
        root = next((d for n, d in ings.items() if n.endswith("-root-redirect")), None)
        public = ings.get("kc-scoutid-keycloak")
        if not mws or not root or not public:
            error(f"ingress mode: missing objects (middleware={bool(mws)} root={bool(root)} public={bool(public)})")
        else:
            check_regex("ingress mode", mws[0])
            ann = root["metadata"]["annotations"]
            want_ref = f"{NS}-{mws[0]['metadata']['name']}@kubernetescrd"
            if ann.get("traefik.ingress.kubernetes.io/router.middlewares") != want_ref:
                error(f"middleware reference {ann.get('traefik.ingress.kubernetes.io/router.middlewares')!r}, expected {want_ref!r}")
            if any(k.startswith("cert-manager.io/") for k in ann):
                error("redirect Ingress carries a cert-manager annotation; the public TLS secret would get two owners")
            if ann.get("traefik.ingress.kubernetes.io/router.entrypoints") != "websecure":
                error("user annotations other than cert-manager were not carried over")
            paths = root["spec"]["rules"][0]["http"]["paths"]
            if [(p["path"], p["pathType"]) for p in paths] != [("/", "Exact")]:
                error(f"redirect Ingress paths {paths}, expected only / Exact")
            if root["spec"]["tls"] != public["spec"]["tls"]:
                error("redirect Ingress does not share the public TLS host and secret")
            # Traefik ranks an unannotated Ingress router by its rule length.
            catchall = len(f"Host(`{HOST}`) && PathPrefix(`/`)")
            prio = int(ann.get("traefik.ingress.kubernetes.io/router.priority", 0))
            if prio <= catchall:
                error(f"redirect priority {prio} does not outrank the catch-all's {catchall}")
            if not failed:
                print(f"ok: ingress mode: Exact / with priority {prio} > {catchall}, middleware "
                      "wired, shared TLS secret, no cert-manager annotation")

    # IngressRoute mode shares the Middleware; route priority is check-route-priority.py.
    proc = render({"type": "ingressroute", "public": {"rootRedirect": ON}})
    if proc.returncode != 0:
        error(f"ingressroute mode: render failed: {proc.stderr.strip()}")
    else:
        docs = objects(proc.stdout)
        mws = [d for d in docs if d["kind"] == "Middleware" and d["metadata"]["name"].endswith("-root-redirect")]
        if len(mws) != 1:
            error(f"ingressroute mode: expected one redirect Middleware, got {len(mws)}")
        else:
            check_regex("ingressroute mode", mws[0])
        if any(d["kind"] == "Ingress" for d in docs):
            error("ingressroute mode rendered a plain Ingress")

    # Disabled: nothing extra.
    proc = render({"public": {"paths": ["/"]}})
    names = [d["metadata"]["name"] for d in objects(proc.stdout)] if proc.returncode == 0 else ["render failed"]
    if any("root-redirect" in n for n in names) or "render failed" in names:
        error(f"rootRedirect disabled still rendered: {[n for n in names if 'root-redirect' in n] or names}")
    else:
        print("ok: disabled renders no redirect objects")

    for desc, ingress, message in [
        ("non-Traefik class", {"className": "nginx", "public": {"rootRedirect": ON}},
         "would be silently ignored by ingress controller \"nginx\""),
        ("ingress.type=none", {"type": "none", "public": {"rootRedirect": ON}},
         "ingress.type=none renders none"),
        ("public ingress disabled", {"public": {"enabled": False, "rootRedirect": ON}},
         "requires ingress.public.enabled=true"),
    ]:
        proc = render(ingress)
        if proc.returncode == 0:
            error(f"guard did not fire: {desc}")
        elif message not in proc.stderr:
            error(f"{desc}: failed for another reason: {proc.stderr.strip()}")
        else:
            print(f"ok: rejected {desc}")

    print()
    if failed:
        print(f"{failed} root-redirect expectation(s) failed")
        return 1
    print("all root-redirect expectations hold")
    return 0


if __name__ == "__main__":
    sys.exit(main())
