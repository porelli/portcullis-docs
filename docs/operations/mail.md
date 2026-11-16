# Mail Operations

Running the [mail server](../setup/mail.md) once it is on: the spam filter,
DKIM keys, the MTA-STS and DMARC policies, DANE, backups, former mailboxes,
testing and troubleshooting. The interfaces are in
[contracts §19](../guides/integration-contracts.md#19-mail-new-mail).

Three places show the state:

- **`./portcullis mail status`** on the server (`--json` for machines): the
  three services, the Hub's document ("the Hub's document: generation N,
  applied M"), the certificate, each domain's DKIM keys and stages, MTA-STS
  and DMARC, the queue, former accounts, every check that isn't ok, the daily
  timer and the client-address mode. It exits 1 on a problem. The same block
  is in `./portcullis status` ("Mail").
- **Settings → Mail** in the Hub ([Hub → Mail](hub.md#mail)).
- **The doctor** ([below](#troubleshooting)): every mail problem with its
  steps, and one-click fixes for the policy promotions.

mailctl runs its checks every 6 hours, and when you ask (the doctor's
re-check, `GET /api/mail/checks?refresh=1`).

## The daily timer

`portcullis-mail.timer` (installed by `./portcullis mail schedule --systemd`)
runs `./portcullis mail rotate` once a day:

1. renews the mail certificate when it expires within 30 days (and reloads
   Stalwart);
2. moves the DKIM, MTA-STS and TLSA state on (new keys, `pending` →
   `active` → `retiring` → `retired`, the rollover's switch);
3. writes the main domain's mail records through your DNS provider.

If the main domain isn't a mail domain (mail off for it, or the Hub hasn't sent its first document yet), the step says "The main domain isn't a mail domain (yet): nothing to rotate for it." and still succeeds.

Added domains don't wait for it: the Hub republishes their records within
about a minute of every change. Run `./portcullis mail rotate` by hand any
time; it is what the timer runs.

## Spam

Stalwart's built-in filter scores every incoming message with the vendored
rule set (mailctl imports it into Stalwart and checks that every rule is
there), a statistical classifier, DNS blocklists, SPF / DKIM / DMARC / ARC
results and sender reputation. Greylisting and the AI classifier are off.
There is no virus scanner; the risky-attachment rules are on.

### Thresholds

In **Settings → Mail**:

| Setting | Default | Effect |
|---------|---------|--------|
| **Junk at score** | 5 | A message scoring at least this goes to the person's Junk folder, with `X-Spam-*` headers saying why |
| **Reject at score** | 15 | A message scoring at least this is refused during the SMTP conversation (`550 5.7.1`): the sender gets the bounce, nobody here sees it |

Junk must stay below Reject (1 ≤ junk < reject ≤ 100). Raise Reject before
lowering it: a refused message is gone for good, a junked one is only
misfiled. Remote domains' DMARC `p=reject` is honoured at SMTP time.

### Junk training

The classifier learns from what people do: **moving a message into Junk**
trains it as spam, **moving one out of Junk** as wanted mail. Tell people to
move messages rather than delete them; a few dozen moves make a visible
difference.

### Allow and block lists

**Always accept** and **Always refuse** in Settings → Mail take one domain
(`example.org`) or address (`newsletter@example.net`) per line. A message
from an allowed sender counts as trusted (Stalwart's `TRUSTED_DOMAIN`, which
lowers its score) only when it passes DMARC, so a forged sender gains
nothing; a message from a blocked sender is tagged `BLOCKED_DOMAIN`, which
scores it for refusal.

### Blocklists and the Spamhaus DQS key

Spamhaus ZEN, SpamCop and Barracuda are on by default (switch each in
Settings → Mail). They are queried through `mail-resolver`, Portcullis' own
validating resolver. Spamhaus's free public mirrors refuse queries from many
cloud resolvers and large volumes; a refused query is a Warning, never "ok".
With a free [Spamhaus DQS](https://www.spamhaus.com/free-trial/sign-up-for-a-free-data-query-service-account/)
key, set `MAIL_SPAMHAUS_DQS_KEY` in `.env` (8–64 lowercase letters and
digits) and run `./portcullis up`: the queries then go to your key's zone.
Settings → Mail shows whether a key is set, never the key.

The same blocklists also judge **your own** address
([`mail_blocklisted`](#troubleshooting)). A Spamhaus PBL listing means a
residential range: send through a [relay](../setup/mail.md#sending-through-a-relay).

### Check the spam filter

Send a message whose Subject is the GTUBE test string
`XJS*C4JDBQADN1.NSBN3*2IDNEN*GTUBE-STANDARD-ANTI-UBE-TEST-EMAIL*C.34X` from
another mail server: Portcullis refuses it with `550 5.7.1`. Stalwart
recognises GTUBE only in the Subject, not in the body.

If it is accepted, the doctor shows why: `mail_spam_rules_missing` (the rules
aren't imported yet, so nothing is scored).

### No surprise connections

After every rules import mailctl turns off the rule set's four external
phishing and domain lookups, so the filter never contacts outside feeds. It
checks that they stay off every minute for 30 minutes after a start or an
import, then every 15 minutes; if one can't be turned off the doctor shows
`mail_external_lookups_on`.

## Sending limits

Each person may send to at most **300 recipients an hour** and **1000 a day**
(Settings → Mail, 1–100000). Messages over the limit wait in the queue
instead of going out, and the doctor shows `mail_rate_held` naming the
person, so a stolen mail password can't burn the server's reputation
unnoticed. Revoke the person's mail passwords if they didn't send it.

## DKIM rotation

Every mail domain signs with two keys at once, Ed25519 and RSA-2048, with
selectors `v1-ed25519-YYYYMMDD` and `v1-rsa-YYYYMMDD`. Each key goes through:

| Stage | Meaning |
|-------|---------|
| `pending` | Created; its TXT record is being published. Not used for signing yet |
| `active` | Both public resolvers (1.1.1.1 and 8.8.8.8) serve its exact record; mail is signed with it. The previous key becomes `retiring` at the same moment |
| `retiring` | Kept in DNS for 7 days, so mail signed with it still verifies |
| `retired` | Its TXT is removed; the key is destroyed 30 days later |

Keys rotate every `MAIL_DKIM_ROTATE` (180 days). Rotate now (after a
suspected leak, or to test):

```bash
./portcullis mail dkim rotate example.com
```

For an **added domain** the Hub publishes the new record within about a
minute. For the **main domain** it is published at the next
`./portcullis mail rotate` (the timer) or `./portcullis dns setup --only mail`.
A key `pending` for more than a day is `mail_dkim_stuck`. On a main domain
whose DNS provider Portcullis can't write, one key per algorithm is made at
bootstrap and never rotates (`mail_dkim_manual`): copy the records from
`./portcullis dns plan` by hand.

The private keys are made by mailctl, sent once to Stalwart and never kept
anywhere else; they are in the mail store, so they survive a restore.

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
published at all ([Setup → DNS](../setup/mail.md#dns)). A domain whose mail goes off without the usual drain still never jumps straight to off: an `enforce` policy goes back to `testing` for the last policy's `max_age`, then off.

**DMARC** (what receivers do with mail that fails SPF and DKIM):
`p=none` → `p=quarantine` → `p=reject`, each step offered as
`mail_dmarc_promote` after 14 clean days. A domain that had no mail before
Portcullis starts at `p=reject`. DMARC is never lowered automatically.

!!! note "Reports are shown, not trusted"
    DMARC and TLS aggregate reports (to `dmarc-reports@` and `tls-reports@`)
    are ordinary mail: anyone can send one. Portcullis would count a report
    only when its message passed DKIM aligned with its sender's domain, and
    reports never weaken a policy. Stalwart v1.1.0 gives no DKIM result for
    report messages, so **every report is display-only**: the failing
    sources show in `mail_dmarc_failures` ("shown only, never acted on") and
    the promotions follow the clock and the certificate check. Read the
    failing sources before you accept a promotion: a legitimate sender you
    forgot (a newsletter service, a printer) would then be refused.

## DANE and the TLSA rollover

**Outbound:** Stalwart verifies other domains' DANE records when it delivers,
as long as `mail-resolver` can validate DNSSEC from this host (it needs to
reach the root servers over UDP and TCP port 53). After 3 failed validations
in a row spanning at least 30 minutes, outbound DANE is switched off
(`mail_dane_off`; MTA-STS and STARTTLS still apply), and the first
successful check switches it back on.

**Inbound:** `_25._tcp.<MAIL_HOSTNAME>` carries `TLSA 3 1 1` with the mail
certificate key's SPKI hash, published only while the main zone's DNSSEC
state is `secure`. The key is reused across renewals, so the record is stable.
To change the key (after a suspected compromise, or on a schedule):

```bash
./portcullis mail rotate --next-key
```

1. A next key is created and **both** hashes are published.
2. After 2 × TTL + 1 day, the daily timer issues the certificate with the
   next key and reloads Stalwart.
3. After a further 2 × TTL the old hash is dropped.

Don't delete the mail volumes during a rollover; `mail_acme` holds the next
key (it is backed up).

## Backups and restores

`./portcullis backup` includes mail ([Backups](backups.md)): Stalwart's store
and configuration (`mail_data`, `mail_etc`), mailctl's state, the mail
certificate and its ACME account.

**Mail stops for the copy.** Stalwart's store has no online backup, so
`backup` stops `mail` while it archives `mail_data` and `mail_etc`, and
starts it again, also when the copy fails. The Hub stops for that time too
(it restarts `mail` after every revoke, which would tear the copy), and if
`mail` is running again when the copy ends anyway, the backup fails rather
than keep a torn copy. This is the one exception to
"backups never stop services". For that minute port 25 is closed; other
servers retry later (they keep trying for days), and mail clients reconnect.

**A restore voids every mail password.** A restored store contains the mail
passwords that existed at backup time, including ones revoked since. Before
mail serves anyone after a restore, every mail password is destroyed, and
people see "reset by a restore" on their Sign-in page and create new ones.
The order:

1. Before restoring the mail store, the restore writes a marker
   (`secrets/mail/gate/void-pending`).
2. While the marker exists, nothing starts mail normally: `restore`, `up`,
   `upgrade` and `mail enable` void first, and the mail container itself
   refuses to start without the void session.
3. The void runs in a short recovery session: `mail` with no published
   ports, only its internal network and no restart policy, bound to the
   host's current boot (a recovery container left by a killed command or a
   reboot is refused). The marker is removed only once it worked.

The container checks a sentinel in the same directory
(`secrets/mail/gate/.present`) before every normal start: if the directory
isn't readable it says "the mail gate isn't readable" and stays stopped, so
a broken mount can never hide a pending void. `./portcullis up` writes the
sentinel again.

If the void fails, mail and mailctl stay stopped while the rest of the stack
runs, `restore` exits 1 with "mail passwords could not be voided: mail stays
stopped (./portcullis mail enable to retry)", and `./portcullis status` says
the same. Fix the cause (mail's and mailctl's logs say why) and run
`./portcullis mail enable`. DKIM keys survive
the restore, so the DNS records stay valid.

## Mass removals

When more than half the mailboxes would disappear at once (people leaving
`mail_users`), mailctl refuses to remove them on its own: an LDAP outage
could look the same. Their mail passwords are revoked at once and they can't
sign in to mail, but their mailboxes stay until a **full administrator**
(`lldap_admin`) confirms, in Settings → Mail (**Confirm removal**) or with the
doctor's fix on `mail_mass_removal_pending`. If they shouldn't have left, add
them back to `mail_users` instead. Removals made by full administrators
themselves confirm automatically; a delegate's never do.

## Former mailboxes and mail export

A person who leaves `mail_users` (or is deleted) doesn't get their mail
bounced and doesn't lose it at once:

- their mail passwords are revoked, the account can't sign in, send or
  receive, and their addresses stop existing (`550 5.1.1`);
- the mailbox is parked as `former-<uuid>` for `MAIL_FORMER_RETENTION`
  (30 days), then deleted;
- someone coming back with the same LLDAP account (the same uuid) within
  that time gets their mailbox back; new mail passwords are needed.

A **new** person who reuses the username gets a fresh, empty mailbox, never
the old one.

Former accounts are listed by `./portcullis mail status` and in Settings →
Mail. To keep one's mail before it is deleted:

```bash
./portcullis mail export former-6f1c2a9e-3b4d-4e5f-8a7b-1c2d3e4f5a6b
# → backups/mail-export/former-…-<time>.mbox (mode 0600); --out FILE elsewhere
```

This is the only way anyone reads mailbox content, and only on the server:
never through the Hub or an AI. It opens the former account for a moment
with a one-hour, read-only credential and closes it again, also on error.

## Changing `MAIL_HOSTNAME`

`./portcullis mail enable --hostname mail2.example.com` (or a new
`MAIL_HOSTNAME` in `.env`, then `./portcullis up`) issues a certificate for
the new name; set the PTR to it at your provider and run
`./portcullis dns setup`. The CLI records every earlier name
(`secrets/mail/former-hostnames`), and only those recorded names are cleaned
up in DNS (the old HELO SPF and TLSA); a name Portcullis never used is never
touched.

## Turning mail off: what stays

`./portcullis mail disable` removes every mail domain's mail records, but
**leaves `MAIL_HOSTNAME`'s A record and its CAA pin** (a known limitation).
Delete them by hand at your DNS provider if you don't turn mail on again.

## One command at a time

`up`, `down`, `upgrade`, `restore`, `backup` and `mail enable`, `disable`,
`rotate` and `cert` take a lock (`.portcullis.lock` in the checkout), shared
with the backup and mail timers. A second one says "Waiting for another
./portcullis command (a backup or mail timer?) to finish...", waits up to
`PORTCULLIS_LOCK_WAIT` seconds (default 1800), then refuses.

## Testing your install

Portcullis never tests itself by sending to the internet. Test from your own
side:

**A signed test message.**

```bash
./portcullis mail test --to you@example.org
```

It sends from the first postmaster account (`<admin>@<primary domain>`),
signed with the primary domain's DKIM keys, and prints the Message-ID. Use a
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
| `spf` | The MX / SPF records, or `MAIL_HOSTNAME`'s A record (`./portcullis dns setup`); with a relay, `MAIL_RELAY_SPF_INCLUDE` |
| `dmarc` | Needs `dkim` or `spf` to pass **and** align with the From domain |
| `iprev` / reverse DNS | The PTR ([`mail_ptr_missing`](#troubleshooting)) |

Also check the message didn't land in spam, and reply to it: the reply tests
inbound port 25.

**Check the spam filter** with GTUBE in the Subject from another server
([above](#check-the-spam-filter)).

**An external tester.** Services such as mail-tester.com give you an
address to send to and score the result (DKIM, SPF, DMARC, reverse DNS,
blocklists, content); `./portcullis mail test --to <their address>`. Web
checkers for MTA-STS, TLS-RPT and DANE (for example the internet.nl mail
test) read your published records from outside.

## Troubleshooting

Every mail finding of the [doctor](hub.md#mail-checks), what it means and
what to do. None fires while mail is off; while mailctl can't be read the
Doctor tab says so and shows no mail findings.

| Kind | Severity | Means | What to do |
|------|----------|-------|------------|
| `mail_port25_blocked` | Problem (Info: "no outbound delivery yet: not known") | Every delivery of the last 24 h failed to connect to the receivers' port 25 | Ask the provider to open outbound 25 ([Hosting providers](../setup/mail.md#hosting-providers)), or set a relay |
| `mail_ptr_missing` | Problem | The server's IPv4 address has no reverse DNS, or its name doesn't resolve | Set the PTR to `MAIL_HOSTNAME` at your provider; the steps name Hetzner, DigitalOcean, AWS EC2, AWS Lightsail and OVH |
| `mail_ptr_mismatch` | Problem | The PTR's name resolves to another address | Point the PTR at `MAIL_HOSTNAME`, and `MAIL_HOSTNAME`'s A record at the address |
| `mail_ipv6_ptr` | Info | The IPv6 address's reverse DNS isn't right | Nothing: outbound mail uses IPv4 |
| `mail_blocklisted` | Problem (Warning: the lookup was refused) | The server's address is on Spamhaus, SpamCop or Barracuda; a refused lookup can't tell | Follow the list's delisting page; a PBL listing means use a relay; a refused lookup: set a [DQS key](#blocklists-and-the-spamhaus-dqs-key) |
| `mail_records_wrong` | Problem | A domain's mail records are missing or wrong, or its live DKIM key isn't the one mail signs with | Added domain: one-click fix (applies the `mail` set). Main domain: `./portcullis dns setup --only mail` |
| `mail_dkim_stuck` | Warning | A new DKIM key has waited over a day for both public resolvers to serve it | Check the record with `./portcullis dns plan` (main) or the DNS panel (added); a provider that rewrites long TXT records can cause it |
| `mail_dkim_manual` | Info | The main domain's provider can't be written: DKIM doesn't rotate | Copy the records from `./portcullis dns plan` |
| `mail_cert_expiring` | Warning (14 days), Problem (3 days, or the certificate isn't right) | The mail certificate is about to expire, or isn't the one served on 25 / 465 / 587 / 993 | `./portcullis mail cert`; check the timer |
| `mail_timer_missing` | Warning | The daily timer hasn't run for 36 h | `./portcullis mail schedule --systemd` and its install commands |
| `mail_dmarc_failures` | Warning | Aggregate reports of the last 7 days name senders failing SPF / DKIM or TLS | Read the sources: add a forgotten legitimate sender's service to your setup, or ignore forgeries (reports are display-only) |
| `mail_dmarc_promote` | Info | 14 clean days: DMARC can move one step stricter | One click (after reading the reports) |
| `mail_mtasts_enforce` | Info | 7 days of `testing` with a valid certificate: MTA-STS can enforce | One click |
| `mail_dane_off` | Problem | `mail-resolver` can't validate DNSSEC, so outbound DANE is off | Let the host reach the root servers on UDP and TCP port 53; it turns back on by itself |
| `mail_client_ip_rewritten` | Warning | Rootless Podman: SPF, iprev and the IP blocklists are off and DMARC never rejects | Expected under rootless Podman ([degraded mode](../setup/mail.md#rootless-podman)) |
| `mail_lan_only_unenforced` | Problem | LAN-only is on but can't be enforced (rewritten client addresses): mail passwords work from anywhere | `./portcullis mail enable --lan-only false` |
| `mail_rate_held` | Warning | A person's outgoing mail is held by the sending limit; or the Hub's restart of mail after a revoke failed ("mail sessions may still be open") | Check the person's mail; revoke their mail passwords if it wasn't them. For the restart: `./portcullis up` |
| `mail_mass_removal_pending` | Problem | More than half the mailboxes left at once: removal waits for a confirmation | [Mass removals](#mass-removals): confirm, or add the people back |
| `mail_sync_blocked` | Problem | The Hub sends the mail server nothing: it can't tell which mailboxes a refused update would remove | Confirm or resolve the pending removal (Settings → Mail), or put the people back in `mail_users` |
| `mail_hub_secret_invalid` | Problem | Mail is on but the Hub's mail secret is missing or shorter than 32 characters: no mail change reaches the server | `./portcullis up` (recreates the Hub with the secret) |
| `mail_spam_rules_missing` | Problem | The spam filter has no rules yet: nothing is scored, GTUBE passes | mailctl retries every minute; if it stays, read mailctl's log ("spam rules") and run `./portcullis up` |
| `mail_external_lookups_on` | Problem | The spam rules' external lookups may be on and couldn't be turned off | mailctl retries every minute; read its log ("external lookups") |

Other things to check:

- **Nobody's mail password works and `mail status` says "mail passwords from
  a restore are not voided yet"**: run `./portcullis mail enable`
  ([Backups and restores](#backups-and-restores)).
- **"mailctl has no document from the Hub"** in `mail status`: the Hub isn't
  reaching mailctl; its log says why, and `./portcullis up` restarts it.
- **A new person's mail password says "your mailbox isn't ready yet"**: new
  mailboxes are created up to a minute after someone joins `mail_users`.
- **A revoked password or a removed person** is refused by IMAP and SMTP
  within 8 seconds: the Hub restarts `mail` after every revoke to end open
  sessions, so mail clients reconnect briefly.
