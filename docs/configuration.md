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
| `admin.ensurePermanentAdmin.shell` | `["/bin/sh", "-c"]` | Override for images with a different shell path |
| `admin.ensurePermanentAdmin.resources` | 50m/128Mi, limit 512Mi | |

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
| `metrics.serviceMonitor.port` | `management` | Must be a port name the Service exposes |
| `metrics.serviceMonitor.path` | `/metrics` | |
| `metrics.serviceMonitor.interval` | `30s` | Omitted when empty |
| `metrics.serviceMonitor.scrapeTimeout` | `10s` | Omitted when empty |

Metrics are served on the management port (9000), not the HTTP port.

A `port` the Service does not expose is rejected at render time — the API server
would accept such a ServiceMonitor and it would simply scrape nothing. Setting
`interval` or `scrapeTimeout` to null omits the key rather than emitting a blank
one, so Prometheus applies its own global default instead of an empty value.

The `release: kps` label is load-bearing on the Scouterna clusters: Prometheus selects
ServiceMonitors with `serviceMonitorSelector.matchLabels.release=kps`, and a monitor
without it is **ignored silently** — no error anywhere, just no metrics. On a cluster
whose selector differs, change this label. Where there is no Prometheus operator, set
`metrics.serviceMonitor.enabled: false`.

## The ScoutID realm

| Value | Default | Notes |
|---|---|---|
| `scoutid.enabled` | `true` | Applies the bundled ScoutID realm configuration |
| `scoutid.realm` | `""` | Empty reads the realm from the bundled config; a value that disagrees is rejected |

This is what makes the deployment *ScoutID* rather than a stock Keycloak that happens
to contain the provider JARs. With it disabled you get a plain Keycloak: no ScoutID
login flow, no user-profile schema, no ScoutID claims.

The configuration lives in the chart at `scoutid-config/` and is applied by the
keycloak-config-cli Job. It is **chart-owned in this release** — there are no values
for changing its content. Treat a chart upgrade as the way realm configuration
changes.

It configures the **`scoutnet`** realm and leaves `master` stock, so Keycloak
administrators stay separate from ScoutID members. This matches the existing
`dev.id.scouterna.se` deployment.

The realm name is fixed by the bundled files, not by a value. `scoutid.realm` exists
only so tooling can read it: left empty the chart derives it from the config itself,
and a value that disagrees is rejected at render time rather than producing output
that names one realm while importing another. To run ScoutID in a different realm,
disable `scoutid.enabled` and supply your own config through `configCli`.

What it contains:

- **`01-realm.yaml`** — theme `scoutid`, Swedish/English with `sv` default, token and
  session lifetimes, and the full user-profile schema. Scoutnet is the credential
  authority, so self-registration, password reset and email login are all off.
- **`02-authentication.yaml`** — the `ScoutID browser login` flow (cookie
  re-authenticator, falling back to the interactive Scoutnet authenticator) bound as
  the realm's browser flow.
- **`03-scopes.yaml`** — the claims contract: `profile`, `email` and `phone` extended
  with the ScoutID attributes, plus the custom `scoutnet-memberships` scope.
- **`04-clients.yaml`** — `account` (needs the scopes to render attributes) and
  `security-admin-console` (pinned to the built-in browser flow).

Relying-party clients are **not** included. They carry per-environment secrets and
redirect URIs, so they are registered separately.

`admin.bootstrap.existingSecret` is required while this is enabled — config-cli
authenticates as that admin.

### Two things in here that fail silently

**Standard OIDC claims and full-state scopes.** keycloak-config-cli replaces *all*
protocol mappers on a scope it manages. The mappers listed become the complete set,
and anything unlisted is deleted. So `03-scopes.yaml` re-declares every standard
Keycloak mapper alongside the ScoutID ones. Omit them and `preferred_username`,
`given_name` and `family_name` disappear from every token while the import still
reports success. Both the upstream provider repo and the J26 deployment hit this
independently. If you fork this config, keep the built-in mappers.

**Unmanaged attributes.** The provider writes one `group_email_<groupId>` attribute
per group. Those names are dynamic and cannot be declared, so the realm sets
`unmanagedAttributePolicy: ADMIN_EDIT`; without a policy Keycloak 26 discards them.
`scoutnet_profile_hash` and `scoutnet_last_fetch` are declared explicitly — the hash
is the sync change-detection key, and losing it makes every login re-fetch the whole
profile.

### Known deviation: the `phone` scope on `account`

