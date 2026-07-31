#!/usr/bin/env python3
"""Assert NOTES.txt reports the realm the bundled config actually imports.

NOTES.txt tells the operator which realm to curl. If that disagrees with the
realm inside scoutid-config/, the instructions send people to a realm that does
not exist — and nothing else in CI would notice.

`helm template` does not render NOTES.txt, and `helm install --dry-run=client`
contacts the cluster (it fails in CI, which has none). So this renders the
NOTES.txt template directly through a throwaway chart that has no other
templates, which needs no cluster on either Helm 3 or 4.

Run from the repo root:  python3 scripts/check-notes-realm.py
"""

import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

import yaml

CHART = pathlib.Path("charts/scoutid-keycloak")
BASE = [
    "--set", "hostname.public=id.example.se",
    "--set", "database.cnpg.clusterName=db",
    "--set", "admin.bootstrap.existingSecret=kc-admin",
]


def bundled_realms():
    """The realm every file under scoutid-config/ declares."""
    realms = set()
    for path in sorted((CHART / "scoutid-config").glob("*.yaml")):
        doc = yaml.safe_load(path.read_text())
        if isinstance(doc, dict) and doc.get("realm"):
            realms.add(doc["realm"])
    return realms


def rendered_notes():
    """NOTES.txt rendered as a normal template, so no cluster is involved."""
    with tempfile.TemporaryDirectory() as tmp:
        probe = pathlib.Path(tmp) / "probe"
        shutil.copytree(CHART, probe)
        templates = probe / "templates"
        # Keep NOTES.txt and the partials it calls; drop every real manifest.
        for child in templates.iterdir():
            if child.name in ("NOTES.txt",) or child.name.startswith("_"):
                continue
            child.unlink() if child.is_file() else shutil.rmtree(child)
        # Rendered as a template it must produce output, so give it a document.
        notes = (templates / "NOTES.txt").read_text()
        (templates / "notes-probe.yaml").write_text(
            "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: notes-probe\ndata:\n"
            "  notes: |\n" + "".join(f"    {line}\n" for line in notes.splitlines())
        )
        (templates / "NOTES.txt").unlink()

        out = subprocess.run(["helm", "template", "probe", str(probe), *BASE],
                             capture_output=True, text=True)
        if out.returncode != 0:
            print(f"::error::could not render NOTES.txt: {out.stderr.strip()}")
            return None
        return out.stdout


def main():
    realms = bundled_realms()
    if len(realms) != 1:
        print(f"::error::expected exactly one realm in scoutid-config/, found {sorted(realms)}")
        return 1
    imported = realms.pop()

    notes = rendered_notes()
    if notes is None:
        return 1

    reported = set(re.findall(r"realms/([A-Za-z0-9_-]+)/\.well-known", notes))
    reported |= set(re.findall(r"applied to realm '([A-Za-z0-9_-]+)'", notes))
    if not reported:
        print("::error::NOTES.txt names no realm; the extraction is out of date")
        return 1

    if reported != {imported}:
        print(f"::error::NOTES reports realm(s) {sorted(reported)} but the config "
              f"imports {imported!r}")
        return 1

    print(f"ok: NOTES and the bundled config both use realm {imported!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
