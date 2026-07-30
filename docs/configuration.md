# Configuration

Full values reference, plus the reasoning behind the defaults. Values comments are
kept terse on purpose; the explanations live here.

## Image

| Value | Default | Notes |
|---|---|---|
| `image.repository` | `ghcr.io/scouterna/scoutid-keycloak` | |
| `image.tag` | `latest` | Required; there is no semver tag upstream |
| `image.pullPolicy` | `IfNotPresent` | |
| `image.pullSecrets` | `[]` | Needed if the GHCR package is private |

Pin an explicit tag in production. The upstream CI publishes `sha-<short>` on every
push and `latest` only from the default branch — it never publishes a semver tag, so
`appVersion` (the Keycloak version *inside* the image) is not a usable tag and the
chart does not fall back to it. An empty `image.tag` is rejected at render time.

### What is fixed at build time

The image is an *optimized* Keycloak build (`kc.sh build` at image build time), which
bakes in:

```
KC_DB=postgres
KC_HEALTH_ENABLED=true
KC_METRICS_ENABLED=true
KC_FEATURES=user-event-metrics
```

These cannot be changed by environment variables at runtime. Enabling a feature the
image was not built with makes Keycloak **exit 2** under `start --optimized` — a
crash loop, not a warning. `keycloak.features.userEventMetrics` therefore only ever
*disables* the feature; it cannot introduce one. Changing the DB vendor requires
rebuilding the image.

The image's entrypoint execs `kc.sh "$@"` with no default subcommand, so the chart
always passes `args: ["start", "--optimized"]`. Do not override it.

## Hostnames

| Value | Default | Notes |
|---|---|---|
| `hostname.public` | — | **Required.** Bare host, no scheme |
| `hostname.admin` | `""` | Optional separate admin host |
| `hostname.strict` | `true` | |

Values take bare hosts; the chart builds the `https://…` URLs that `KC_HOSTNAME` and
`KC_HOSTNAME_ADMIN` expect. Passing a scheme is rejected at render time.

Setting `hostname.admin` is what makes Keycloak withhold the admin console from the
public host. This is defence in depth with `ingress.public.paths` — Keycloak refuses
to serve the console there, *and* the ingress does not route to it.

## Database

| Value | Default | Notes |
|---|---|---|
| `database.mode` | `cnpg` | `cnpg` or `external` |
| `database.cnpg.clusterName` | `""` | Reads `<name>-app` and `<name>-rw` |
| `database.cnpg.secretName` | `""` | Override the generated secret (credentials only) |
| `database.cnpg.host` | `""` | Override the `-rw` service (host only) |
| `database.cnpg.database` | `app` | CloudNativePG's bootstrap database |
| `database.cnpg.sslMode` | `disable` | In-cluster hop; `verify-*` needs client certs |
| `database.external.jdbcUrl` | `""` | Wins over host/port/name |
| `database.external.host` | `""` | |
| `database.external.port` | `5432` | |
| `database.external.name` | `keycloak` | |
| `database.external.sslMode` | `require` | |
| `database.external.params` | `""` | Extra JDBC query parameters |
| `database.credentials.existingSecret` | `""` | Defaults to the CNPG app secret |
| `database.credentials.usernameKey` | `username` | |
| `database.credentials.passwordKey` | `password` | |

**The chart does not create a database.** On `azure-webservices` the CloudNativePG
`Cluster` is infra-owned and lives in `k8s/projects/<project>/infra/database.yaml`;
templating one here would both violate that contract and couple a generic chart to
CNPG's CRDs.

In `cnpg` mode, `clusterName` is normally the only value needed: the host is its `-rw`
service and the credentials are its generated `<cluster>-app` secret. The host and the
credentials are nevertheless independent settings, and the chart requires each to be
resolvable on its own — naming only a secret leaves the host undefined, which would
otherwise render `jdbc:postgresql://-rw:5432/…` and never connect. Overriding just one
is fine (`cnpg.host` with `cnpg.secretName`, say); overriding neither, or only the
credential half, is rejected at render time.

`jdbcUrl` is the escape hatch for connection strings the chart cannot assemble — the
Azure managed-identity plugin, for example, needs
`?authenticationPluginClassName=com.azure.identity.extensions.jdbc.postgresql.AzurePostgresqlAuthenticationPlugin`.

