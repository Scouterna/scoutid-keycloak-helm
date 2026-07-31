#!/usr/bin/env python3
"""Check that the bundled ScoutID realm config survives Helm templating intact.

Reads `helm template` output on stdin. Exits non-zero on any failure, and prints
GitHub Actions error annotations so failures surface on the workflow run.

The claim check is the important one: keycloak-config-cli manages client scopes in
FULL state, so a mapper that is not re-declared is deleted. A config missing the
standard Keycloak mappers imports successfully and silently strips
preferred_username / given_name / family_name / email from every token.
"""

import sys

import yaml

REQUIRED_CLAIMS = {
    "preferred_username",
    "given_name",
    "family_name",
    "email",
    "phone_number",
    "scoutnet_member_no",
    "memberships",
    "primary_group_no",
    "primary_group_name",
    "group_emails_json",
}

EXPECTED_AUTHENTICATORS = ["scoutnet-cookie-authenticator", "scoutnet-authenticator"]


def error(msg):
    print(f"::error::{msg}")


def check_schema_enum(realm):
    """The schema pins scoutid.realm to the realm the bundled config targets.

    Those are two separate files, so a realm rename could leave them disagreeing —
    the schema would then reject the very value the config actually uses.
    """
    import json
    import pathlib

    path = pathlib.Path(__file__).resolve().parent.parent / "charts/scoutid-keycloak/values.schema.json"
    if not path.exists():
        error(f"values.schema.json not found at {path}")
        return False
    schema = json.loads(path.read_text())
    enum = schema["properties"]["scoutid"]["properties"]["realm"].get("enum")
    if enum is None:
        print("ok: scoutid.realm has no enum to check")
        return True
    if sorted(enum) != sorted(["", realm]):
        error(
            f"values.schema.json pins scoutid.realm to {enum}, but the bundled "
            f"config targets realm {realm!r}; update the schema enum"
        )
        return False
    print(f"ok: schema enum matches the bundled realm ({realm})")
    return True


def main():
    docs = [d for d in yaml.safe_load_all(sys.stdin) if d]
    configmaps = [d for d in docs if d.get("kind") == "ConfigMap"]
    if not configmaps:
        error("no ConfigMap rendered — the ScoutID config is missing")
        return 1

    data = configmaps[0]["data"]
    failed = False
    claims = set()
    realms = set()

    for name, body in sorted(data.items()):
        inner = yaml.safe_load(body)  # must survive Helm's indentation
        if not inner:
            error(f"{name} parsed empty after templating")
            failed = True
            continue
        realms.add(inner["realm"])
        for scope in inner.get("clientScopes", []):
            for mapper in scope.get("protocolMappers", []):
                claim = (mapper.get("config") or {}).get("claim.name")
                if claim:
                    claims.add(claim)
        print(f"ok: {name} parsed")

    if realms != {"scoutnet"}:
        error(f"expected realm scoutnet in every file, got {sorted(realms)}")
        failed = True
    elif not check_schema_enum("scoutnet"):
        failed = True

    missing = REQUIRED_CLAIMS - claims
    if missing:
        error(f"claims missing from the rendered scopes: {sorted(missing)}")
        failed = True
    else:
        print(f"ok: all {len(REQUIRED_CLAIMS)} required claims present")

    realm = yaml.safe_load(data["01-realm.yaml"])
    policy = realm["userProfile"].get("unmanagedAttributePolicy")
    if policy != "ADMIN_EDIT":
        error(
            f"unmanagedAttributePolicy is {policy!r}; must be ADMIN_EDIT or the "
            "dynamic group_email_<id> attributes are dropped"
        )
        failed = True
    else:
        print("ok: unmanagedAttributePolicy set")

    auth = yaml.safe_load(data["02-authentication.yaml"])
    ids = [e["authenticator"] for e in auth["authenticationFlows"][0]["authenticationExecutions"]]
    if ids != EXPECTED_AUTHENTICATORS:
        error(f"authenticator IDs {ids} do not match the provider JAR")
        failed = True
    else:
        print("ok: authenticator IDs match the provider JAR")

    clients = [c["clientId"] for c in yaml.safe_load(data["04-clients.yaml"])["clients"]]
    leaked = [c for c in clients if c.startswith("j26-") or "test" in c]
    if leaked:
        error(f"non-core clients leaked into the chart: {leaked}")
        failed = True
    else:
        print(f"ok: only built-in clients ({clients})")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
