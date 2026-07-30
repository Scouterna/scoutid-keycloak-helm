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
{{- if and .Values.configCli.enabled (not .Values.admin.bootstrap.existingSecret) -}}
{{- fail "configCli.enabled=true requires admin.bootstrap.existingSecret (config-cli authenticates as that admin)" -}}
{{- end -}}
{{- if and .Values.admin.ensurePermanentAdmin.enabled (not .Values.admin.ensurePermanentAdmin.existingSecret) -}}
{{- fail "admin.ensurePermanentAdmin.enabled=true requires admin.ensurePermanentAdmin.existingSecret" -}}
{{- end -}}
{{- if and .Values.admin.ensurePermanentAdmin.enabled (not .Values.admin.bootstrap.existingSecret) -}}
{{- fail "admin.ensurePermanentAdmin.enabled=true requires admin.bootstrap.existingSecret (the Job authenticates as the bootstrap admin first)" -}}
{{- end -}}
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
TLS secret names default to <host>-tls with dots normalised to dashes.
*/}}
{{- define "scoutid-keycloak.publicTlsSecret" -}}
{{- default (printf "%s-tls" (.Values.hostname.public | replace "." "-")) .Values.ingress.public.tlsSecretName -}}
{{- end -}}

{{- define "scoutid-keycloak.adminTlsSecret" -}}
{{- default (printf "%s-tls" (.Values.hostname.admin | replace "." "-")) .Values.ingress.admin.tlsSecretName -}}
{{- end -}}

{{/*
Internal URL used by the Jobs to reach Keycloak.
*/}}
{{- define "scoutid-keycloak.internalUrl" -}}
{{- printf "http://%s:%d" (include "scoutid-keycloak.fullname" .) (int .Values.service.httpPort) -}}
{{- end -}}
