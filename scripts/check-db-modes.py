#!/usr/bin/env python3
"""Assert how each database mode reaches Keycloak, and that conflicts are rejected.

external + fromSecret (the default) must take host, port and database name from the
credentials secret and never also emit KC_DB_URL, which would override the parts.
A literal host/port/name/jdbcUrl next to fromSecret would be silently ignored, so it
is rejected. Each rejection is matched on its message: a render that fails for some
other reason must not count as the guard firing.

Run from the repo root:  python3 scripts/check-db-modes.py
"""

import json
import subprocess
import sys
import tempfile

import yaml

CHART = "charts/scoutid-keycloak"
BASE = {"hostname": {"public": "id.example.se"}, "admin": {"bootstrap": {"existingSecret": "a"}}}
SECRET = {"credentials": {"existingSecret": "proj-db"}}

failed = 0


def error(msg):
    global failed
    failed += 1
    print(f"::error::{msg}")


def render(database, **extra):
    with tempfile.NamedTemporaryFile("w", suffix=".yaml") as f:
        json.dump({**BASE, "database": database, **extra}, f)
        f.flush()
        proc = subprocess.run(["helm", "template", "kc", CHART, "-f", f.name],
                              capture_output=True, text=True)
    return proc


def env_of(stdout):
    """{container name: {env name: value or (secret, key)}} for the Deployment."""
    docs = [d for d in yaml.safe_load_all(stdout) if d]
    spec = next(d for d in docs if d.get("kind") == "Deployment")["spec"]["template"]["spec"]
    out = {}
    for c in spec.get("initContainers", []) + spec["containers"]:
        env = {}
        for e in c.get("env", []):
            ref = (e.get("valueFrom") or {}).get("secretKeyRef")
            env[e["name"]] = (ref["name"], ref["key"]) if ref else e.get("value")
        out[c["name"]] = env
    return out


def expect(desc, database, want, want_absent=(), container="keycloak", **extra):
    proc = render(database, **extra)
    if proc.returncode != 0:
        error(f"{desc}: render failed: {proc.stderr.strip()}")
        return
    env = env_of(proc.stdout)[container]
    bad = {k: (env.get(k), v) for k, v in want.items() if env.get(k) != v}
    bad.update({k: (env[k], "absent") for k in want_absent if k in env})
    if bad:
        for k, (got, exp) in bad.items():
            error(f"{desc}: {container} {k} = {got!r}, expected {exp!r}")
    else:
        print(f"ok: {desc}")


def expect_rejected(desc, database, message):
    proc = render(database)
    if proc.returncode == 0:
        error(f"guard did not fire: {desc}")
    elif message not in proc.stderr:
        error(f"{desc}: failed for another reason: {proc.stderr.strip()}")
    else:
        print(f"ok: rejected {desc}")


def main():
    parts = {
        "KC_DB_URL_HOST": ("proj-db", "host"),
        "KC_DB_URL_PORT": ("proj-db", "port"),
        "KC_DB_URL_DATABASE": ("proj-db", "dbname"),
        "KC_DB_USERNAME": ("proj-db", "username"),
        "KC_DB_PASSWORD": ("proj-db", "password"),
    }
    expect("default: external + fromSecret", SECRET,
           {**parts, "KC_DB_URL_PROPERTIES": "?sslmode=require"}, want_absent=["KC_DB_URL"])
    expect("fromSecret: sslMode and params in the properties",
           {**SECRET, "external": {"sslMode": "disable", "params": "&connectTimeout=5"}},
           {"KC_DB_URL_PROPERTIES": "?sslmode=disable&connectTimeout=5"})
    expect("fromSecret: custom key names",
           {"credentials": {"existingSecret": "s", "hostKey": "h", "portKey": "p", "databaseKey": "d"}},
           {"KC_DB_URL_HOST": ("s", "h"), "KC_DB_URL_PORT": ("s", "p"), "KC_DB_URL_DATABASE": ("s", "d")})
    expect("fromSecret: wait-for-db reads the host from the secret", SECRET,
           {"DB_HOST": ("proj-db", "host"), "DB_PORT": ("proj-db", "port")},
           container="wait-for-db", initContainers={"waitForDb": {"enabled": True}})
    expect("literal host, default port and name",
           {**SECRET, "external": {"fromSecret": False, "host": "pg.example.se"}},
           {"KC_DB_URL": "jdbc:postgresql://pg.example.se:5432/keycloak?sslmode=require"},
           want_absent=["KC_DB_URL_HOST", "KC_DB_URL_PROPERTIES"])
    expect("literal host, port and name",
           {**SECRET, "external": {"fromSecret": False, "host": "pg", "port": 6543, "name": "kc"}},
           {"KC_DB_URL": "jdbc:postgresql://pg:6543/kc?sslmode=require"})
    expect("literal jdbcUrl",
           {**SECRET, "external": {"fromSecret": False, "jdbcUrl": "jdbc:postgresql://x:1/y"}},
           {"KC_DB_URL": "jdbc:postgresql://x:1/y"})
    expect("literal host: wait-for-db gets it as a value",
           {**SECRET, "external": {"fromSecret": False, "host": "pg.example.se"}},
           {"DB_HOST": "pg.example.se", "DB_PORT": "5432"},
           container="wait-for-db", initContainers={"waitForDb": {"enabled": True}})
    expect("cnpg mode is unaffected by the fromSecret default",
           {"mode": "cnpg", "cnpg": {"clusterName": "db"}},
           {"KC_DB_URL": "jdbc:postgresql://db-rw:5432/app?sslmode=disable",
            "KC_DB_USERNAME": ("db-app", "username")},
           want_absent=["KC_DB_URL_HOST"])

    ignored = "would be ignored: database.external.fromSecret=true"
    for key, value in [("host", "pg"), ("port", 5432), ("name", "kc"),
                       ("jdbcUrl", "jdbc:postgresql://x:1/y")]:
        expect_rejected(f"fromSecret with external.{key}", {**SECRET, "external": {key: value}},
                        f"database.external.{key} {ignored}")
    expect_rejected("external without a secret", {}, "requires database.credentials.existingSecret")
    expect_rejected("fromSecret: false without host or jdbcUrl",
                    {**SECRET, "external": {"fromSecret": False}},
                    "requires database.external.host or database.external.jdbcUrl")

    print()
    if failed:
        print(f"{failed} database-mode expectation(s) failed")
        return 1
    print("all database-mode expectations hold")
    return 0


if __name__ == "__main__":
    sys.exit(main())
