{{/*
Name helpers.
*/}}
{{- define "scoutid-keycloak.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "scoutid-keycloak.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "scoutid-keycloak.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "scoutid-keycloak.labels" -}}
helm.sh/chart: {{ include "scoutid-keycloak.chart" . }}
{{ include "scoutid-keycloak.selectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "scoutid-keycloak.selectorLabels" -}}
app.kubernetes.io/name: {{ include "scoutid-keycloak.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "scoutid-keycloak.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "scoutid-keycloak.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{/*
Image reference. appVersion is NOT a usable fallback: the upstream repo publishes
only `latest` and `sha-<short>` tags, so a semver tag would always 404.
*/}}
{{- define "scoutid-keycloak.image" -}}
{{- if not .Values.image.tag -}}
{{- fail "image.tag is required; upstream publishes only `latest` and `sha-<short>` tags (appVersion is not a valid tag)" -}}
{{- end -}}
{{- printf "%s:%s" .Values.image.repository .Values.image.tag -}}
{{- end -}}

{{/*
Validation guards. Rendered once from the top of deployment.yaml so a bad values
file fails at `helm template` rather than at runtime.
*/}}
{{- define "scoutid-keycloak.validate" -}}
{{- if not .Values.hostname.public -}}
{{- fail "hostname.public is required (bare host, e.g. id.scouterna.se)" -}}
{{- end -}}
{{- if regexMatch "^https?://" .Values.hostname.public -}}
{{- fail "hostname.public must be a bare host without a scheme (the chart adds https://)" -}}
{{- end -}}
{{- if and .Values.hostname.admin (regexMatch "^https?://" .Values.hostname.admin) -}}
{{- fail "hostname.admin must be a bare host without a scheme (the chart adds https://)" -}}
{{- end -}}
{{- if and (gt (int .Values.replicaCount) 1) (not .Values.cache.enabled) -}}
{{- fail "replicaCount > 1 requires cache.enabled=true; without Infinispan/JGroups discovery, sessions break across replicas" -}}
{{- end -}}
{{- if not (has .Values.database.mode (list "cnpg" "external")) -}}
{{- fail "database.mode must be one of: cnpg, external" -}}
{{- end -}}
{{- if not (has .Values.ingress.type (list "ingress" "ingressroute" "none")) -}}
{{- fail "ingress.type must be one of: ingress, ingressroute, none" -}}
{{- end -}}
{{- if eq .Values.database.mode "cnpg" -}}
{{/* Host and credentials are separate concerns: secretName/existingSecret name a
     credential source and say nothing about where the server is. */}}
{{- if not (or .Values.database.cnpg.clusterName .Values.database.cnpg.host) -}}
{{- fail "database.mode=cnpg requires database.cnpg.clusterName (the CloudNativePG Cluster name, from which the -rw service and -app secret are derived) or an explicit database.cnpg.host. Setting only a secret name leaves the host undefined." -}}
{{- end -}}
{{- if not (or .Values.database.cnpg.clusterName .Values.database.cnpg.secretName .Values.database.credentials.existingSecret) -}}
{{- fail "database.mode=cnpg needs a credential source: set database.cnpg.clusterName (uses the generated <cluster>-app secret), database.cnpg.secretName, or database.credentials.existingSecret." -}}
{{- end -}}
{{- end -}}
{{- if eq .Values.database.mode "external" -}}
{{- if not (or .Values.database.external.jdbcUrl .Values.database.external.host) -}}
{{- fail "database.mode=external requires database.external.host or database.external.jdbcUrl" -}}
{{- end -}}
{{- if not .Values.database.credentials.existingSecret -}}
{{- fail "database.mode=external requires database.credentials.existingSecret" -}}
{{- end -}}
{{- end -}}
{{- if and .Values.ingress.admin.enabled (not .Values.hostname.admin) -}}
{{- fail "ingress.admin.enabled=true requires hostname.admin" -}}
{{- end -}}
{{- if and (eq .Values.ingress.type "ingress") .Values.ingress.public.rootRedirect.enabled -}}
{{- fail "ingress.public.rootRedirect is only implemented for ingress.type=ingressroute; on a plain Ingress add a controller-specific redirect annotation instead" -}}
{{- end -}}
{{- if and .Values.ingress.admin.ipAllowList (eq .Values.ingress.type "ingress") (ne .Values.ingress.className "traefik") -}}
{{- fail (printf "ingress.admin.ipAllowList is enforced by a Traefik Middleware and would be silently ignored by ingress controller %q, leaving the admin host ungated. Either use Traefik, or clear ipAllowList and set an equivalent annotation for your controller in ingress.annotations (nginx: nginx.ingress.kubernetes.io/whitelist-source-range)." .Values.ingress.className) -}}
{{- end -}}
{{- if and .Values.initContainers.waitForDb.enabled (not (include "scoutid-keycloak.dbHost" .)) -}}
{{- fail "initContainers.waitForDb.enabled=true needs a resolvable host, but none could be derived (database.external.jdbcUrl does not expose one). Set database.external.host as well, or disable the init container." -}}
{{- end -}}
{{- if and .Values.configCli.enabled (not (or .Values.configCli.configDir .Values.configCli.existingConfigMap)) -}}
{{- fail "configCli.enabled=true requires configCli.configDir or configCli.existingConfigMap" -}}
{{- end -}}
{{- if and .Values.configCli.configDir .Values.configCli.existingConfigMap -}}
{{- fail "configCli.configDir and configCli.existingConfigMap are mutually exclusive: existingConfigMap wins and configDir would be silently ignored, so your files would never be applied. Set one." -}}
{{- end -}}
{{- if and (or .Values.scoutid.enabled .Values.configCli.enabled) (not .Values.admin.bootstrap.existingSecret) -}}
{{- fail "applying realm config requires admin.bootstrap.existingSecret (config-cli authenticates as that admin). Set it, or disable both scoutid.enabled and configCli.enabled." -}}
{{- end -}}
{{- if .Values.scoutid.enabled -}}
{{- $actual := include "scoutid-keycloak.scoutidRealm" . -}}
{{- if and .Values.scoutid.realm (ne .Values.scoutid.realm $actual) -}}
{{- fail (printf "scoutid.realm=%q does not match the realm the bundled config targets (%q). The realm is fixed by the chart in this release; setting a different value would report one realm while importing another. Remove the override, or disable scoutid.enabled and supply your own config via configCli." .Values.scoutid.realm $actual) -}}
{{- end -}}
{{- end -}}
{{- if and .Values.scoutid.enabled .Values.configCli.existingConfigMap -}}
{{- fail "scoutid.enabled=true cannot be combined with configCli.existingConfigMap: the bundled ScoutID config would be silently replaced by yours. Disable scoutid.enabled if you are supplying a complete realm config." -}}
{{- end -}}
{{/* Both config sources land in one ConfigMap keyed by basename; a name clash would
     silently drop the bundled file. */}}
{{- if and .Values.scoutid.enabled .Values.configCli.enabled .Values.configCli.configDir -}}
{{- $bundledNames := list -}}
{{- range $p, $_ := .Files.Glob "scoutid-config/*.yaml" -}}
{{- $bundledNames = append $bundledNames (base $p) -}}
{{- end -}}
{{- $glob := include "scoutid-keycloak.configDirGlob" . -}}
{{- range $p, $_ := .Files.Glob $glob -}}
{{- if has (base $p) $bundledNames -}}
{{- fail (printf "configCli.configDir contains %q, which collides with a bundled ScoutID config file of the same name and would silently replace it. Rename it (e.g. 10-%s) or disable scoutid.enabled." (base $p) (base $p)) -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- if and .Values.admin.ensurePermanentAdmin.enabled (not .Values.admin.ensurePermanentAdmin.existingSecret) -}}
{{- fail "admin.ensurePermanentAdmin.enabled=true requires admin.ensurePermanentAdmin.existingSecret" -}}
{{- end -}}
{{- if and .Values.admin.ensurePermanentAdmin.enabled (not .Values.admin.bootstrap.existingSecret) -}}
{{- fail "admin.ensurePermanentAdmin.enabled=true requires admin.bootstrap.existingSecret (the Job authenticates as the bootstrap admin first)" -}}
{{- end -}}
{{/* A ServiceMonitor naming a port the Service does not expose is accepted by the
     API server and then scrapes nothing at all — no error, just missing metrics. */}}
{{- if and .Values.metrics.enabled .Values.metrics.serviceMonitor.enabled -}}
{{- $port := .Values.metrics.serviceMonitor.port | default "management" -}}
{{- if not (has $port (list "http" "management")) -}}
{{- fail (printf "metrics.serviceMonitor.port %q is not a port exposed by the Service (http, management); the ServiceMonitor would silently scrape nothing" $port) -}}
{{- end -}}
{{- end -}}
{{/* Clients are registered by operators and kår groups are synced by the Scoutnet
     provider; neither is declared in Git. keycloak-config-cli deletes whatever the
     config files do not declare, and it does so silently — a verified run with
     managedGroup=full removed every kår subgroup and logged nothing. Refuse to
     render rather than hand someone a Job that quietly destroys live data. */}}
{{- if or .Values.scoutid.enabled .Values.configCli.enabled -}}
{{- if eq .Values.configCli.managedClient "full" -}}
{{- fail "configCli.managedClient=full deletes every client not declared in the config files, including relying parties registered by operators. Use no-delete." -}}
{{- end -}}
{{- if eq .Values.configCli.managedGroup "full" -}}
{{- fail "configCli.managedGroup=full deletes every group not declared in the config files, including the kår groups the Scoutnet provider creates at login, and the user memberships attached to them. Use no-delete." -}}
{{- end -}}
{{- end -}}
{{/* The API server rejects a PodDisruptionBudget carrying both fields
     ("minAvailable and maxUnavailable cannot be both set"), and a PDB with neither
     defaults to minAvailable: 0 — a budget that permits every eviction. Both fail
     at apply time rather than here, so catch them while rendering. */}}
{{- if .Values.podDisruptionBudget.enabled -}}
{{- $min := .Values.podDisruptionBudget.minAvailable -}}
{{- $max := .Values.podDisruptionBudget.maxUnavailable -}}
{{- $hasMin := and (not (kindIs "invalid" $min)) (ne (toString $min) "") -}}
{{- $hasMax := and (not (kindIs "invalid" $max)) (ne (toString $max) "") -}}
{{- if and $hasMin $hasMax -}}
{{- fail "podDisruptionBudget: set either minAvailable or maxUnavailable, not both — the API server rejects a PDB with both fields" -}}
{{- end -}}
{{- if and (not $hasMin) (not $hasMax) -}}
{{- fail "podDisruptionBudget.enabled=true requires either minAvailable or maxUnavailable; a PDB with neither allows every voluntary eviction" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
The glob for a user-supplied configCli.configDir. Restricted to the extensions
keycloak-config-cli can actually parse, so a README or a stray editor backup in
that directory is not mounted as realm config. Defined once because the collision
guard and the ConfigMap must agree on exactly which files are in play.
*/}}
{{- define "scoutid-keycloak.configDirGlob" -}}
{{- printf "%s/*.{yaml,yml,json}" (.Values.configCli.configDir | trimSuffix "/") -}}
{{- end -}}

{{/*
Renders a set of files as ConfigMap keys, keyed by basename. Takes a dict of
"files" (a .Files.Glob result) and "root" (the chart context). Shared by the
bundled ScoutID config and a user-supplied configDir so the two cannot drift.
Go's text/template sorts map keys when ranging, so key order is deterministic.
*/}}
{{- define "scoutid-keycloak.configMapData" -}}
{{- $root := .root -}}
{{- range $path, $_ := .files }}
  {{ base $path }}: |
    {{- $root.Files.Get $path | nindent 4 }}
{{- end -}}
{{- end -}}

{{/*
The realm the bundled ScoutID config actually targets, read from the files
themselves so displayed output can never diverge from what is imported.
*/}}
{{- define "scoutid-keycloak.scoutidRealm" -}}
{{- $realms := list -}}
{{- range $path, $_ := .Files.Glob "scoutid-config/*.yaml" -}}
{{- $doc := $.Files.Get $path | fromYaml -}}
{{- if $doc.realm -}}
{{- $realms = append $realms $doc.realm -}}
{{- end -}}
{{- end -}}
{{- $realms = uniq $realms -}}
{{- if gt (len $realms) 1 -}}
{{- fail (printf "the bundled ScoutID config targets more than one realm (%v); every file must declare the same realm" $realms) -}}
{{- end -}}
{{- first $realms -}}
{{- end -}}

{{/*
Secret holding the DB username/password.
cnpg: CloudNativePG generates "<cluster>-app" with keys username/password.
*/}}
{{- define "scoutid-keycloak.dbSecretName" -}}
{{- if .Values.database.credentials.existingSecret -}}
{{- .Values.database.credentials.existingSecret -}}
{{- else if .Values.database.cnpg.secretName -}}
{{- .Values.database.cnpg.secretName -}}
{{- else -}}
{{- printf "%s-app" .Values.database.cnpg.clusterName -}}
{{- end -}}
{{- end -}}

{{/*
DB host. cnpg exposes the primary as the "<cluster>-rw" Service.
*/}}
{{- define "scoutid-keycloak.dbHost" -}}
{{- if eq .Values.database.mode "cnpg" -}}
{{- default (printf "%s-rw" .Values.database.cnpg.clusterName) .Values.database.cnpg.host -}}
{{- else -}}
{{- .Values.database.external.host -}}
{{- end -}}
{{- end -}}

{{- define "scoutid-keycloak.dbPort" -}}
{{- if eq .Values.database.mode "cnpg" -}}5432{{- else -}}{{- .Values.database.external.port | default 5432 -}}{{- end -}}
{{- end -}}

{{- define "scoutid-keycloak.dbName" -}}
{{- if eq .Values.database.mode "cnpg" -}}
{{- default "app" .Values.database.cnpg.database -}}
{{- else -}}
{{- default "keycloak" .Values.database.external.name -}}
{{- end -}}
{{- end -}}

{{/*
Full JDBC URL. An explicit database.external.jdbcUrl always wins.
sslMode/params are appended as query parameters.
*/}}
{{- define "scoutid-keycloak.jdbcUrl" -}}
{{- if and (eq .Values.database.mode "external") .Values.database.external.jdbcUrl -}}
{{- .Values.database.external.jdbcUrl -}}
{{- else -}}
{{- $host := include "scoutid-keycloak.dbHost" . -}}
{{- $port := include "scoutid-keycloak.dbPort" . -}}
{{- $name := include "scoutid-keycloak.dbName" . -}}
{{- $sslMode := ternary (default "disable" .Values.database.cnpg.sslMode) (default "require" .Values.database.external.sslMode) (eq .Values.database.mode "cnpg") -}}
{{- $params := ternary "" (default "" .Values.database.external.params) (eq .Values.database.mode "cnpg") -}}
{{- $query := printf "sslmode=%s" $sslMode -}}
{{- if $params -}}
{{- $query = printf "%s&%s" $query ($params | trimPrefix "&" | trimPrefix "?") -}}
{{- end -}}
{{- printf "jdbc:postgresql://%s:%s/%s?%s" $host $port $name $query -}}
{{- end -}}
{{- end -}}

{{/*
KC_HOSTNAME / KC_HOSTNAME_ADMIN want a full URL in this deployment's convention.
Values take a bare host; the scheme is added here.
*/}}
{{- define "scoutid-keycloak.publicUrl" -}}
{{- printf "https://%s" .Values.hostname.public -}}
{{- end -}}

{{- define "scoutid-keycloak.adminUrl" -}}
{{- printf "https://%s" .Values.hostname.admin -}}
{{- end -}}

{{/*
TLS secret names default to <host>-tls with dots normalised to dashes. A wildcard
host must lose its leading "*." — an asterisk is neither a valid resource name nor
valid unquoted YAML.
*/}}
{{- define "scoutid-keycloak.hostToName" -}}
{{- . | trimPrefix "*." | replace "*" "wildcard" | replace "." "-" | trimAll "-" | lower | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "scoutid-keycloak.publicTlsSecret" -}}
{{- default (printf "%s-tls" (include "scoutid-keycloak.hostToName" .Values.hostname.public)) .Values.ingress.public.tlsSecretName -}}
{{- end -}}

{{- define "scoutid-keycloak.adminTlsSecret" -}}
{{- default (printf "%s-tls" (include "scoutid-keycloak.hostToName" .Values.hostname.admin)) .Values.ingress.admin.tlsSecretName -}}
{{- end -}}

{{/*
Internal URL used by the Jobs to reach Keycloak.
*/}}
{{- define "scoutid-keycloak.internalUrl" -}}
{{- printf "http://%s:%d" (include "scoutid-keycloak.fullname" .) (int .Values.service.httpPort) -}}
{{- end -}}