`04-clients.yaml` lists `phone` among the `account` client's default scopes, but
Keycloak ships `phone` as a realm-level *optional* scope and keycloak-config-cli does
not move it, so it ends up optional on that client. The claims contract is unaffected
— `phone` stays in `scopes_supported` and any client requesting `scope=phone` still
receives `phone_number`. Only the account console's default set differs from what the
file states. Add it as a default scope by hand if the account console needs to show
the phone number without an explicit request.

## Bringing your own realm configuration (keycloak-config-cli)

| Value | Default | Notes |
|---|---|---|
| `configCli.enabled` | `false` | |
| `configCli.image` | `adorsys/keycloak-config-cli:6.5.1-26` | Pin to the Keycloak major |
| `configCli.varSubstitution` | `true` | Chart default; the tool's own default is off |
| `configCli.configDir` | `""` | Path inside the chart; `*.yaml`/`*.yml`/`*.json` globbed into a ConfigMap |
| `configCli.existingConfigMap` | `""` | Use a ConfigMap you manage |
| `configCli.managedClient` | `no-delete` | Operator-owned; `full` is rejected |
| `configCli.managedGroup` | `no-delete` | Provider-owned; `full` is rejected |
| `configCli.hook` | `""` | `Sync` re-applies on every ArgoCD sync |
| `configCli.resources` | 50m/256Mi, limit 512Mi | |
| `configCli.podSecurityContext` | `runAsNonRoot`, `RuntimeDefault` | Set to `null` to omit |
| `configCli.securityContext` | no privilege escalation, read-only rootfs, all caps dropped | Set to `null` to omit |

`configDir` is globbed with `.Files.Glob` into a ConfigMap, which removes the manual
`kubectl create configmap --from-file` regeneration step the kustomize setup needed.
Only `.yaml`, `.yml` and `.json` files are picked up, so a README or an editor backup
living in that directory is not mounted as realm config.
A checksum annotation re-runs the Job when the config changes — with
`existingConfigMap` the chart cannot see the content, so no checksum is written and
the Job does not restart on its own.

The security defaults suit the upstream image, which already runs as `nobody`
(65534) and starts on a read-only root filesystem. A custom `configCli.image` that
needs to write outside `/tmp` may need `readOnlyRootFilesystem: false`.

To drop either block entirely, set it to `null` — Helm removes null-valued keys, so
the field is omitted. An empty map (`{}`) does **not** work: Helm merges it with the
defaults and the hardened settings survive.

> **Variable substitution.** keycloak-config-cli ships with substitution *off*.
> Without it, `secret: $(env:CLIENT_SECRET)` is stored as that literal string. The
> failure is deeply misleading: ScoutID login succeeds and only the code-to-token
> exchange fails with `unauthorized_client`, so the application's secret looks
> correct — because it is. Keycloak is holding the placeholder. The chart defaults
> this to `true`.

### Who owns what

keycloak-config-cli manages each resource type in **full** state by default:
anything the config files do not declare is deleted. That is deliberate for most of
the realm — Git is the source of truth and a hand-edit in the admin console is meant
to be overwritten on the next sync. Two resource types are not owned by Git:

| Resource | Owner | On sync |
|---|---|---|
| Realm settings, authentication flows, client scopes, protocol mappers, user profile | **Git** | Overwritten — manual edits are reverted |
| Clients (relying parties) | **Maintainers**, by hand or through a separate GUI | Left alone |
| Groups (one per kår) and user memberships | **The Scoutnet provider**, at login | Left alone |

The chart therefore pins `IMPORT_MANAGED_CLIENT` and `IMPORT_MANAGED_GROUP` to
`no-delete`, and **rejects `full` for either at render time**. Both are set
explicitly rather than left to the partial-document layout that happens to spare
them today: relying on that would make a config-cli upgrade, or a merge of the four
files into one full-realm document, silently start deleting.

> **Declaring the parent group does not make `full` safe** — it makes things worse.
> `no-delete` only protects *undeclared top-level* groups. Declaring `scoutnet`
> promotes it to a managed parent, and `full` then prunes every child not listed in
> Git. Verified on a live deployment: declaring `groups: [{name: scoutnet}]` and
> running with `IMPORT_MANAGED_GROUP=full` deleted all four kår subgroups and the
> memberships attached to them. The Job logged **nothing** about the deletion and
> exited successfully. Making `full` safe would mean declaring every kår in Git and
> keeping it in sync with Scoutnet, which defeats the provider.

> **Group renames are destructive.** Renaming children of a managed parent group has
> deleted hundreds of subgroups and tens of thousands of user-to-group memberships.
> `IMPORT_MANAGED_GROUP=no-delete` does **not** protect against this — it only guards
> undeclared *top-level* groups. Safe procedures: suspend the sync, rename, then
> re-sync; or rename in place with `kcadm` (which preserves the group UUID) and update
> the config afterwards. This is why `configCli.enabled` defaults to `false` — the
> bundled ScoutID config declares no groups, so it is unaffected.

