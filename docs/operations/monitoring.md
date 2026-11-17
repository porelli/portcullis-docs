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
| `group-gate` | `group-gate:8080/metrics` | Decisions by endpoint/result (`allow`, `deny`, and the sign-in pages `stepup`, `needs_stronger`, `present_certificate`), denials and sign-in pages by reason, policy load errors, CRL last fetch and `nextUpdate`, revoked-serial counts |
| `keycloak` | `keycloak:9000/metrics` | Management port (`--metrics-enabled`), not routed. Refused password attempts for `admin` / `portcullis-hub` (password sign-in is never available for them, contract §8.1 "Passwords") still appear as Keycloak `LOGIN_ERROR` events (`invalid_user_credentials`, with the account's user id) although brute-force protection counts nothing: don't alert on them as a lockout |
| `prometheus`, `alertmanager`, `grafana` | self | |
| `portcullis` | `textfile-exporter:9100` | `backup_local.prom` / `backup_offsite.prom` (from `portcullis backup`) and `status.prom` (from `portcullis status --textfile`: service health, Vault active, CA expiry of the root and both intermediates, the newest YubiKey and browser certificate per person and kind, and the [DNS checks](#dns-metrics)) |
| `vault_health` | blackbox → `http://vault:8200/v1/sys/health` | 200 only when initialised, unsealed and active |
| `services`, `services_tcp` | blackbox → enroll, forward-auth, Hub, LLDAP (HTTP); Postgres, LLDAP LDAP (TCP) | Services without a metrics endpoint |
| `wg` | `wg-metrics:9100` (file discovery `secrets/monitoring/prometheus/wg-targets.json`) | Only while the `wg` profile is on (an empty target list otherwise, so no `TargetDown`); over the internal network `portcullis-metrics-wg` (exactly `wg` and Prometheus). The [VPN](vpn.md) edge: `wg_edge_accepted_total{provider}`, `wg_edge_rejected_total{provider,reason}`, `wg_edge_closed_total{provider,reason}`, `wg_provider_stale{provider}`, `wg_role_up{role}`, `wg_people_peers` (configured built-in peers), `wg_mode_restricted` |
| `link` | `wg-metrics:9100` (the same target as `wg`, which drops these families) | Only while the `wg` profile is on. [Multiple servers](servers.md): link's own `wg_link_peer_handshake_age_seconds{server}`, `wg_link_peer_rx_bytes_total{server}`, `wg_link_peer_tx_bytes_total{server}` and `wg_link_connect_rejected_total{path,reason}`, plus every ready worker agent's `GET /v1/metrics`, fetched by `wg` over the tunnel with the `link.control` certificate and labelled `server="<id>"`: `portcullis_agent_info{version,runtime}`, `portcullis_agent_ready`, `portcullis_agent_link_handshake_age_seconds`, `portcullis_agent_disk_free_bytes` / `_disk_total_bytes` (the engine's data root), `portcullis_agent_data_free_bytes` / `_data_total_bytes` (the agent's data directory) and `portcullis_agent_container_unhealthy{app,service}` (`app` is the instance id) |
| `mail`, `mailctl` | `mail-metrics:9180/metrics/prometheus` (Stalwart, Basic auth `prometheus` with the password file `/etc/portcullis/mail-metrics-secret`) and `mailctl-metrics:9100` (Basic auth `prometheus` with `/etc/portcullis/mailctl-metrics-secret`, a copy of `secrets/mail/mailctl-metrics-secret`, at least 32 characters: mailctl refuses to start otherwise; file discovery `secrets/monitoring/prometheus/mail-targets.json`, labels `service="mail"` / `service="mailctl"`) | Only while the `mail` profile is on (an empty target list otherwise), over the internal `portcullis-metrics-mail` network. mailctl's: `portcullis_mail_check{check}` (1 ok, 0 not), `portcullis_mail_dkim_stage{domain,stage}`, `portcullis_mail_cert_expiry_seconds`, `portcullis_mail_queue_messages`, `portcullis_mail_queue_deferred_ratio`. See [Mail operations](mail.md) |
| `hub-usage` | `hub-metrics:9100` | The Hub's [usage history](#usage-history), over the internal network `portcullis-metrics-hub` (exactly the Hub and Prometheus) |
| `tls` | blackbox → `auth.<domain>:443` | Goes through the host's published port, so it sees the certificate browsers see. Verified against the system roots |

### DNS metrics

`status --textfile` writes two gauges per name (the main domain and every
added domain), from the same plans as the
[status DNS block](cli.md#status):

| Metric | Labels | Value |
|--------|--------|-------|
| `portcullis_dns_check` | `name`, `check` (`address`, `caa`, `dnssec`, `foreign`) | `1` when that check of the name has no Warning or Problem, else `0`. `caa` is also `0` when the CA wouldn't issue to the pinned account; `dnssec` is `1` only for `secure` or `unsigned` |
| `portcullis_dnssec_state` | `name`, `state` (`secure`, `unsigned`, `ds_missing`, `ds_mismatch`, `bogus`, `insecure`, `unknown`) | `1` for the name's current state; absent for a name with no plan yet |

Both are absent while the DNS checks are unavailable (the domains service
not running). No alert rule uses them yet; a DNS Problem already counts in
`PortcullisStatusProblems`.

The Vault metrics token is an orphan token without the default policy, with a
10-year TTL. It lives in `secrets/monitoring/prometheus/vault-token`.
`vault init` recreates it when less than a year is left (it raises the
`token/` mount's max TTL to allow this).

## Usage history

The Hub's [Usage](hub.md#usage) page keeps one hour in memory. With the
monitoring profile on, Prometheus scrapes the same figures from the Hub
(job `hub-usage`, `hub-metrics:9100`, set by core as `HUB_METRICS_ADDR`) and
Grafana shows them on the provisioned dashboard **Portcullis usage** (uid
`portcullis-usage`): CPU and working set per app, memory against its limit
per container, storage per app volume and folder, and each filesystem's
use. The Usage page links to it ("History in Grafana ↗") once Prometheus
has scraped the Hub in the last 5 minutes.

| Series | Labels | Value |
|--------|--------|-------|
| `portcullis_container_cpu_seconds_total` | `app`, `service`, `number` | CPU time (counter) |
| `portcullis_container_memory_working_set_bytes`, `portcullis_container_memory_limit_bytes` | the same | Working set and limit |
| `portcullis_container_pids`, `portcullis_container_oom_killed` | the same | Processes; 1 after an OOM kill |
| `portcullis_container_network_receive_bytes_total`, `…_transmit_bytes_total`, `portcullis_container_blkio_read_bytes_total`, `…_write_bytes_total` | the same | Counters |
| `portcullis_storage_alloc_bytes`, `portcullis_storage_measured_timestamp_seconds` | `app`, `kind`, `target` (a volume name, folder id, service or image, never a host path: binds are `bind:<n>`) | Last measured size and when |
| `portcullis_filesystem_free_bytes`, `portcullis_filesystem_total_bytes` | `dev` | Per filesystem |
| `portcullis_usage_sampler_last_success_timestamp_seconds` | — | The sampler's last good sweep |

`app` is the instance id, or `core` (`instance` stays Prometheus' own label, the target `hub-metrics:9100`). A figure the Hub doesn't have is
left out, never exported as 0. **Retention:** the existing
`PROMETHEUS_RETENTION` (default 30 days). Rough cost: 30 containers × 10
series × 2 samples/min × 30 d ≈ 26 M samples, about 40 MB.

## Alerts

| Alert | Fires when | Severity |
|-------|-----------|----------|
| `VaultSealedOrDown` | `/v1/sys/health` ≠ 200 for 2 min | critical |
| `TargetDown` | A scrape target is down for 5 min | warning |
| `ServiceProbeFailed` | A liveness probe fails for 5 min | warning |
| `PublicCertExpiringSoon` | The public (ACME) certificate expires in < 14 days | critical |
| `PublicCertProbeFailed` | TLS to `auth.<domain>` fails for 30 min | warning |
| `CrlStale` | group-gate has no CRL newer than 10 min, or it is past `nextUpdate` | critical |
| `RevocationListUnreadable` | group-gate cannot read `revoked-serials.txt` (it then denies every request that presents a certificate) | critical |
| `GroupGateDenySpike` | > 0.5 denials/s for 10 min | warning |
| `GroupGatePolicyErrors` | The Hub policy file is invalid (group-gate fails closed) | warning |
| `BackupTooOld` | The last successful local or off-host backup is > 36 h old | warning |
| `BackupNeverRan` | No backup metric at all for 6 h | warning |
| `ClientCertExpiring` | A person's newest YubiKey or browser certificate (label `kind`: `yubikey` / `browser`) expires in < 7 days (renew the YubiKey certificate, or make a new browser certificate, on the Sign-in page, `https://people.<domain>/signin`) | info |
| `CaExpiring` | The root, the YubiKey certificate CA (`ca="intermediate"`) or the browser certificate CA (`ca="browser"`) expires in < 90 days | critical |
| `PortcullisVPNDown` | The VPN mode is `admin` or `server` (`portcullis_vpn_mode_restricted == 1`, from `status --textfile`) and `wg` can't be scraped, for 2 min: the VPN-only core surfaces are unreachable. Break-glass: `./portcullis vpn mode apps` | critical |
| `PortcullisVPNProviderStale` | A VPN provider's device list is stale (`wg_provider_stale == 1`) for 5 min: its devices are denied (the identity hook fails or the gateway is down; see the instance's VPN tab) | warning |
| `MailQueueHigh` | More than 100 messages wait in the mail queue for 30 min | warning |
| `MailDeferralsHigh` | More than a fifth of the queued mail is deferred for 1 h (often: outbound port 25 blocked, or a blocklist) | warning |
| `MailCertExpiring` | The mail certificate expires within 14 days, or is missing, for 10 min (check `portcullis-mail.timer`; `./portcullis mail cert`) | warning |
| `MailBlocklisted` | The mail server's address is on a blocklist, or a list refused the query, for 10 min | critical |
| `MailDKIMStuck` | A new DKIM key has waited more than 24 h for DNS, for 10 min | warning |
| `MailCheckFailing` | Any other mail check fails for 1 h (`./portcullis mail status`, or the Hub's doctor) | warning |
| `PortcullisAppMemoryNearLimit` | A container's working set is above 90 % of its memory limit for 10 min (the doctor's `memory_near_limit`) | warning |
| `PortcullisDiskNearlyFull` | A filesystem with Portcullis data has less than 10 % or 5 GiB free for 30 min (the doctor's warning band) | warning |
| `PortcullisDiskAlmostFull` | Less than 3 % or 1 GiB free for 10 min (the doctor's problem band) | critical |
| `PortcullisUsageSamplerStale` | The Hub's usage sampler has had no good sweep for 10 min while the Hub is up | warning |
| `PortcullisUsageSamplerNeverRan` | The Hub has been scraped for 15 min and its sampler has never had a good sweep | warning |
| `PortcullisServerDown` | A worker server has had no tunnel handshake for 5 minutes (`wg_link_peer_handshake_age_seconds > 300`, for 1 min): its apps are unreachable, their containers keep running. Also fires for a server added but never joined | critical |
| `PortcullisServerDiskLow` | Less than 10 % free on a worker's engine data root or the agent's data directory, for 15 min | warning |
| `PortcullisServerContainerUnhealthy` | A worker app's container (`app`, `service`) has failed its healthcheck for 5 min | warning |
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
