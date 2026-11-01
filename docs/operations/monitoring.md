# Monitoring

The opt-in compose profile `monitoring` adds Prometheus, Alertmanager, Grafana
and two small exporters to the core stack. Grafana is at
`https://metrics.<domain>`, for `lldap_admin` only, and nothing else is
published. `./portcullis status` works the same with or without the profile.

## Enable

```bash
# .env
COMPOSE_PROFILES=monitoring
# Optional: where alerts go (default: nowhere; they are only visible in Grafana)
ALERT_NTFY_URL=https://ntfy.sh/<your-topic>
```

```bash
./portcullis up
```

`./portcullis up` generates the files the containers read into
`secrets/monitoring/`, and so do `init`, `upgrade`, `restore` and
`vault init`. `vault init` also creates the Vault metrics token. Always go
through the CLI.

- **DNS.** Add a record for `metrics.<domain>` if you don't use a wildcard.
- **Backup and certificate metrics.** Schedule the backup with
  `./portcullis backup schedule --systemd` (see [Backups](backups.md#schedule-systemd-timer)).
  It runs `portcullis backup` and `portcullis status --textfile`, which write
  those metrics.

## Components

| Service | Image | Networks | Purpose |
|---------|-------|----------|---------|
| prometheus | `prom/prometheus` | `monitoring`, `portcullis` | Scrapes everything below and evaluates `monitoring/prometheus/alerts.yml`. Retention `PROMETHEUS_RETENTION` (default `30d`) |
| alertmanager | `prom/alertmanager` | `monitoring`, `alerting` | Routes alerts to the receivers configured in `.env`. `alerting` is its only network with egress |
| grafana | `grafana/grafana` | `monitoring`, `portcullis-proxy` | Provisioned read-only dashboard "Portcullis", datasources Prometheus + Alertmanager |
| blackbox | `prom/blackbox-exporter` | `monitoring`, `portcullis` | HTTP/TCP liveness probes, Vault seal probe, TLS probe of the public certificate |
| textfile-exporter | `prom/node-exporter` (textfile collector only, no host metrics or mounts) | `monitoring` | Serves `monitoring/textfile/*.prom`, written by `./portcullis` |

All images:

- are pinned `tag@sha256`
- run as non-root (65534; Grafana 472) with read-only root filesystems
- have `no-new-privileges`, no capabilities, and memory/pid limits

`monitoring` is an `internal` network.

## What is scraped

| Job | Target | Notes |
|-----|--------|-------|
| `traefik` | `traefik:8082/metrics` | Internal `metrics` entrypoint, not published, no routers |
| `vault` | `vault:8200/v1/sys/metrics?format=prometheus` | Uses a token with policy `portcullis-metrics` (`vault/policies/metrics.hcl`, read `sys/metrics` only); details below |
| `group-gate` | `group-gate:8080/metrics` | Decisions by endpoint/result, denials and step-ups by reason, policy load errors, CRL last fetch and `nextUpdate`, revoked-serial counts |
| `keycloak` | `keycloak:9000/metrics` | Management port (`--metrics-enabled`), not routed |
| `prometheus`, `alertmanager`, `grafana` | self | |
| `portcullis` | `textfile-exporter:9100` | `backup_local.prom` / `backup_offsite.prom` (from `portcullis backup`) and `status.prom` (from `portcullis status --textfile`: service health, Vault active, CA expiry, newest client cert per user) |
| `vault_health` | blackbox → `http://vault:8200/v1/sys/health` | 200 only when initialised, unsealed and active |
| `services`, `services_tcp` | blackbox → enroll, forward-auth, Hub, LLDAP (HTTP); Postgres, LLDAP LDAP (TCP) | Services without a metrics endpoint |
| `tls` | blackbox → `auth.<domain>:443` | Goes through the host's published port, so it sees the certificate browsers see. Verified against the system roots |

The Vault metrics token is an orphan token without the default policy, with a
10-year TTL. It lives in `secrets/monitoring/prometheus/vault-token`.
`vault init` recreates it when less than a year is left (it raises the
`token/` mount's max TTL to allow this).

## Alerts

| Alert | Fires when | Severity |
|-------|-----------|----------|
| `VaultSealedOrDown` | `/v1/sys/health` ≠ 200 for 2 min | critical |
| `TargetDown` | A scrape target is down for 5 min | warning |
| `ServiceProbeFailed` | A liveness probe fails for 5 min | warning |
| `PublicCertExpiringSoon` | The public (ACME) certificate expires in < 14 days | critical |
| `PublicCertProbeFailed` | TLS to `auth.<domain>` fails for 30 min | warning |
| `CrlStale` | group-gate has no CRL newer than 10 min, or it is past `nextUpdate` | critical |
| `RevocationListUnreadable` | group-gate cannot read `revoked-serials.txt` (it then denies every client cert) | critical |
| `GroupGateDenySpike` | > 0.5 denials/s for 10 min | warning |
| `GroupGatePolicyErrors` | The Hub policy file is invalid (group-gate fails closed) | warning |
| `BackupTooOld` | The last successful local or off-host backup is > 36 h old | warning |
| `BackupNeverRan` | No backup metric at all for 6 h | warning |
| `ClientCertExpiring` | A user's newest client certificate expires in < 7 days | info |
| `CaExpiring` | The root or intermediate CA expires in < 90 days | critical |
| `PortcullisStatusStale` / `PortcullisStatusProblems` | `status --textfile` did not run for 36 h / reported problems for 1 h | warning |

Core CI runs `promtool test rules monitoring/prometheus/tests/alerts_test.yml`,
which covers the main rules.

## Receivers

Receivers are set in `.env`. `./portcullis up` writes
`secrets/monitoring/alertmanager/alertmanager.yml` from them, JSON-encoding the
values so any character is safe. You can set several at once.

| Variables | Receiver |
|-----------|----------|
| `ALERT_WEBHOOK_URL` | Generic webhook (Alertmanager JSON payload) |
| `ALERT_NTFY_URL` | [ntfy](https://ntfy.sh) topic URL, sent with `?template=alertmanager` so ntfy formats the alert |
| `ALERT_SMTP_SMARTHOST` (`host:port`), `ALERT_SMTP_TO`, optional `ALERT_SMTP_FROM` (default `portcullis@<domain>`), `ALERT_SMTP_USERNAME`, `ALERT_SMTP_PASSWORD`, `ALERT_SMTP_REQUIRE_TLS` (`true`) | Email |

After changing them, run `./portcullis up`. It regenerates the file, and a
running Alertmanager reloads it.

## Access and trust

- **`metrics.<domain>` is a core subdomain** in group-gate, like `hub` and
  `traefik`. It always requires `lldap_admin`, and the Hub's policy file can't
  change that. The router uses
  `client-headers@file,portcullis-auth@docker,portcullis-groups@docker`.
- **Grafana trusts only Traefik.** It logs users in from `X-Forwarded-User`
  (the LLDAP **username**) only, never by email (LLDAP email is
  user-editable and Grafana can link accounts by email). The header is
  accepted only from Traefik's fixed IP
  (`GF_AUTH_PROXY_WHITELIST=${PORTCULLIS_TRAEFIK_IP}`). Its login form and basic
  auth are off. Everyone who gets through is an `lldap_admin`, so everyone is a
  Grafana Admin.
- **Prometheus, Alertmanager and the exporters have no route.** To look at
  Prometheus directly, use Grafana's Explore view or
  `docker compose exec prometheus wget -qO- 'http://127.0.0.1:9090/api/v1/alerts'`.
- **Internal metrics endpoints are unauthenticated.** That covers Traefik
  `:8082`, group-gate `/metrics` and Keycloak `:9000`, all on the internal
  `portcullis` network, which only core services join. The Vault metrics token
  can only read `sys/metrics`.
