#!/usr/bin/env python3
"""Assert configCli.configDir only picks up parseable realm-config files.

The directory a user points at is often a working directory: a README, an editor
backup, a checked-in binary. keycloak-config-cli tries to parse everything it is
given, so mounting a README as realm config fails the import — and mounting a
large binary can blow the 1MiB ConfigMap limit. Only .yaml/.yml/.json are taken.

The collision guard in _helpers.tpl must consider exactly the same file set, or a
file could be mounted without being checked for a name clash with the bundled
ScoutID config. Both go through scoutid-keycloak.configDirGlob; this pins it.

Run from the repo root:  python3 scripts/check-configdir-glob.py
"""

import pathlib
import shutil
import subprocess
import sys
import tempfile

import yaml

CHART = "charts/scoutid-keycloak"
BASE = [
    "--set", "hostname.public=id.example.se",
    "--set", "database.cnpg.clusterName=db",
    "--set", "admin.bootstrap.existingSecret=kc-admin",
]

INCLUDED = {"50-realm.yaml": "realm: t\n",
            "51-more.yml": "realm: t\n",
            "52-extra.json": '{"realm":"t"}\n'}
EXCLUDED = {"README.md": "# notes\n",
            "notes.txt": "scratch\n",
            "50-realm.yaml.bak": "old\n",
            "blob.bin": "\x00binary\n"}


def render(chart_dir, *extra):
    cmd = ["helm", "template", "kc", str(chart_dir), *BASE, *extra]
    out = subprocess.run(cmd, capture_output=True, text=True)
    return out


def main():
    with tempfile.TemporaryDirectory() as tmp:
        chart = pathlib.Path(tmp) / "scoutid-keycloak"
        shutil.copytree(CHART, chart)
        cfg = chart / "mycfg"
        cfg.mkdir()
        for name, body in {**INCLUDED, **EXCLUDED}.items():
            (cfg / name).write_text(body)

        out = render(chart, "--set", "scoutid.enabled=false",
                     "--set", "configCli.enabled=true",
                     "--set", "configCli.configDir=mycfg")
        if out.returncode != 0:
            print(f"::error::render failed: {out.stderr.strip()}")
            return 1

        cms = [d for d in yaml.safe_load_all(out.stdout)
               if d and d.get("kind") == "ConfigMap"]
        if not cms:
            print("::error::no ConfigMap rendered")
            return 1
        keys = set(cms[0].get("data") or {})

        fail = 0
        missing = set(INCLUDED) - keys
        if missing:
            print(f"::error::parseable config files were dropped: {sorted(missing)}")
            fail = 1
        leaked = set(EXCLUDED) & keys
        if leaked:
            print(f"::error::non-config files were mounted as realm config: {sorted(leaked)}")
            fail = 1
        if not fail:
            print(f"ok: mounted exactly {sorted(keys)}")

        # The collision guard must see the same set: a bundled filename supplied
        # through configDir has to be rejected, and a README must not trip it.
        clash = chart / "clashcfg"
        clash.mkdir()
        (clash / "01-realm.yaml").write_text("realm: t\n")
        out = render(chart, "--set", "configCli.enabled=true",
                     "--set", "configCli.configDir=clashcfg")
        if out.returncode == 0:
            print("::error::a configDir file colliding with the bundled config was accepted")
            fail = 1
        else:
            print("ok: colliding filename rejected")

        benign = chart / "benigncfg"
        benign.mkdir()
        (benign / "90-extra.yaml").write_text("realm: t\n")
        (benign / "README.md").write_text("# notes\n")
        out = render(chart, "--set", "configCli.enabled=true",
                     "--set", "configCli.configDir=benigncfg")
        if out.returncode != 0:
            print(f"::error::a non-colliding configDir was rejected: {out.stderr.strip()}")
            fail = 1
        else:
            print("ok: non-colliding configDir accepted")

        return fail


if __name__ == "__main__":
    sys.exit(main())
