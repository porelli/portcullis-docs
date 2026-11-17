# Mail Operations

Running the [mail server](../setup/mail.md) once the slot is open: wiring,
switching and unwiring a provider, the void of mail passwords, template
updates, DKIM keys, the MTA-STS and DMARC policies, DANE, backups, former
mailboxes, testing and troubleshooting. The interfaces are in
[contracts §19](../guides/integration-contracts.md#19-mail-provider-api-new-mail-provider);
what a particular mail server does inside (for Stalwart: its services, its
bootstrap, its spam rules) is on its app page, [Stalwart](../apps/stalwart.md).

Three places show the state:

- **`./portcullis mail status`** on the server (`--json` for machines): the
  wired provider (instance, label, version), a void owed or a hold, whether
  the provider is reachable, the Hub's document ("the Hub's document:
  generation N, applied M"), every provider check that isn't ok, the
  certificate, the TLSA state, the daily timer, the client-address mode and
  LAN-only. It exits 1 on a problem (the Hub not answering, nothing wired, a
  void owed, a hold, the provider unreachable, the certificate's expiry
  unknown, a Problem check). The same block is in `./portcullis status`
  ("Mail").
- **Settings → Mail** and the provider instance's **Mail** tab in the Hub
  ([Hub → Mail](hub.md#mail)).
- **The doctor** ([below](#troubleshooting)): every mail problem with its
  steps, and one-click fixes for the policy promotions.

The provider runs its checks every 6 hours, and when you ask (the doctor's
re-check, `GET /api/mail/checks?refresh=1`).

## The slot and the provider

Core and the Hub own the **mail slot**; the **provider** is one app
instance plugged into it. At most one instance is wired at a time, and
installing a mail template never wires it.

| The slot (core and the Hub) | The wired provider (the app) |
|-----------------------------|------------------------------|
| `PORTCULLIS_MAIL=on`, `MAIL_HOSTNAME`, LAN-only, the CLI | The mail server, its spam filter, the mailboxes and DKIM keys, in its own volumes |
| The mail certificate (`mail-cert`), the TLSA record and the HELO SPF | Serves the certificate on 25, 465, 587 and 993 |
| The provider API network `portcullis-mail-api` and the metrics network | Its adapter answers the Hub on the API network |
| The slot volumes: `mail_slot` (metrics discovery) and `mail_provider_slot` (the provider's secrets and gate files) | Reads the gate files and refuses to start without them |
| The Hub: the mailboxes, domains, aliases, lists and settings it sends; the DNS it writes after checking it; the mail passwords' rows | Applies the Hub's document; proposes each domain's DNS records |

The provider never gets DNS credentials, the wildcard certificate's key,
LLDAP or Keycloak credentials, engine access or the Hub's data. Its powers
are exactly what the Hub's override gives the wired instance, and they go
when it is unwired.

## Wiring a provider

`./portcullis mail enable` wires the default `stalwart` app for you. To wire
another installed mail app (the Marketplace marks them "Mail server"), open
its **Mail** tab in the Hub (`#apps/<id>/mail`, or the list on Settings →
Mail). The tab shows the warning, what the provider reports (name, version,
checks), and why wiring is refused right now, if it is. Type the instance
id, click **Make this the mail server**, and sign in again with your
security key in the small window.

Wiring is refused, in this order, for:

1. an AI or MCP caller, or anyone but a full administrator (`lldap_admin`): `403`;
2. a missing or stale fresh sign-in: "a fresh sign-in is required";
3. a wrong typed id: "type the instance id to confirm";
4. a closed slot: "mail is off: run ./portcullis mail enable on the host";
5. another wired instance: "&lt;id&gt; is this server's mail provider: switch instead";
6. Kubernetes; rootless Podman with `ip_unprivileged_port_start` above 25;
   another instance that publishes 25, 465, 587 or 993;
7. a template whose `mail:` block doesn't validate, or whose API version the
   Hub doesn't speak;
8. a stop still owed to the previous provider: "the previous provider's stop
   is still owed (&lt;id&gt;): it is retried; wire again once it is down".

The CLI's typed instance id stands in for the fresh sign-in (it runs on
the server's host socket). Every wiring is audited (`mail.provider_wired`,
with the instance, the template, its source and commit, the block hash and
who did it).

The Hub then runs the wiring in the background, each step saved before the
next, so a Hub restart resumes it: it records the provider and the owed
void; writes the provider's secrets and gate files; starts the instance in
**void mode** (no ports, no internet, no router); **voids every mail
password** and checks that none is left ([The void](#the-void)); starts the
instance normally (the ports, the networks, the well-known router); sends
the first document; and writes the domains' DNS. **Every wiring starts with
a void**, so a provider that arrives with credentials from a restore, an
older wiring or an imported store starts clean. People see "the mail server
changed on &lt;date&gt;: create a new mail password" on their Sign-in page.

A wiring can be stopped until its normal start begins; the instance is
then stopped, unwired.

## Template updates hold

The Hub fingerprints the wired template when it is wired (its `mail:`
block, its `compose.yml` and every file of the template directory). After
every source sync it compares again. On any change, an image bump included,
or when the template no longer validates, the provider is **held**:

- the running containers keep serving, and nothing of the changed template
  starts: no `up`, re-render or recreate;
- anything that would need an `up` meanwhile (enabling, a dead container,
  a Hub restart, an environment change) starts it in void mode instead;
- the mail routes answer as for an unreachable provider; revocations,
  removals and session resets still reach the running provider (if it
  can't take them, the Hub voids it);
- the doctor shows `mail_provider_refused`: "the mail provider's template
  changed: review and confirm on its Mail tab".

Review the change, then confirm on the instance's Mail tab (**Confirm the
updated template**): the same guards as a wiring, and the extra warning
"The template changed since you wired it. Confirming keeps every mail
password and mailbox: the updated app gets them as they are." A
confirmation voids no mail password (it is the same mailbox store). A sync
of other templates changes nothing.

## Switching providers

Settings → Mail → **Switch…** moves the slot to another installed mail
app. Type the new instance's id and the phrase "&lt;n&gt; mailboxes start
empty" (n is the number of mailboxes now), then sign in again. The same MX,
the same certificate and the same TLSA serve both: a switch is a cutover.

- The old provider is unwired (no drain) and **stopped with its data**; the
  switch moves no mail, so people's mailboxes on the new provider start
  empty.
- The new one is wired as above: every mail password is voided.
- Each domain's records are replaced domain by domain; the old DKIM records
  stay for **7 days** so mail signed just before the switch still verifies;
  MTA-STS starts again at `testing`; DMARC never drops below the domain's
  floor.
- Audited `mail.provider_switched` (`from`, `to`). A switch can be stopped
  only before the old provider is unwired.

## Unwiring

**Unwire…** (Settings → Mail or the Mail tab), or `./portcullis mail disable`:

- **draining** (the default): every mail domain drains (MTA-STS `mode: none`
  for its `max_age`, up to 7 days, then the MX goes); the provider keeps
  serving until every domain is off, then the Hub finishes the unwire;
- **at once** (untick *drain first*, or `--force`): every domain's `mail`
  set goes now, and senders with a cached MTA-STS policy may bounce mail.

Then every active mail password is voided ("the mail server changed"), the
provider's secrets and gate files are removed, so the gate closes, and the
instance is **stopped**. It stays installed with its data. Nothing waits for
the provider: each call to it is bounded at 30 s, and the gate closes
whatever it answers. Audited `mail.provider_unwired`. The wired instance
can't be deleted: "unwire it first (Settings → Mail)".

## The void

A void destroys every mail password of every account. One is owed after
every wiring and every restore. While it is owed:

- the provider runs in **void mode** only: no published port, no router, no
  metrics, every network of the template internal, and a session nonce in
  its environment that the gate files must match;
- the Hub refuses to create mail passwords (`503`), and the mail routes
  answer "mail isn't running right now".

The Hub asks the provider to void, then lists every account's credentials
itself and revokes anything left; only an empty second listing is a void.
Then it writes the gate's sentinel and starts the provider normally. If the
void fails, the provider stays stopped, the doctor shows `mail_void_pending`,
and the Hub retries every **5 minutes**; **Retry** on the Mail tab or
Settings → Mail retries at once. **Retry** is also the fix when the wired
provider's API secret is missing or too short (Settings → Mail says "Mail
can't be managed: the Hub's secret for the wired mail provider is missing or
too short"): it owes a void, and the void writes a fresh secret. After
`./portcullis mail restore-hold clear`, Retry is what starts the provider
again, through a void.

## The daily timer

`portcullis-mail.timer` (installed by `./portcullis mail schedule --systemd`)
runs `./portcullis mail rotate` once a day:

1. renews the mail certificate when it expires within 30 days;
2. moves the TLSA rollover on when a step is due ([below](#dane-and-the-tlsa-rollover));
3. gives the Hub the certificate's keys, and the Hub reloads the provider
   (only while a provider is serving);
4. writes the main domain's mail records through your DNS provider. With
   nothing wired they are withdrawn instead ("No mail provider is wired: the
   main domain's mail records are withdrawn.").

The provider rotates DKIM keys on its own schedule; added domains don't wait
for the timer: the Hub republishes their records within about a minute of
every change. Run `./portcullis mail rotate` by hand any time; it is what
the timer runs.

## Spam

The provider's spam filter scores every incoming message; how it does that
(rules, classifier, blocklists) is the provider's, on its app page
([Stalwart → Spam filter](../apps/stalwart.md#spam-filter)). The settings
are the Hub's, in **Settings → Mail**, and every provider must honour them.

### Thresholds

| Setting | Default | Effect |
|---------|---------|--------|
| **Junk at score** | 5 | A message scoring at least this goes to the person's Junk folder, with `X-Spam-*` headers saying why |
| **Reject at score** | 15 | A message scoring at least this is refused during the SMTP conversation (`550 5.7.1`): the sender gets the bounce, nobody here sees it |

Junk must stay below Reject (1 ≤ junk < reject ≤ 100). Raise Reject before
lowering it: a refused message is gone for good, a junked one is only
misfiled. Remote domains' DMARC `p=reject` is honoured at SMTP time.

### Junk training

Tell people to **move** messages into Junk and out of it rather than delete
them: a provider with a statistical classifier (Stalwart's) learns from
those moves.

### Allow and block lists

**Always accept** and **Always refuse** in Settings → Mail take one domain
(`example.org`) or address (`newsletter@example.net`) per line. An allowed
sender is trusted only when the message passes DMARC, so a forged sender
gains nothing; a blocked sender's mail is scored for refusal.

### Blocklists

Spamhaus ZEN, SpamCop and Barracuda are switched on or off in Settings →
Mail. Spamhaus's free public mirrors refuse queries from many cloud
resolvers and from large volumes; a refused query is a Warning, never "ok".
Stalwart can use a Spamhaus DQS key instead (its
[`dqs_key` setting](../apps/stalwart.md#spam-filter)).

The same blocklists also judge **your own** address
([`mail_blocklisted`](#troubleshooting)). A Spamhaus PBL listing means a
residential range: send through a [relay](../setup/mail.md#sending-through-a-relay).

## Sending limits

Each person may send to at most **300 recipients an hour** and **1000 a day**
(Settings → Mail, 1–100000). Messages over the limit wait in the queue
instead of going out, and the doctor shows `mail_rate_held` naming the
person, so a stolen mail password can't burn the server's reputation
unnoticed. Revoke the person's mail passwords if they didn't send it.

## DKIM rotation

Every mail domain signs with keys the provider makes and keeps (they never
leave it); Stalwart signs with two at once, Ed25519 and RSA-2048. Each key
goes through:

| Stage | Meaning |
|-------|---------|
| `pending` | Created; its TXT record is being published. Not used for signing yet |
| `active` | Both public resolvers (1.1.1.1 and 8.8.8.8) serve its exact record; mail is signed with it. The previous key becomes `retiring` at the same moment |
| `retiring` | Kept in DNS for 7 days, so mail signed with it still verifies |
| `retired` | Its TXT is removed; the key is destroyed 30 days later |

Keys rotate every `dkim_rotate` (a Hub setting, default 180 days). Rotate
now (after a suspected leak, or to test):

```bash
./portcullis mail dkim rotate example.com
```

For an **added domain** the Hub publishes the new record within about a
minute. For the **main domain** it is published at the next
`./portcullis mail rotate` (the timer) or `./portcullis dns setup --only mail`.
A key `pending` for more than a day is `mail_dkim_stuck`. On a main domain
whose DNS provider Portcullis can't write, one key per algorithm is made and
never rotates (`mail_dkim_manual`): copy the records from
`./portcullis dns plan` by hand.

The CLI records every DKIM name it wrote for the main domain
(`secrets/mail/dkim-written`, append-only), and removes a stale DKIM record
only when it is listed there: another sender's selector at the same domain
stays.

## MTA-STS and DMARC promotion

Both policies start soft and get stricter only when an administrator accepts
the step. The doctor offers each step as a one-click fix (Info) when its
conditions hold; nothing is ever promoted by itself.

**MTA-STS** (senders must use TLS to reach you):

| Mode | `max_age` | When |
|------|-----------|------|
| `testing` | 1 day | From the start: senders report problems but deliver anyway |
| `enforce` | 7 days | After you accept `mail_mtasts_enforce`: offered after 7 days of `testing` with the certificate check passing |

`enforce` goes back to `testing` only when the server's own certificate check
fails definitely twice, at least 15 minutes apart (an unreachable port or a
timeout doesn't count). While the core pages are VPN-only, no policy is
published at all ([Setup → DNS](../setup/mail.md#dns)). A domain whose mail
goes off without the usual drain still never jumps straight to off: an
`enforce` policy goes back to `testing` for the last policy's `max_age`, then
off. Every 6 hours the Hub also fetches each domain's published policy and
reports `mail_records_wrong` unless it names exactly `MAIL_HOSTNAME`.

**DMARC** (what receivers do with mail that fails SPF and DKIM):
`p=none` → `p=quarantine` → `p=reject`, each step offered as
`mail_dmarc_promote` after 14 clean days. A domain that had no mail before
Portcullis starts at `p=reject`. DMARC is never lowered, and the Hub refuses
any record set below the domain's floor, a switch's included.

!!! note "Reports are shown, not trusted"
    DMARC and TLS aggregate reports (to `dmarc-reports@` and `tls-reports@`)
    are ordinary mail: anyone can send one. A report counts only when its
    message passed DKIM aligned with its sender's domain, and reports never
    weaken a policy. A provider that can't authenticate them (Stalwart
    v1.1.0) shows them only: the failing sources show in
    `mail_dmarc_failures` ("shown only, never acted on") and the promotions
    follow the clock and the certificate check. Read the failing sources
    before you accept a promotion: a legitimate sender you forgot (a
    newsletter service, a printer) would then be refused.

## DANE and the TLSA rollover

**Outbound:** the provider verifies other domains' DANE records when it
delivers, as long as its resolver can validate DNSSEC from this host (it
needs to reach the root servers over UDP and TCP port 53). After 3 failed
validations in a row spanning at least 30 minutes, outbound DANE is switched
off (`mail_dane_off`; MTA-STS and STARTTLS still apply), and the first
successful check switches it back on.

**Inbound:** `_25._tcp.<MAIL_HOSTNAME>` carries `TLSA 3 1 1` with the mail
certificate key's SPKI hash, published only while the main zone's DNSSEC
state is `secure`. It is core's, not the provider's: a switch changes
nothing. The key is reused across renewals, so the record is stable. To
change the key (after a suspected compromise, or on a schedule):

```bash
./portcullis mail rotate --next-key
```

1. A next key is created and **both** hashes are published.
2. After 2 × TTL + 1 day, and only once the next key's TLSA has been seen on
   every authoritative server of the zone for at least the TTL, the daily
   timer issues the certificate with the next key; the Hub reloads the
   provider. With a DNS provider Portcullis can't write, the switch waits
   until you have published the record yourself.
3. After a further 2 × TTL the old hash is dropped, once the provider has
   confirmed it serves the key that stays (with no provider serving, both
   hashes stay).

`./portcullis mail status` shows the rollover's phase ("TLSA: …, 2 key(s)
(switch due at the next mail rotate)"). Don't delete the mail volumes
during a rollover; `mail_acme` holds the next key (it is backed up).

## Backups and restores

`./portcullis backup` includes mail ([Backups](backups.md)): the provider's
store through a **Hub instance backup** of the wired instance (reason
`core`), which stops the instance for the copy and starts it again, and the
mail certificate and its ACME account (`mail_tls`, `mail_acme`) online. The
instance archive is inside `hub_data`, so one `./portcullis backup` holds the
mailboxes; `backup verify` checks that it is there. For the copy port 25 is
closed; other servers retry later (they keep trying for days), and mail
clients reconnect. While a void is owed or the provider is held, the
instance comes back in void mode (or stays stopped), never normal.

**A restore voids every mail password.** A restored store contains the mail
passwords that existed at backup time, including ones revoked since. Before
the provider serves anyone after a restore, every mail password is
destroyed, and people see "reset by a restore" on their Sign-in page and
create new ones.

- **An instance restore** of the provider (from the Hub) owes a void before
  the volumes are replaced.
- **A core restore** (`./portcullis restore`) empties `hub_secrets` and the
  provider's slot volume, so the gate closes (a raw start of the provider
  fails closed). It writes a hold into `hub_data`
  (`mail-restore-pending`, the archive's name) before the Hub starts, so the
  Hub keeps the provider stopped; then it asks the Hub to restore the
  provider from the archive the backup names (`hub mail restore`, waited
  for), and only then starts the rest of the stack. The Hub voids every mail
  password before the provider serves again.

If the provider's restore fails, the hold stays, the restore still finishes
the rest of the stack and ends with "the mail provider couldn't be restored
from its archive (its mailboxes are NOT back yet; the Hub holds it): fix the
cause and run ./portcullis restore again, or lift the hold with
./portcullis mail restore-hold clear (the provider then starts on what its
volumes hold)". Lifting the hold never starts the provider by itself, and
you must type `clear` to confirm (`--yes` for scripts); it is logged. DKIM
keys survive a restore of the store, so the DNS records stay valid.

## Mass removals

When more than half the mailboxes would disappear at once (people leaving
`mail_users`), the Hub refuses to send that removal on its own: an LDAP
outage could look the same (the provider refuses such a document too).
Their mail passwords are revoked at once and they can't sign in to mail, but
their mailboxes stay until a **full administrator** (`lldap_admin`)
confirms, in Settings → Mail (**Confirm removal**) or with the doctor's fix
on `mail_mass_removal_pending`. If they shouldn't have left, add them back
to `mail_users` instead. Delegates' removals never confirm it.

## Former mailboxes and mail export

A person who leaves `mail_users` (or is deleted) doesn't get their mail
bounced and doesn't lose it at once:

- their mail passwords are revoked, the account can't sign in, send or
  receive, and their addresses stop existing (`550 5.1.1`);
- the mailbox is parked as `former-<uuid>` for `former_retention` (a Hub
  setting, default 30 days), then deleted;
- someone coming back with the same LLDAP account (the same uuid) within
  that time gets their mailbox back; new mail passwords are needed.

A **new** person who reuses the username gets a fresh, empty mailbox, never
the old one.

Former accounts are listed in Settings → Mail (**Former accounts**: the
username, the id and since when). To keep one's mail before it is deleted:

```bash
./portcullis mail export former-6f1c2a9e-3b4d-4e5f-8a7b-1c2d3e4f5a6b
# → backups/mail-export/former-…-<time>.mbox (mode 0600); --out FILE elsewhere
```

It runs the provider's export command (from its `mail:` block) inside the
provider's container; a provider without one says "the mail provider has no
export". This is the only way anyone reads mailbox content, and only on the
server: never through the Hub or an AI. The provider must refuse anything
but a former account and clean up whatever access it granted itself for the
export, also on error.

## Changing `MAIL_HOSTNAME`

`./portcullis mail enable --hostname mail2.example.com` (or a new
`MAIL_HOSTNAME` in `.env`, then `./portcullis up`) issues a certificate for
the new name; set the PTR to it at your provider and run
`./portcullis dns setup`. The CLI records every earlier name
(`secrets/mail/former-hostnames`), and only those recorded names are cleaned
up in DNS (the old HELO SPF and TLSA); a name Portcullis never used is never
touched.

## Turning mail off: what stays

`./portcullis mail disable` unwires the provider and removes every mail
domain's mail records, but **leaves `MAIL_HOSTNAME`'s A record and its CAA
pin** (a known limitation) and the provider instance with its data. Delete
the records by hand at your DNS provider, and the instance from the Hub, if
you don't turn mail on again. The daily timer stays installed too:
`systemctl disable --now portcullis-mail.timer` (`--user` under rootless
Podman), as `mail disable` reminds you.

## One command at a time

`up`, `down`, `upgrade`, `restore`, `backup` and `mail enable`, `disable`,
`rotate` and `cert` take a lock (`.portcullis.lock` in the checkout), shared
with the backup and mail timers. A second one says "Waiting for another
./portcullis command (a backup or mail timer?) to finish...", waits up to
`PORTCULLIS_LOCK_WAIT` seconds (default 1800), then refuses. A mail command
that starts a Hub operation (wiring, unwiring, a restore) waits for the
operation to end (up to `MAIL_OP_WAIT` seconds, default 1800) and succeeds
only when it did.

## Testing your install

Portcullis never tests itself by sending to the internet. Test from your own
side:

**A signed test message.**

```bash
./portcullis mail test --to you@example.org
```

It sends from the first postmaster account (`<admin>@<primary domain>`),
signed with the primary domain's DKIM keys, and prints the queue id. Use a
mailbox at a large provider you can read.

**Read `Authentication-Results`.** Open the received message's headers
("Show original" in Gmail, "View message source" in Outlook, "View → Message
Source" in Thunderbird) and find the receiver's line:

```
Authentication-Results: mx.example.org;
       dkim=pass header.d=example.com header.s=v1-ed25519-20261115;
       dkim=pass header.d=example.com header.s=v1-rsa-20261115;
       spf=pass smtp.mailfrom=admin@example.com;
       dmarc=pass header.from=example.com
```

| Result | If it isn't `pass` |
|--------|--------------------|
| `dkim` | The DKIM record isn't published or differs: `mail_records_wrong`, `mail_dkim_stuck`; for the main domain `./portcullis dns setup --only mail` |
| `spf` | The MX / SPF records, or `MAIL_HOSTNAME`'s A record (`./portcullis dns setup`); with a relay, its SPF include |
| `dmarc` | Needs `dkim` or `spf` to pass **and** align with the From domain |
| `iprev` / reverse DNS | The PTR ([`mail_ptr_missing`](#troubleshooting)) |

Also check the message didn't land in spam, and reply to it: the reply tests
inbound port 25.

**Check the spam filter** with your provider's test (Stalwart: GTUBE in the
Subject, [Stalwart → Spam filter](../apps/stalwart.md#spam-filter)).

**An external tester.** Services such as mail-tester.com give you an
address to send to and score the result (DKIM, SPF, DMARC, reverse DNS,
blocklists, content); `./portcullis mail test --to <their address>`. Web
checkers for MTA-STS, TLS-RPT and DANE (for example the internet.nl mail
test) read your published records from outside.

## Troubleshooting

Every mail finding of the [doctor](hub.md#mail-checks), what it means and
what to do. None fires while mail is off. While the wired provider can't be
read, its checks don't fire and the Doctor tab says so; the findings the Hub
judges on its own (the slot, the void, the hold, the timer) still do.

| Kind | Severity | Means | What to do |
|------|----------|-------|------------|
| `mail_provider_missing` | Warning | The slot is open and no app is the mail provider: nobody has a mailbox and no mail is sent or received | Wire a mail server (Settings → Mail) or run `./portcullis mail disable` |
| `mail_provider_unreachable` | Problem | The wired provider hasn't answered (or kept reporting it isn't ready) for 10 minutes: no mailbox, address or mail password changes reach it | Check the instance on its Mail tab and its logs |
| `mail_void_pending` | Problem | A void of every mail password is owed and its last attempt failed: the provider stays stopped | Retry on the Mail tab, or look at the provider's logs ([The void](#the-void)) |
| `mail_provider_refused` | Problem | The wired template changed, no longer validates or speaks an unknown API version: the provider is held | Review the change and confirm on the instance's Mail tab ([Template updates hold](#template-updates-hold)) |
| `mail_provider_check` | Up to Problem | A check of the provider's own (`x-…`), with its title, detail and steps as plain text | Follow its steps (Stalwart's: [Provider checks](../apps/stalwart.md#provider-checks)) |
| `mail_port25_blocked` | Problem (Info: "no outbound delivery yet: not known") | Every delivery of the last 24 h failed to connect to the receivers' port 25 | Ask the provider to open outbound 25 ([Hosting providers](../setup/mail.md#hosting-providers)), or set a relay |
| `mail_ptr_missing` | Problem | The server's IPv4 address has no reverse DNS, or its name doesn't resolve | Set the PTR to `MAIL_HOSTNAME` at your provider; the steps name Hetzner, DigitalOcean, AWS EC2, AWS Lightsail and OVH |
| `mail_ptr_mismatch` | Problem | The PTR's name resolves to another address | Point the PTR at `MAIL_HOSTNAME`, and `MAIL_HOSTNAME`'s A record at the address |
| `mail_ipv6_ptr` | Info | The IPv6 address's reverse DNS isn't right | Nothing: outbound mail uses IPv4 |
| `mail_blocklisted` | Problem (Warning: the lookup was refused) | The server's address is on a blocklist; a refused lookup can't tell | Follow the list's delisting page; a PBL listing means use a relay; a refused lookup: a DQS key, if your provider takes one |
| `mail_records_wrong` | Problem | A domain's mail records are missing or wrong, its live DKIM key isn't the one mail signs with, the provider proposed records the rules refuse (the rule's text), the published MTA-STS policy doesn't name `MAIL_HOSTNAME`, or a domain still waits for its new set after a switch | Added domain: one-click fix (applies the `mail` set). Main domain: `./portcullis dns setup --only mail` |
| `mail_dkim_stuck` | Warning | A new DKIM key has waited over a day for both public resolvers to serve it | Check the record with `./portcullis dns plan` (main) or the DNS panel (added); a provider that rewrites long TXT records can cause it |
| `mail_dkim_manual` | Info | The main domain's provider can't be written: DKIM doesn't rotate | Copy the records from `./portcullis dns plan` |
| `mail_cert_expiring` | Warning (14 days), Problem (3 days, or the certificate isn't right) | The mail certificate is about to expire, or isn't the one served on 25 / 465 / 587 / 993 | `./portcullis mail cert`; check the timer |
| `mail_timer_missing` | Warning | The daily timer hasn't run for 36 h | `./portcullis mail schedule --systemd` and its install commands |
| `mail_dmarc_failures` | Warning | Aggregate reports of the last 7 days name senders failing SPF / DKIM or TLS | Read the sources: add a forgotten legitimate sender's service to your setup, or ignore forgeries |
| `mail_dmarc_promote` | Info | 14 clean days: DMARC can move one step stricter | One click (after reading the reports) |
| `mail_mtasts_enforce` | Info | 7 days of `testing` with a valid certificate: MTA-STS can enforce | One click |
| `mail_dane_off` | Problem | The provider's resolver can't validate DNSSEC, so outbound DANE is off | Let the host reach the root servers on UDP and TCP port 53; it turns back on by itself |
| `mail_client_ip_rewritten` | Warning | Rootless Podman: SPF, iprev and the IP blocklists are off and DMARC never rejects | Expected under rootless Podman ([degraded mode](../setup/mail.md#rootless-podman)) |
| `mail_lan_only_unenforced` | Problem | LAN-only is on but can't be enforced (rewritten client addresses), or a mail password reached beyond the Local networks and the Hub revoked it | `./portcullis mail enable --lan-only false` under rootless Podman; otherwise check the provider |
| `mail_rate_held` | Warning | A person's outgoing mail is held by the sending limit; or the Hub's restart of the provider after a revoke failed ("mail sessions may still be open") | Check the person's mail; revoke their mail passwords if it wasn't them. For the restart: restart the provider instance |
| `mail_mass_removal_pending` | Problem | More than half the mailboxes left at once: removal waits for a confirmation | [Mass removals](#mass-removals): confirm, or add the people back |
| `mail_sync_blocked` | Problem | The Hub sends the provider nothing: it can't tell which mailboxes a refused update would remove | Confirm or resolve the pending removal (Settings → Mail), or put the people back in `mail_users` |

Other things to check:

- **Nobody's mail password works and the Mail tab shows a void owed**: the
  void hasn't succeeded yet ([The void](#the-void)).
- **"the Hub's document" isn't applied** in `mail status`: the provider
  isn't taking the Hub's document; its logs say why. The Hub sends no
  document at all until the mail certificate's key has been posted once
  (`./portcullis mail rotate` posts it, as does `mail enable` once the
  provider serves).
- **A new person's mail password says "your mailbox isn't ready yet: try
  again in a minute"**: new mailboxes are created up to a minute after
  someone joins `mail_users`.
- **A revoked password or a removed person** is refused by IMAP and SMTP
  within 8 seconds: the Hub restarts the provider's session service after
  every revoke to end open sessions, so mail clients reconnect briefly.
