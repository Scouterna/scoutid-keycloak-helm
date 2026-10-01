# scoutid-keycloak

Keycloak with the Scoutnet authenticator and ScoutID theme
([scoutid-keycloak](https://github.com/Scouterna/scoutid-keycloak)).

```bash
helm install scoutid-keycloak oci://ghcr.io/scouterna/charts/scoutid-keycloak \
  --version 0.7.0 -n <namespace> -f values.yaml
```

Ships the ScoutID realm configuration (realm `scoutid`, with production defaults; `master` only hardened): the
ScoutID browser flow against Scoutnet, the `scoutid` theme, the user-profile schema
and the claims contract. `scoutid.enabled: false` gives a plain Keycloak.
Individual realm settings can be overridden per deployment with
`configCli.extraConfig`.

Minimum values:

```yaml
hostname:
  public: id.example.org
database:
  credentials:
    existingSecret: keycloak-db     # keys: host, port, dbname, username, password
admin:
  bootstrap:
    existingSecret: keycloak-admin
```

The chart references existing Secrets and never templates secret material, and it
consumes a database rather than creating one. Defaults suit the Scouterna
`azure-webservices` cluster (Traefik, cert-manager, the shared CloudNativePG
server, kube-prometheus-stack); every platform choice is a value. For a Secret
without connection details, set `database.external.fromSecret: false` and
`database.external.host`.

Full documentation:
<https://github.com/Scouterna/scoutid-keycloak-helm/tree/main/docs>
