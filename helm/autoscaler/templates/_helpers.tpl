{{/*
Expand the name of the chart.
*/}}
{{- define "autoscaler.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "autoscaler.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "autoscaler.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "autoscaler.labels" -}}
helm.sh/chart: {{ include "autoscaler.chart" . }}
{{ include "autoscaler.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- with .Values.commonLabels }}
{{ toYaml . }}
{{- end }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "autoscaler.selectorLabels" -}}
app.kubernetes.io/name: {{ include "autoscaler.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "autoscaler.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "autoscaler.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Namespace to use
*/}}
{{- define "autoscaler.namespace" -}}
{{- .Values.global.namespace | default "autoscaling-ns" }}
{{- end }}

{{/*
App labels
*/}}
{{- define "autoscaler.app.labels" -}}
{{ include "autoscaler.labels" . }}
app.kubernetes.io/component: app
{{- end }}

{{/*
App selector labels
*/}}
{{- define "autoscaler.app.selectorLabels" -}}
app: {{ .Values.app.name }}
{{- end }}

{{/*
Predictor labels
*/}}
{{- define "autoscaler.predictor.labels" -}}
{{ include "autoscaler.labels" . }}
app.kubernetes.io/component: predictor
{{- end }}

{{/*
Predictor selector labels
*/}}
{{- define "autoscaler.predictor.selectorLabels" -}}
app: {{ .Values.predictor.name }}
{{- end }}

{{/*
Prometheus labels
*/}}
{{- define "autoscaler.prometheus.labels" -}}
{{ include "autoscaler.labels" . }}
app.kubernetes.io/component: prometheus
{{- end }}

{{/*
Prometheus selector labels
*/}}
{{- define "autoscaler.prometheus.selectorLabels" -}}
app: {{ .Values.prometheus.name }}
{{- end }}

{{/*
Prometheus Adapter labels
*/}}
{{- define "autoscaler.prometheusAdapter.labels" -}}
{{ include "autoscaler.labels" . }}
app.kubernetes.io/component: prometheus-adapter
{{- end }}

{{/*
Prometheus Adapter selector labels
*/}}
{{- define "autoscaler.prometheusAdapter.selectorLabels" -}}
app: {{ .Values.prometheusAdapter.name }}
{{- end }}

{{/*
Grafana labels
*/}}
{{- define "autoscaler.grafana.labels" -}}
{{ include "autoscaler.labels" . }}
app.kubernetes.io/component: grafana
{{- end }}

{{/*
Grafana selector labels
*/}}
{{- define "autoscaler.grafana.selectorLabels" -}}
app: {{ .Values.grafana.name }}
{{- end }}

{{/*
Node Exporter labels
*/}}
{{- define "autoscaler.nodeExporter.labels" -}}
{{ include "autoscaler.labels" . }}
app.kubernetes.io/component: node-exporter
{{- end }}

{{/*
Node Exporter selector labels
*/}}
{{- define "autoscaler.nodeExporter.selectorLabels" -}}
app: {{ .Values.nodeExporter.name }}
{{- end }}

{{/*
Kube State Metrics labels
*/}}
{{- define "autoscaler.kubeStateMetrics.labels" -}}
{{ include "autoscaler.labels" . }}
app.kubernetes.io/component: kube-state-metrics
{{- end }}

{{/*
Kube State Metrics selector labels
*/}}
{{- define "autoscaler.kubeStateMetrics.selectorLabels" -}}
app: {{ .Values.kubeStateMetrics.name }}
{{- end }}
