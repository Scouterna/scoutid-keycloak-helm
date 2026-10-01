# Installing

## On the Scouterna azure-webservices cluster

Three things must exist before the chart is installed. The first two come from
the platform's project onboarding; the third is self-service. The platform's own
`docs/onboarding.md` and `docs/postgres.md` are the authority for steps 1 and 2;
this is the ScoutID-specific summary.

### 1. Namespace

Namespaces are infra-owned, created from
`k8s/projects/proj-scoutid/infra/namespace-<env>.yaml` and applied by the
`project-infra` ApplicationSet: `proj-scoutid-dev`, `proj-scoutid-staging`,
`proj-scoutid-prod`.

### 2. Database (the shared server)

Projects get a database and a role per environment on the shared PostgreSQL
server, not a cluster of their own. The platform's
`scripts/new-project-db.sh proj-scoutid dev staging prod` generates them. It also
writes `k8s/projects/proj-scoutid/infra/database.yaml`, which puts a Secret named
`proj-scoutid-db` into each namespace with `host`, `port`, `dbname`, `username`
and `password`.

The chart's defaults read exactly that Secret, connection details included:

```yaml
database:
  credentials:
    existingSecret: proj-scoutid-db
```

Backups of the shared server are the platform's concern. A dedicated
CloudNativePG cluster is still possible for a project that needs one; see
[the `cnpg` mode](configuration.md#a-dedicated-cloudnativepg-cluster-cnpg-mode).

### 3. Admin secret

The chart does not create it. Use Sealed Secrets, the recommended self-service
path on this cluster:

```bash
kubeseal --controller-namespace sealed-secrets --fetch-cert > pub-cert.pem

kubectl create secret generic keycloak-admin -n proj-scoutid-dev \
  --from-literal=KC_BOOTSTRAP_ADMIN_USERNAME=admin \
  --from-literal=KC_BOOTSTRAP_ADMIN_PASSWORD="$(openssl rand -base64 24)" \
  --dry-run=client -o yaml \
  | kubeseal --cert pub-cert.pem --format yaml > sealedsecret-keycloak-admin.yaml
```

Commit the sealed file. It is bound to this cluster's key *and* to the namespace
and name, so it cannot be moved between namespaces.

If a value must outlive the cluster or be centrally rotated, use External Secrets
against the `azure-kv` ClusterSecretStore instead. One constraint: `ExternalSecret`
is **not** whitelisted in the `apps-dev` / `apps-prod` AppProjects, so it must live
in `k8s/projects/proj-scoutid/infra/`, not in the app chart.

### 4. Install

```bash
helm install scoutid-keycloak oci://ghcr.io/scouterna/charts/scoutid-keycloak \
  --version 0.7.0 -n proj-scoutid-dev \
  -f examples/values-azure-webservices-dev.yaml
```

Or register an ArgoCD `Application` under `apps-dev` / `apps-prod`. If you do,
the AppProject's `sourceRepos` must include the OCI registry
(`ghcr.io/scouterna/charts`) — it lists only `https://github.com/*` today.

### DNS and certificates

`*.wsinfra.scouterna.net` already resolves to the Traefik load balancer, so a
hostname under that wildcard needs no DNS work. A vanity domain needs its own
records — and if you publish an AAAA record, **verify IPv6 reachability first**.
Let's Encrypt prefers IPv6 when an AAAA exists, so an unreachable one makes
certificate issuance fail for the whole cluster, presenting as "certs won't
issue" rather than as an IPv6 fault.

Validate against `letsencrypt-staging` before switching to `letsencrypt-prod`.

## On any other cluster

The chart needs only a PostgreSQL database, a Secret with its credentials, and an
ingress controller. If the Secret also holds the connection details (keys `host`,
`port`, `dbname` by default), the defaults read them and `host`/`name` can go;
otherwise state them and turn `fromSecret` off:

```yaml
hostname:
  public: id.example.org
database:
  mode: external
  external:
    fromSecret: false
    host: postgres.example.org
    name: keycloak
    sslMode: require
  credentials:
    existingSecret: keycloak-db
    usernameKey: username
    passwordKey: password
admin:
  bootstrap:
    existingSecret: keycloak-admin
ingress:
  className: nginx
  public:
    paths: ["/"]
metrics:
  serviceMonitor:
    enabled: false          # no Prometheus operator
```

If the ingress controller is not Traefik, use `ingress.type: ingress` (the
default). `ingressroute` requires Traefik's CRDs.

For a database that needs a non-standard connection string — Azure managed-identity
auth, for instance — set `database.external.jdbcUrl` directly, with
`fromSecret: false`; it overrides the host/port/name assembly.

## Verifying the install

```bash
kubectl -n <ns> rollout status deploy/<release>-scoutid-keycloak
```

The first boot runs Liquibase migrations and is slow; the startup probe allows ten
minutes. Then:

```bash
kubectl -n <ns> port-forward svc/<release>-scoutid-keycloak 9000:9000
curl -s localhost:9000/health/ready
```

- Certificates: `kubectl -n <ns> get certificate`
- Public host serves `/realms/master/.well-known/openid-configuration`
- The admin console is reachable only on the admin host, not the public one
- Metrics: confirm the target is UP in Prometheus. A ServiceMonitor whose labels
  do not match the Prometheus selector is ignored *silently*.

## Replacing existing hand-written manifests

If Keycloak already runs from manifests applied with `kubectl apply`, there are two
ways in. Keep the database either way — Keycloak's state lives there, not in the pod.

**Replace outright.** Delete the old objects, then `helm install`. Simpler, at the
cost of a short outage. It also clears away anything `kubectl apply` left behind:
apply does not prune, so renamed hosts tend to leave orphaned Certificates and TLS
Secrets, which a Helm release would have tracked and removed.

**Adopt the existing objects.** Helm can take ownership of resources that already
exist if they carry the right metadata. Object names must match, which they will not
by default — the chart names things `<release>-scoutid-keycloak`. Line them up with
`fullnameOverride`, then label and annotate each object:

```bash
kubectl -n <ns> label    <kind>/<name> app.kubernetes.io/managed-by=Helm
kubectl -n <ns> annotate <kind>/<name> meta.helm.sh/release-name=<release>
kubectl -n <ns> annotate <kind>/<name> meta.helm.sh/release-namespace=<ns>
```

Either way, diff before switching:

```bash
helm template <release> oci://ghcr.io/scouterna/charts/scoutid-keycloak \
  --version <ver> -n <ns> -f values.yaml > rendered.yaml
```

## Upgrading

```bash
helm upgrade scoutid-keycloak oci://ghcr.io/scouterna/charts/scoutid-keycloak \
  --version <new> -n <ns> -f values.yaml
```

With a single replica the strategy is `Recreate`, so there is a short outage while
the new pod starts — deliberate, because two Keycloak versions must not run against
one database schema at the same time. Keycloak upgrades may migrate the schema, so
confirm the database backup is current first.

### To 0.7.0: production realm defaults

The bundled realm settings are now production values; see
[Production defaults](configuration.md#production-defaults). Two changes are
visible to users and apps:

- **Sessions are 1 day unless the user ticks "remember me"** (30 days). Before,
  sessions lasted 30 days either way. Users of apps that relied on the long
  session will have to log in again sooner. Development and staging can keep
  longer sessions through `configCli.extraConfig`.
- **Offline tokens expire after 60 days** even when in use.

Realm `master` gets brute-force protection and admin events. The config Job's
name now ends in a checksum of the config (`<release>-config-<hash>`), so a
`kubectl logs job/…` command needs the new name. NOTES prints it.

### To 0.5.0: database defaults changed

The default is now `mode: external` with `fromSecret: true`. With `-f values.yaml`
(and with ArgoCD) both breaking cases are rejected at render time, so nothing
starts against the wrong database:

- **Relying on `mode: cnpg` without stating it:** add `database.mode: cnpg`.
- **`external` with a literal `host`, `port`, `name` or `jdbcUrl`:** either add
  `database.external.fromSecret: false`, or delete those values if the credentials
  Secret already holds them (the platform's `<project>-db` does).

`helm upgrade --reuse-values` is different: Helm then keeps the *previous*
chart's defaults, so the release carries on exactly as before (the old mode and
a literal host). Nothing breaks, but nothing moves to the secret either; switch
to `-f` with updated values to adopt the new defaults.
