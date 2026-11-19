# 📬 Stalwart

> Mail server for every person and mail domain (SMTP, IMAP, spam filter, DKIM, MTA-STS), wired as the server's mail provider

**Category:** mail  
**Tags:** `mail`, `smtp`, `imap`, `email`, `stalwart`  
**Website:** <https://stalw.art/>  
**Source:** <https://github.com/stalwartlabs/stalwart>

## Authentication

| Property | Value |
|----------|-------|
| **Method** | `custom` |
| **SSO** | :x: No |
| **Group Access** | :x: |
| **Group Admin** | :x: |

!!! info "Auth Notes"
    A mail provider (contract §3.5, §19): installing it grants nothing. A full administrator wires it into the server's one mail slot (Settings -> Mail), and only then does the Hub publish host ports 25, 465, 587 and 993 onto its listeners, attach its adapter to the provider API network, route the MTA-STS / autoconfig / autodiscover hosts to it and hand it the mail certificate and its secrets. instances: single because of those host ports and the one mail slot. The mailbox population is the Hub's mail_users group, never this template's; mail passwords go through the provider API only (no person_secret here). Services: stalwart (Stalwart mail server, uid 2000, read-only, cap_drop ALL plus NET_BIND_SERVICE, which the image's binary carries as a file capability; listeners 10025 / 10465 / 10587 / 10993 behind the Hub's published ports), adapter (Portcullis' mailctl, uid 10010: the provider API, the well-known files, the spam rules, the checks and metrics; the only holder of Stalwart's API key), resolver (Unbound, a validating recursive resolver for the two), and two one-off jobs: adapter-bin copies the pinned mailctl into a volume, key-init prepares the key volume (it holds the API key alone), and bootstrap runs Stalwart in recovery mode inside its own container only (a random recovery password made in the job, a job-only session nonce), applies the base plan once per store (only on an empty store; a store with data but no marker fails closed), writes the API key (0640, group mailkey, in the key volume only the job and the adapter mount) and exits 0 only once the recovery login is refused. It runs as Stalwart's uid, adds only NET_BIND_SERVICE (the Stalwart binary's file capability; no other), is gated like the server, re-runs on every cold start (a recovery start that checks the API key, then a normal start; a lost key gets a new key only, the settings untouched) and does nothing while the server holds the store lock. Start gate: stalwart starts only when the Hub's slot files say so (.present, or the Hub's void mode with its session nonce); a raw compose up after a core restore stays stopped. A recovery-mode start outside the bootstrap job is refused. Networks: internal (no internet; pinned 172.31.255.2 / .3 / .4 in the fixed subnet 172.31.255.0/28: an existing network on that range stops the start) and egress (stalwart and the resolver only). Mail over IPv6 isn't supported. The dqs_key setting reaches the adapter as an environment variable (the adapter moves it to a file before mailctl starts), so it shows in the adapter container's configuration (docker inspect): a third-party lookup key, not a Portcullis credential. Updates: Stalwart is pinned; any change to this template (an image bump included) holds the wired provider until an admin re-confirms it on the instance's Mail tab.

## Mail provider

This template is a **mail provider** ([contracts §3.5](../guides/integration-contracts.md#35-mail-providers-the-mail-block-new-mail-provider)): installing it grants nothing. A full administrator wires one instance into the server's mail slot ([Mail operations → Wiring a provider](../operations/mail.md#wiring-a-provider)), and only that instance gets the slot's powers: the public ports, the provider API network, the mail certificate, the slot files and the well-known router.

| `mail:` field | Value |
|---------------|-------|
| `label` | Stalwart |
| `api_version` | `1` |
| `api` | `adapter` port `8080`: the provider API the Hub dials on `portcullis-mail-api` |
| `listeners` | `stalwart`: host port 25 → `10025`, 465 → `10465`, 587 → `10587`, 993 → `10993` (published by the Hub, IPv4 only) |
| `wellknown` | `adapter` port `8081`: MTA-STS, autoconfig and autodiscover |
| `metrics` | `adapter` port `9100` |
| `server_metrics` | `stalwart` port `9180`, path `/metrics/prometheus` |
| `tls` | `stalwart`, `adapter`, `bootstrap` |
| `gated` | `stalwart`, `adapter`, `bootstrap` |
| `sessions.restart` | `stalwart`: restarted after every removal and every revoked mail password |
| `export` | `adapter`: `mailctl export --former {former_id}` (`./portcullis mail export`) |

This page is normative for the `stalwart` template only
([contracts §19](../guides/integration-contracts.md#19-mail-provider-api-new-mail-provider)
is the provider-neutral part). The adapter is Portcullis' `mailctl`, built
from core's `mailctl/` and published as `ghcr.io/porelli/portcullis-mailctl`
(cosign-signed, pinned by digest here).

### Services

| Service | Image | Runs as | What it does |
|---------|-------|---------|--------------|
| `adapter-bin` (job) | mailctl | `10010:10010`, no network | Copies the pinned image's static `mailctl` into the `mailctl_bin` volume on every start, so the bootstrap job runs the same binary next to Stalwart |
| `key-init` (job) | mailctl | `10010:10010` + group 2010, no network | Makes the key volume `adapter_key` `2770 10010:2010`; refuses to go on when it holds anything but `api-key` |
| `bootstrap` (job) | Stalwart | `2000:2010` (primary group 2010, `mailkey`), `NET_BIND_SERVICE` only, the internal network only | The base plan and Stalwart's API key ([below](#the-bootstrap-job)). In `tls` and `gated`: the base plan reads the certificate and the slot's metrics secret |
| `stalwart` | `stalwartlabs/stalwart` (upstream, unmodified) | `2000:2000`, `NET_BIND_SERVICE` only | The mail server: SMTP 10025, submissions 10465, submission 10587, IMAPS 10993, management 8080 (the adapter only), metrics 9180. `mem_limit` 1g |
| `adapter` | mailctl | `10010:10010` + group 2010, no capability | The provider API (8080), the well-known pages (8081), the vendored spam rules (8082, internal only), metrics (9100), the checks. The only holder of Stalwart's API key besides the job. `mem_limit` 256m |
| `resolver` | `klutchell/unbound` | `101:102` (the image's) | A validating recursive resolver (from the root servers, DNSSEC with the image's trust anchor) on port 5353 for `stalwart` and the adapter. `mem_limit` 128m |

Every service has `cap_drop: [ALL]`, `no-new-privileges`, a read-only root
and an explicit `pids_limit`; none publishes a port or carries a Traefik
label (the Hub's override adds both for the wired instance). Stalwart's
binary carries `NET_BIND_SERVICE` as a file capability and can't be
executed without it in the bounding set, so `stalwart` and `bootstrap` add
that one capability back; Stalwart still binds only ports ≥ 8080.

**Networks.** `internal` (`internal: true`, fixed subnet `172.31.255.0/28`:
`stalwart` at `.2`, the adapter at `.3`, the resolver at `.4`, the bootstrap
job a dynamic address from `172.31.255.8/29`; an existing network on that
range stops the start) and `egress` (`stalwart` and the resolver only:
outbound delivery, DNS, the blocklists). The adapter has no egress. Mail
over IPv6 isn't supported.

**Volumes.** `data` (Stalwart's RocksDB store), `job_data` (the job's own
files, such as the last server image), `adapter_data` (mailctl's state
machines: DKIM, MTA-STS, DMARC, DANE, the spam rules' import),
`adapter_key` (the API key alone, `0640` group `mailkey` 2010, mounted only
by the job read-write and the adapter read-only) and `mailctl_bin`. The
store is in `data`, so a [backup](../operations/backups.md) of the instance
holds every mailbox and the DKIM keys.

### The start gate

`stalwart`, the adapter and the bootstrap job are `gated`: each checks the
slot files (`PORTCULLIS_MAIL_SLOT_DIR`) before its server starts
([contracts §19.4](../guides/integration-contracts.md#194-the-provider-environment-gate-and-obligations)).
`stalwart` and the job use the template's `gate/entrypoint.sh`
(`entrypoint.sh --check` runs only the check, for the job); the adapter
uses mailctl's own check. A start goes on only when `void-pending` is
absent and `.present` is exactly `portcullis-mail-gate`, or in the Hub's
void mode with its session nonce. Otherwise it stops before the server
opens the store, with one of:

- "the mail gate isn't readable: the slot's files are missing (is this instance wired?)" (an unwired instance, or a raw `up` after a core restore emptied the slot volume);
- "the mail gate is closed: .present isn't the gate sentinel";
- "the mail gate is closed: a void is owed and this isn't the Hub's void mode".

The adapter also refuses a slot mount that shows anything but the slot
files: "the mail slot mount shows "&lt;name&gt;": not the wired provider's
slot files (the mail_provider_slot volume's root)".

**Recovery mode** (Stalwart's one-time admin) starts only inside the
bootstrap job: the job writes a session nonce into its own tmpfs
(`/run/portcullis/bootstrap`, which no other service has) and passes the
same nonce to its server child. Any other recovery-mode start is refused
("a recovery-mode start outside the bootstrap job"). The job's normal
starts are let through by the job's mark in the same tmpfs. Every other
start takes the store lock first and waits up to 600 s while the job holds
it, so two processes never open the store at once. Forging either needs a
compose change, which is a template change: it [holds](../operations/mail.md#template-updates-hold)
the wired provider until an admin confirms it.

### The bootstrap job

The job runs before `stalwart` and the adapter
(`service_completed_successfully`), on every start of the instance:

1. The gate check (above): unwired, or a void owed outside the Hub's void
   mode, it exits 1 and nothing else starts.
2. The store lock. When it is busy, the server is running on this store (a
   later `up` re-runs the job): it says "bootstrap: the store is in use (the
   server is running): nothing to do" and exits 0.
3. **An unmarked store** gets the base plan only when it is empty (no
   account but mailctl's, no foreign domain); a store with data but no
   marker fails the job, and the adapter never starts. The plan runs with
   Stalwart in recovery mode as the job's own child, a recovery password
   made inside the job: the listeners, the caches cut to fit 1 GiB, the
   certificate files, no ACME and manual DNS and DKIM management on every
   domain, the resolver, the management access rule, the metrics login, the
   SMTP rules, the spam settings, the parking domain
   `portcullis-former.internal`, the role and account below and one API
   key, written `0640` group `mailkey` to the key volume. Then a normal
   start must refuse the recovery login, and only then is the store marked.
4. **A marked store** gets a recovery start that checks the key, then the
   normal start that must refuse the recovery login. The settings are never
   planned again (the adapter applies the Hub's document on every pass). A
   missing key gets a new key only. After a change of the Stalwart image
   the normal start also updates the role's permissions
   (`STALWART_UPDATE_ROLE_PERMISSIONS`); when the server was running during
   that `up`, the update waits for the next cold start.

The job exits 0 only once the recovery login is refused, and no container
keeps a recovery variable.

### Stalwart's API key and role

The key has the custom role **`portcullis-mailctl`**, on the account
`portcullis-mailctl@portcullis-former.internal` (a random password, never
kept): accounts, domains, DKIM signatures, mail passwords (app passwords),
lists, the queue (read), DMARC and TLS reports (read), the spam settings,
rules and lookups, the DNSBL servers, sender authentication, the outbound
and inbound throttles, the TLS strategies, the routes, the system and
security settings, the spam rules' import task and the reload actions, plus
exactly the permission sets it grants (a mail password's, the export's),
because Stalwart refuses to grant a permission the caller lacks. Never
`sysApiKey*`, `sysRole*`, JMAP, DAV, Sieve or POP3: the key can't widen
itself. `impersonate` plus creating app passwords already amounts to
mailbox access, so the key admits only the adapter's address (`allowedIps`
its `/32`).

**The management listener** answers only the adapter's pinned address on
`/jmap`, `/api` and `/.well-known/jmap` (and the metrics path on the
metrics listener), `404` otherwise. That rule fails open (Stalwart treats an
expression error as allow, and loopback bypasses it), so the real control is
the network: only this template's services are on `internal`, and core CI
checks that another address there gets `404`.

### Spam filter

Stalwart's built-in filter with the vendored rules
(`stalwartlabs/spam-filter` v3.0.4, sha256
`604cc4386b1574e95185d37cb9c194ac20d360cca3865960b6ed0edf70475562`), served by
the adapter on `172.31.255.3:8082` only, so the filter never downloads them.
The adapter imports them itself: it starts Stalwart's spam-filter
maintenance task with its own copy, checks that every vendored rule is
present, and only then records the import (check `x-spam_rules`); until then
it asks again every minute. After every import it turns the rules' external
phishing and domain lookups off again, and checks that they stay off every
minute for 30 minutes after a start or an import, then every 15 minutes
(check `x-external_lookups`).

The filter scores at DATA: at least the **Reject** score (15) is refused
with `550 5.7.1`, at least the **Junk** score (5) goes to Junk with
`X-Spam-*` headers (Settings → Mail sets both). It has the statistical
classifier, trained by moving messages into and out of Junk, and the DNS
blocklists through the template's resolver. Greylisting, the AI classifier,
Pyzor and DMARC report forwarding are off.

**GTUBE.** Stalwart v1.1.0 recognises the GTUBE test string only in the
**Subject**, not in the body. Send a message whose Subject is
`XJS*C4JDBQADN1.NSBN3*2IDNEN*GTUBE-STANDARD-ANTI-UBE-TEST-EMAIL*C.34X` from
another mail server: it is refused with `550 5.7.1` at DATA. If it is
accepted, the spam rules aren't imported yet (`x-spam_rules`).

**The Spamhaus DQS key** (setting `dqs_key`, below). Spamhaus's public
mirrors refuse queries from many cloud resolvers and from large volumes; a
refused query is a Warning of the `blocklist` check, never "ok". With a free
[Spamhaus DQS](https://www.spamhaus.com/free-trial/sign-up-for-a-free-data-query-service-account/)
key (8–64 letters and digits, read in lowercase) the filter and the
`blocklist` check query your key's zones instead. The key reaches the
adapter as the environment variable `STALWART_DQS_KEY`, which the adapter
moves into a `0600` file before mailctl starts, so it shows in the adapter
container's configuration (`docker inspect`): it is a third-party lookup
key, not a Portcullis credential. A changed key applies at the instance's
next restart.

### Provider checks

Besides the neutral catalog
([contracts §19.8](../guides/integration-contracts.md#198-checks-report-trust-spam-outbound-and-metrics)),
the adapter reports two checks of its own, shown by the doctor as
`mail_provider_check` (explain-only, never a one-click fix):

| Check | Title | Not ok when | Steps |
|-------|-------|-------------|-------|
| `x-spam_rules` | Spam filter rules | Problem: "Stalwart has no spam rules: the import hasn't run yet (the adapter retries every minute; the spam filter scores nothing meanwhile)", with the import's error | Check mailctl's log (the stalwart instance's adapter logs) for "spam rules"; restarting the stalwart instance asks for the import again. |
| `x-external_lookups` | Spam filter external lookups | Problem: "the spam rules' external lookups may be on and couldn't be turned off (the spam filter may contact outside feeds)", with the error; Info before the first check | Check mailctl's log (the stalwart instance's adapter logs) for "spam rules"; the adapter retries every minute. |

DMARC and TLS aggregate reports are display-only with this provider:
Stalwart v1.1.0 gives no DKIM result for report messages, so none is
authenticated, and `dmarc_reports` / `tlsrpt_reports` say "shown only, never
acted on".

### Updates

Stalwart, Unbound and the adapter are pinned by digest. Any change to this
template, an image bump included, changes the wired instance's block hash:
the Hub [holds](../operations/mail.md#template-updates-hold) the provider
until a full administrator confirms the update on the instance's Mail tab.
The confirmation voids no mail password (the same mailbox store).

## AI support

**No AI support:** A mail server reached only by mail clients and the Hub's provider API; mailboxes stay out of AI reach (surveyed 2026-11-17).

## Images

Pinned by version tag and digest; Dependabot proposes updates.

| Service | Image | Digest |
|---------|-------|--------|
| `adapter` | `ghcr.io/porelli/portcullis-mailctl:dev-mailprov-f1c5ef9` | `sha256:7e554e4edc24…` |
| `adapter-bin` | `ghcr.io/porelli/portcullis-mailctl:dev-mailprov-f1c5ef9` | `sha256:7e554e4edc24…` |
| `bootstrap` | `docker.io/stalwartlabs/stalwart:v1.1.0` | `sha256:f772aa6ef8cd…` |
| `key-init` | `ghcr.io/porelli/portcullis-mailctl:dev-mailprov-f1c5ef9` | `sha256:7e554e4edc24…` |
| `resolver` | `docker.io/klutchell/unbound:v1.26.2` | `sha256:50cbeb32b583…` |
| `stalwart` | `docker.io/stalwartlabs/stalwart:v1.1.0` | `sha256:f772aa6ef8cd…` |

## Settings

Options an admin sets in the Hub's [settings panel](../operations/hub.md#app-settings) (person-entered ones: each person, on [My apps](../operations/hub.md#my-apps)). **Scope** and **Applies** are explained in the [Manifest Reference](../guides/manifest-reference.md#settings).

| Setting | Type | Scope | Applies | Description |
|---------|------|-------|---------|-------------|
| **Spamhaus DQS key** | `secret` | instance | `restart` | Optional free Spamhaus Data Query Service key (8-64 letters and digits). Spamhaus refuses blocklist queries from large public resolvers; with a key the spam filter and the blocklist check use the DQS zones instead. |
