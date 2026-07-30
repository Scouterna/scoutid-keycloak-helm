# scoutid-keycloak

Keycloak with the Scoutnet authenticator and ScoutID theme
([scoutid-keycloak](https://github.com/Scouterna/scoutid-keycloak)).

```bash
helm install scoutid-keycloak oci://ghcr.io/scouterna/charts/scoutid-keycloak \
  --version 0.1.0 -n <namespace> -f values.yaml
```

Minimum values:

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

The chart references existing Secrets and never templates secret material, and it
consumes a database rather than creating one. Defaults suit the Scouterna
`azure-webservices` cluster (Traefik, cert-manager, CloudNativePG,
kube-prometheus-stack); every platform choice is a value.

Full documentation:
<https://github.com/Scouterna/scoutid-keycloak-helm/tree/main/docs>