`configCli.enabled` adds *your* configuration on top of the bundled ScoutID files;
both land in one ConfigMap, applied in filename order. Name your files so they sort
after the bundled `01-`–`04-` ones (e.g. `10-clients.yaml`); a filename that collides
with a bundled file is rejected at render time rather than silently replacing it.
`configCli.existingConfigMap` replaces the config entirely, so it cannot be combined
with `scoutid.enabled`, nor with `configCli.configDir` — the ConfigMap would win and
the directory would be ignored, leaving your files unapplied. Both combinations are
rejected at render time.

`scripts/check-config-matrix.py` pins the behaviour of all sixteen combinations of
these flags — which ConfigMap is built, whether the Job runs, and what it mounts — and
runs in CI.

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
| `cache.jgroupsPort` | `7800` | Container port and headless Service port |

`replicaCount > 1` without `cache.enabled` is rejected at render time. Without
Infinispan replication each replica keeps its own session cache, so users are logged
out at random depending on which pod serves them. With `cache.enabled`, the chart adds
a headless service for JGroups discovery and switches the strategy to `RollingUpdate`.

Single-replica is the proven configuration. Multi-replica has not been exercised on
these clusters.

`cache.jgroupsPort` drives both the container port and the headless Service, so the
two cannot drift. JGroups additionally opens its failure-detection socket at that
port + 50000 (57800 by default); that one is peer-to-peer and needs no Service entry.
The chart passes `-Djgroups.tcp.port` from this value, so changing `jgroupsPort`
is enough — container port, headless Service and JGroups itself all follow.
(`jgroups.bind_port` is the JGroups-level name and is *not* honoured by Keycloak;
verified against the image.)

### Disruption budget

| Value | Default | Notes |
|---|---|---|
| `podDisruptionBudget.enabled` | `false` | |
| `podDisruptionBudget.minAvailable` | `1` | Integer or percentage |
| `podDisruptionBudget.maxUnavailable` | `""` | Integer or percentage |

Set exactly one of the two. The API server rejects a PDB carrying both
(`minAvailable and maxUnavailable cannot be both set`), and one carrying neither
silently defaults to `minAvailable: 0` — a budget that permits every eviction. Both
cases are rejected at render time instead.

`0` is a meaningful value and is preserved: `maxUnavailable: 0` blocks every
voluntary eviction. Note that a PDB at `minAvailable: 1` with `replicaCount: 1`
blocks node drains entirely, which is usually not what you want.

## Security context

Defaults are `runAsNonRoot`, `seccompProfile: RuntimeDefault`, no privilege
escalation, and all capabilities dropped. `readOnlyRootFilesystem` is **false**
because Keycloak writes to `/opt/keycloak/data` at runtime.

## Waiting for the database

| Value | Default | Notes |
|---|---|---|
| `initContainers.waitForDb.enabled` | `false` | |
| `initContainers.waitForDb.image` | `busybox:1.36` | Default command needs `sh` and `nc` |
| `initContainers.waitForDb.runAsUser` | `65534` | busybox runs as UID 0 |
| `initContainers.waitForDb.timeoutSeconds` | `300` | Fails the pod instead of waiting forever |
| `initContainers.waitForDb.intervalSeconds` | `3` | |
| `initContainers.waitForDb.command` | `[]` | Replaces the default probe when non-empty; `[]` keeps the default |
| `initContainers.waitForDb.resources` | 10m / 16Mi | |

Off by default. It only makes the wait visible in the logs: Keycloak retries the
database connection itself, and `startupProbe.failureThreshold: 60` already allows
about ten minutes for a slow first boot.

Three things to know if you enable it. The busybox image runs as UID 0, which
`runAsNonRoot: true` rejects with `CreateContainerConfigError` — the pod never
starts, and the message points at the init container rather than at the security
context. `runAsUser: 65534` is applied by default to prevent that. Because it
resolves a host itself, it cannot be used with a bare `database.external.jdbcUrl`
(no host is exposed to derive); that combination is rejected at render time rather
than rendering a loop that waits forever on port 5432 of nothing. And the wait is
bounded by `timeoutSeconds`: on expiry the container exits non-zero with the host and
port in the message, so a DNS, NetworkPolicy or wrong-host problem surfaces as a
failing pod rather than one stuck in `Init:` indefinitely.

The default command assumes `sh` and `nc` are present. Set
`initContainers.waitForDb.command` to replace it wholesale for an image that has
neither — the chart then makes no assumption about the image's contents.

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