> Keycloak's documentation describes a `KCRAW_DB_PASSWORD` variant for passwords with
> literal `$` characters. It is **not honoured** by this image (verified with
> `kc.sh show-config`: `kc.db-password` never appears). The chart uses plain
> `KC_DB_PASSWORD`. If a password ever needs `$`-escaping, do not assume `KCRAW_` works.

On Azure PostgreSQL 15+, `CREATE` on the `public` schema is revoked by default and
Liquibase fails on first boot until you `GRANT ALL ON SCHEMA public TO <user>`. This
does not apply to CloudNativePG.

## Admin access

| Value | Default | Notes |
|---|---|---|
| `admin.bootstrap.existingSecret` | `""` | Omit for an already-provisioned database |
| `admin.bootstrap.usernameKey` | `KC_BOOTSTRAP_ADMIN_USERNAME` | |
| `admin.bootstrap.passwordKey` | `KC_BOOTSTRAP_ADMIN_PASSWORD` | |
| `admin.ensurePermanentAdmin.enabled` | `false` | Runs a `kcadm` Job |
| `admin.ensurePermanentAdmin.hook` | `PostSync` | ArgoCD hook; `""` for a plain Job |

The bootstrap admin is a *bootstrap* credential: Keycloak honours it only while the
master realm has no admin. `ensurePermanentAdmin` runs an idempotent Job that creates
a permanent master-realm admin, so you are not dependent on bootstrap credentials
after the first install.

## Ingress

| Value | Default | Notes |
|---|---|---|
| `ingress.type` | `ingress` | `ingress`, `ingressroute`, or `none` |
| `ingress.className` | `traefik` | |
| `ingress.clusterIssuer` | `letsencrypt-prod` | |
| `ingress.entryPoint` | `websecure` | `ingressroute` only |
| `ingress.public.paths` | `["/realms","/resources"]` | `["/"]` exposes everything |
| `ingress.public.rootRedirect.enabled` | `false` | `ingressroute` only |
| `ingress.admin.enabled` | `false` | |
| `ingress.admin.ipAllowList` | `[]` | Empty means no gate |

`ingress` emits standard `networking.k8s.io/v1` objects and works with any
controller. `ingressroute` emits Traefik CRDs plus explicit cert-manager
`Certificate` resources, and is the only mode supporting `rootRedirect` — asking for
it on a plain Ingress fails at render time rather than silently doing nothing.

The default `public.paths` restricts the public host to `/realms` and `/resources`.
Anything else 404s at the ingress. Combined with a separate `hostname.admin`, the
admin console is unreachable on the public host at two independent layers.

`ipAllowList` renders a Traefik `Middleware` in both modes, and is therefore
**Traefik-specific**. Setting it with a non-Traefik `ingress.className` is rejected at
render time rather than accepted-and-ignored: silently dropping an access control on
the admin console is worse than refusing to render. On nginx, clear `ipAllowList` and
set `nginx.ingress.kubernetes.io/whitelist-source-range` via `ingress.annotations`.

An empty list means no gate at all — prefer that over a `0.0.0.0/0` entry, which
looks like a restriction while allowing everything.

## Metrics

| Value | Default | Notes |
|---|---|---|
| `metrics.enabled` | `true` | |
| `metrics.serviceMonitor.enabled` | `true` | Needs the Prometheus operator CRDs |
| `metrics.serviceMonitor.labels` | `{release: kps}` | Must match the Prometheus selector |

Metrics are served on the management port (9000), not the HTTP port.

The `release: kps` label is load-bearing on the Scouterna clusters: Prometheus selects
ServiceMonitors with `serviceMonitorSelector.matchLabels.release=kps`, and a monitor
without it is **ignored silently** — no error anywhere, just no metrics. On a cluster
whose selector differs, change this label. Where there is no Prometheus operator, set
`metrics.serviceMonitor.enabled: false`.

## Realm configuration (keycloak-config-cli)

| Value | Default | Notes |
|---|---|---|
| `configCli.enabled` | `false` | |
| `configCli.image` | `adorsys/keycloak-config-cli:6.5.1-26` | Pin to the Keycloak major |
| `configCli.varSubstitution` | `true` | Chart default; the tool's own default is off |
| `configCli.configDir` | `""` | Path inside the chart, globbed into a ConfigMap |
| `configCli.existingConfigMap` | `""` | Use a ConfigMap you manage |
| `configCli.managedGroup` | `no-delete` | See the warning below |
| `configCli.hook` | `""` | `Sync` re-applies on every ArgoCD sync |

