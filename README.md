# scoutid-keycloak-helm

Helm chart for [ScoutID Keycloak](https://github.com/Scouterna/scoutid-keycloak) — Keycloak
with the Scoutnet authenticator and the ScoutID login theme baked in.

The chart's defaults target the Scouterna `azure-webservices` cluster (Traefik,
cert-manager, CloudNativePG, kube-prometheus-stack), but every platform-specific
choice is a value: it deploys against any Kubernetes and any PostgreSQL.

## Install

```bash
helm install scoutid-keycloak oci://ghcr.io/scouterna/charts/scoutid-keycloak \
  --version 0.1.0 \
  --namespace scoutid-dev \
  -f my-values.yaml
```

Smallest working configuration:

```yaml
hostname:
  public: id.example.org
database:
  mode: external
  external:
    host: postgres.example.org
    name: keycloak
  credentials:
    existingSecret: keycloak-db     # keys: username, password
admin:
  bootstrap:
    existingSecret: keycloak-admin
```

Worked examples for several platforms are in [`examples/`](examples/).

## What you get

The chart ships the ScoutID realm configuration, so an install produces a working
ScoutID rather than a bare Keycloak: the ScoutID browser login flow against Scoutnet,
the `scoutid` login theme, the ScoutID user-profile schema, and the claims contract
(`scoutnet_member_no`, `memberships`, `primary_group_no`, `scoutnet-memberships`
scope, …).

It configures the **`scoutnet`** realm and leaves `master` stock for Keycloak
administrators. Set `scoutid.enabled: false` for a plain Keycloak.

Relying-party clients are not included — they carry per-environment secrets and are
registered separately. See [docs/configuration.md](docs/configuration.md).

## What the chart does not do

- **It never templates secret material.** Every credential is referenced from an
  existing Secret, so it works with Sealed Secrets, External Secrets, the Key Vault
  CSI driver, a CloudNativePG-generated secret, or a hand-made one.
- **It does not create a database.** On `azure-webservices` the CloudNativePG
  `Cluster` is an infra-owned resource; the chart only consumes its generated
  `<cluster>-app` secret.

Both are deliberate — see [docs/configuration.md](docs/configuration.md).

## Documentation

| Document | Contents |
|---|---|
| [docs/install.md](docs/install.md) | Installing on `azure-webservices`, and on any other cluster |
| [docs/configuration.md](docs/configuration.md) | Full values reference and the reasoning behind the defaults |

## Versioning

`version` is the chart's own; `appVersion` tracks the Keycloak release in the
default image. Chart releases are tagged `v<chart-version>` and published to
`ghcr.io/scouterna/charts/scoutid-keycloak`.

## License

Apache 2.0 — see [LICENSE](LICENSE).
