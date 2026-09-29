#!/usr/bin/env python3
"""Assert configCli.extraConfig renders as specified and its guards fire.

extraConfig lets a values file override the bundled ScoutID realm settings. Each
way it can go wrong is silent at runtime: an entry that is never mounted, one
that replaces a bundled file, one applied before the bundled file it overrides
(and so undone by it), or a realm-name typo that makes keycloak-config-cli
create a second realm. Every one of those must be rejected at render time.

Run from the repo root:  python3 scripts/check-extra-config.py
"""

import json
import subprocess
import sys
import tempfile

import yaml

CHART = "charts/scoutid-keycloak"
BASE = {
    "hostname": {"public": "id.example.se"},
    "database": {"credentials": {"existingSecret": "db"}},
    "admin": {"bootstrap": {"existingSecret": "kc-admin"}},
}
SESSION = {"realm": "scoutid", "ssoSessionIdleTimeout": 86400, "ssoSessionMaxLifespan": 2592000}

failed = 0


def error(msg):
    global failed
    failed += 1
    print(f"::error::{msg}")


def render(values):
    with tempfile.NamedTemporaryFile("w", suffix=".yaml") as f:
        json.dump({**BASE, **values}, f)
        f.flush()
        proc = subprocess.run(["helm", "template", "kc", CHART, "-f", f.name],
                              capture_output=True, text=True)
    return proc.returncode == 0, proc.stdout, proc.stderr


def cli(extra, **more):
    return {"configCli": {"enabled": True, "extraConfig": extra, **more}}


def configmap(stdout):
    docs = [d for d in yaml.safe_load_all(stdout) if d]
    cms = [d for d in docs if d.get("kind") == "ConfigMap"]
    jobs = [d for d in docs if d.get("kind") == "Job" and d["metadata"]["name"].endswith("-config")]
    return (cms[0]["data"] if cms else {}), (jobs[0] if jobs else None)


def expect_rejected(desc, values):
    ok, _, _ = render(values)
    if ok:
        error(f"guard did not fire: {desc}")
    else:
        print(f"ok: rejected {desc}")


def expect_rendered(desc, values):
    ok, out, err = render(values)
    if not ok:
        error(f"{desc}: render failed: {err.strip()}")
        return None, None
    print(f"ok: renders {desc}")
    return configmap(out)


def main():
    # Map and string forms must produce the same document, after the bundled files.
    data, job = expect_rendered("map form", cli({"10-session.yaml": SESSION}))
    if data is not None:
        if sorted(data) != ["01-realm.yaml", "02-authentication.yaml", "03-scopes.yaml",
                            "04-clients.yaml", "10-session.yaml"]:
            error(f"unexpected ConfigMap keys: {sorted(data)}")
        elif yaml.safe_load(data["10-session.yaml"]) != SESSION:
            error(f"map form changed in rendering: {data['10-session.yaml']!r}")
        else:
            print("ok: map form lands after the bundled files, unchanged")
        if not job:
            error("no config-cli Job with bundled config + extraConfig")

    data, _ = expect_rendered("string form", cli({"10-session.yaml": yaml.safe_dump(SESSION)}))
    if data is not None and yaml.safe_load(data["10-session.yaml"]) != SESSION:
        error("string form does not parse to the same document as the map form")

    data, _ = expect_rendered("JSON string", cli({"10-x.json": '{"realm":"scoutid","eventsEnabled":true}'}))
    if data is not None and json.loads(data["10-x.json"]) != {"realm": "scoutid", "eventsEnabled": True}:
        error("JSON entry changed in rendering")

    data, _ = expect_rendered("env placeholder", cli({"10-smtp.yaml": {"realm": "scoutid",
                                                    "smtpServer": {"password": "$(env:SMTP)"}}}))
    if data is not None and "$(env:SMTP)" not in data["10-smtp.yaml"]:
        error("$(env:...) placeholder was not passed through literally")

    expect_rendered("master realm alongside the ScoutID realm", cli({"10-m.yaml": {"realm": "master"}}))

    # Without the bundled config there is no ordering constraint and any realm goes.
    data, job = expect_rendered("extraConfig as the only source",
                                {"scoutid": {"enabled": False}, **cli({"00-own.yaml": {"realm": "other"}})})
    if data is not None:
        if sorted(data) != ["00-own.yaml"] or not job:
            error(f"extraConfig-only: keys={sorted(data)} job={bool(job)}")

    # A content change must change the checksum, or the Job is not re-run.
    sums = []
    for timeout in (86400, 3600):
        ok, out, _ = render(cli({"10-session.yaml": {**SESSION, "ssoSessionIdleTimeout": timeout}}))
        _, job = configmap(out) if ok else ({}, None)
        sums.append(job and job["spec"]["template"]["metadata"]["annotations"]["checksum/config"])
    if not all(sums) or sums[0] == sums[1]:
        error("checksum/config does not change with extraConfig content")
    else:
        print("ok: checksum follows extraConfig content")

    expect_rejected("extraConfig with configCli.enabled=false",
                    {"configCli": {"enabled": False, "extraConfig": {"10-s.yaml": SESSION}}})
    expect_rejected("extraConfig with existingConfigMap",
                    {"scoutid": {"enabled": False},
                     **cli({"10-s.yaml": SESSION}, existingConfigMap="mine")})
    expect_rejected("name without a config extension", cli({"10-session": SESSION}))
    expect_rejected("name with a path separator", cli({"a/10-session.yaml": SESSION}))
    expect_rejected("name of a bundled file", cli({"01-realm.yaml": SESSION}))
    expect_rejected("name sorting before the bundled files", cli({"00-session.yaml": SESSION}))
    expect_rejected("name sorting between bundled files", cli({"04-a.yaml": SESSION}))
    expect_rejected("name colliding with a configDir file",
                    {"scoutid": {"enabled": False},
                     **cli({"01-realm.yaml": {"realm": "x"}}, configDir="scoutid-config")})
    expect_rejected("empty entry", cli({"10-s.yaml": ""}))
    expect_rejected("unparseable YAML", cli({"10-s.yaml": "realm: [scoutid"}))
    expect_rejected("a list instead of a realm document", cli({"10-s.yaml": "- realm: scoutid"}))
    expect_rejected("no realm", cli({"10-s.yaml": {"ssoSessionIdleTimeout": 60}}))
    expect_rejected("realm typo that would create a new realm",
                    cli({"10-s.yaml": {**SESSION, "realm": "scoutnet"}}))

    print()
    if failed:
        print(f"{failed} extraConfig expectation(s) failed")
        return 1
    print("all extraConfig expectations hold")
    return 0


if __name__ == "__main__":
    sys.exit(main())