`configDir` is globbed with `.Files.Glob` into a ConfigMap, which removes the manual
`kubectl create configmap --from-file` regeneration step the kustomize setup needed.
A checksum annotation re-runs the Job when the config changes.

> **Variable substitution.** keycloak-config-cli ships with substitution *off*.
> Without it, `secret: $(env:CLIENT_SECRET)` is stored as that literal string. The
> failure is deeply misleading: ScoutID login succeeds and only the code-to-token
> exchange fails with `unauthorized_client`, so the application's secret looks
> correct — because it is. Keycloak is holding the placeholder. The chart defaults
> this to `true`.

> **Group renames are destructive.** Renaming children of a managed parent group has
> deleted hundreds of subgroups and tens of thousands of user-to-group memberships.
> `IMPORT_MANAGED_GROUP=no-delete` does **not** protect against this — it only guards
> undeclared *top-level* groups. Safe procedures: suspend the sync, rename, then
> re-sync; or rename in place with `kcadm` (which preserves the group UUID) and update
> the config afterwards. This is why `configCli.enabled` defaults to `false`.

### ArgoCD and Jobs

A Job with `ttlSecondsAfterFinished` and no hook annotation is garbage-collected
after completion and then reported `OutOfSync/Missing` forever. Either set a hook
(`Sync` or `PostSync`, so ArgoCD excludes it from sync status) or clear
`ttlSecondsAfterFinished`.

## Clustering

| Value | Default | Notes |
|---|---|---|
| `replicaCount` | `1` | |
| `cache.enabled` | `false` | `KC_CACHE=ispn` + JGroups discovery |
| `cache.stack` | `kubernetes` | |

`replicaCount > 1` without `cache.enabled` is rejected at render time. Without
Infinispan replication each replica keeps its own session cache, so users are logged
out at random depending on which pod serves them. With `cache.enabled`, the chart adds
a headless service for JGroups discovery and switches the strategy to `RollingUpdate`.

Single-replica is the proven configuration. Multi-replica has not been exercised on
these clusters.

## Security context

Defaults are `runAsNonRoot`, `seccompProfile: RuntimeDefault`, no privilege
escalation, and all capabilities dropped. `readOnlyRootFilesystem` is **false**
because Keycloak writes to `/opt/keycloak/data` at runtime.

## Waiting for the database

| Value | Default | Notes |
|---|---|---|
| `initContainers.waitForDb.enabled` | `false` | |
| `initContainers.waitForDb.image` | `busybox:1.36` | |
| `initContainers.waitForDb.runAsUser` | `65534` | busybox runs as UID 0 |

Off by default. It only makes the wait visible in the logs: Keycloak retries the
database connection itself, and `startupProbe.failureThreshold: 60` already allows
about ten minutes for a slow first boot.

Two things to know if you enable it. The busybox image runs as UID 0, which
`runAsNonRoot: true` rejects with `CreateContainerConfigError` — the pod never
starts, and the message points at the init container rather than at the security
context. `runAsUser: 65534` is applied by default to prevent that. And because it
resolves a host itself, it cannot be used with a bare `database.external.jdbcUrl`
(no host is exposed to derive); that combination is rejected at render time rather
than rendering a loop that waits forever on port 5432 of nothing.

## Resources

Defaults request 250m CPU / 768Mi memory with a 1280Mi memory limit and no CPU
limit — house style, and appropriate for the single-node cluster where a CPU limit
throttles startup badly. Keycloak is memory-hungry during Liquibase migrations; do
not lower the memory limit below ~1Gi.

## Escape hatches

`keycloak.extraEnv`, `keycloak.extraEnvFrom`, `extraVolumes`, `extraVolumeMounts`,
`podAnnotations`, `podLabels`, `nodeSelector`, `tolerations`, `affinity`,
`topologySpreadConstraints`.

`extraVolumes` is how CSI-driver secret mounts are attached — mounting the volume is
what makes the Secrets Store CSI driver materialize its Secrets. See
`examples/values-external-db-traefik.yaml`.

> The AKS CSI driver runs without `--enable-secret-rotation` on these clusters: it
> writes a materialized Secret only at *creation*. Rotating a Key Vault value requires
> `kubectl delete secret <name>` followed by a rollout restart. A restart alone is not
> enough.
