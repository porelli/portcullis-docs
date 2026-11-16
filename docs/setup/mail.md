# Mail Server

Portcullis can run a full mail server for the main domain and for every
[added domain](dns.md#adding-extra-domains) you turn mail on for: sending and
receiving, a built-in spam filter, SPF, DKIM and DMARC that pass and align,
MTA-STS, TLS reports, DANE when the main zone is signed, your LLDAP people as
mailboxes, aliases and group lists, and one mail password per device.

It is [Stalwart](https://stalw.art) (the upstream image, unmodified and
pinned) plus `mailctl`, a small Portcullis service that is the only thing
allowed to configure it. Mail is part of core (the compose profile `mail`),
not an app from the marketplace. Day-to-day work (spam, DKIM, policies,
backups, troubleshooting) is on [Mail operations](../operations/mail.md); the
interfaces are in
[contracts §19](../guides/integration-contracts.md#19-mail-new-mail).

## Before you start

Mail is less forgiving than the web: receivers judge your server by its
address, its name and its DNS before they read a single message. Check these
first.

| Need | Why |
|------|-----|
| **A static public IPv4 address** | Your MX, SPF and reverse DNS all name it. A dynamic address breaks all three whenever it changes |
| **Inbound TCP 25** open to the internet | Other servers deliver to you on port 25 only. Open 465, 587 and 993 too if people read mail from outside your LAN |
| **Outbound TCP 25** allowed by the provider | You deliver to other servers on port 25. Many clouds block it by default; without it, use a [relay](#sending-through-a-relay) |
| **Reverse DNS (PTR)** of the address set to `MAIL_HOSTNAME` (default `mail.<domain>`) | Large receivers refuse or junk mail from an address whose PTR doesn't resolve back to it. Only the address's owner (your provider) can set it |
| **A DNS provider Portcullis can write** | The mail certificate is issued through DNS-01, and DKIM keys rotate by rewriting TXT records. Cloudflare, Porkbun, Route 53, DigitalOcean and Hetzner work; other lego providers don't (`mail enable` refuses) |
| **Docker or rootless Podman** | Mail isn't available on [Kubernetes](#kubernetes) yet |
| **About 1.5 GiB of free memory** | Stalwart is capped at 1 GiB, mailctl at 256 MiB, the resolver at 128 MiB |

!!! note "IPv4 only"
    IPv6 for mail isn't supported yet: the mail ports are published on IPv4
    only and outbound mail uses IPv4. A `MAIL_IPV6` line in `.env` makes
    `mail enable`, `up` and `upgrade` stop with "MAIL_IPV6 isn't supported
    yet: remove it from .env". (An IPv6 port in front of the IPv4-only mail
    network would hide the client's address, which LAN-only, SPF and the
    blocklists all need.)

### Hosting providers

Port 25 and reverse DNS are the two things you usually have to ask for. The
doctor gives the same steps when it finds a problem
([`mail_port25_blocked`, `mail_ptr_missing`](../operations/mail.md#troubleshooting)).

| Provider | Outbound port 25 | Reverse DNS (PTR) | Notes |
|----------|------------------|-------------------|-------|
| **AWS Lightsail** | Blocked until AWS approves the **"Request to remove email sending limitations"** form | Set by AWS through the **same form**: give the static IP and the reverse DNS name (`mail.example.com`) | Attach a **static IP** first (a default Lightsail address changes on stop/start). No reverse DNS for IPv6, which Portcullis doesn't use for mail anyway. Open 25, 465, 587 and 993 in the instance's networking firewall |
| **AWS EC2** | Blocked until AWS approves the **"Request to remove email sending limitations"** form for the instance's Elastic IP | Elastic IPs → the address → Actions → **Update reverse DNS** (the A record must already point at it) | Use an Elastic IP. Open the ports in the security group |
| **Hetzner** | Blocked on new accounts: request it in the Cloud Console once the first invoice is paid (Support → Limits → "Unblock port 25") | Cloud Console → the server → Networking → the IP's reverse DNS (Robot: IPs → the address → Reverse DNS) | |
| **DigitalOcean** | Stays blocked on new accounts: ask support, or use a relay | Rename the Droplet to the mail host name exactly; the PTR follows the Droplet's name | |
| **OVH** | Open by default; check the server's firewall (Network → Firewall) and OVH's anti-spam block | Bare Metal / VPS → IP → the address's "…" menu → **Modify the reverse path** | |
| **Home ISP** | Usually blocked, and residential ranges are on Spamhaus's PBL anyway: send through a [relay](#sending-through-a-relay) | Rarely available | **Inbound still needs port 25**, forwarded to the server, and most home ISPs block that too. A static address is still required |
| **Anyone else** | Ask the provider to allow outbound port 25 for this server | Ask the provider to set the PTR of the address | |

Portcullis never probes port 25 itself: it learns that outbound 25 is blocked
from the mail queue (every delivery of the last 24 hours timing out or
refused). Until something has been sent the doctor only says "not known yet".

## Turn mail on

```bash
./portcullis mail enable
```

`mail enable` is idempotent: re-run it any time. It:

1. refuses on Kubernetes, with a DNS provider Portcullis can't write, with
   `MAIL_IPV6` set, and under rootless Podman without the
   [port sysctl](#rootless-podman);
2. writes `MAIL_HOSTNAME` (`--hostname`, default `mail.<domain>`) and adds
   `mail` to `COMPOSE_PROFILES`;
3. issues the **mail certificate** for `MAIL_HOSTNAME` through your DNS
   provider, with its own ACME account and its own key (never Traefik's
   wildcard key, so a compromised mail server can't impersonate
   `auth.<domain>`), and pins a CAA record at `MAIL_HOSTNAME` to that
   account;
4. sets Stalwart up in a short **recovery session**: a one-time admin login
   exists only during it, and the CLI checks that it is refused afterwards;
5. starts `mail`, `mail-resolver` and `mailctl` (and recreates Traefik, the
   Hub and the domains service), and gives mailctl the certificate's key;
6. offers to install the daily mail timer (`--yes` installs it without
   asking).

| Option | Meaning |
|--------|---------|
| `--hostname H` | The mail server's name (the MX of every mail domain, the certificate, the PTR you set). Default `mail.<domain>` |
| `--lan-only true\|false` | Mail passwords work only from the Hub's Local networks ([below](#lan-only-mail-passwords)) |
| `--rotate-key` | Replace mailctl's Stalwart API key |
| `--yes` | Install the daily timer without asking |

Then install the timer if you didn't (it renews the mail certificate,
rotates DKIM, moves the policies on and rewrites the main domain's mail
records):

```bash
./portcullis mail schedule --systemd   # prints the two install commands
```

!!! warning "The daily timer is required"
    Without `portcullis-mail.timer` the mail certificate is never renewed and
    the main domain's DKIM keys never rotate. `./portcullis mail status` and
    the doctor (`mail_timer_missing`) warn after 36 hours without a run.

## DNS

Every mail domain gets one record set, `mail` ([Record sets](dns.md#record-sets)):
the MX, SPF, DKIM, DMARC, MTA-STS, TLS reporting, the client SRV records and,
for the main domain, the HELO SPF and the DANE TLSA record. `mail` replaces
the `nomail` set while mail is on.

**The main domain** is written by the CLI only:

```bash
./portcullis dns setup             # MAIL_HOSTNAME's address now, the mail records too once mailctl has them
./portcullis dns setup --only mail # just the mail records
```

Run `dns setup` right after `mail enable`: with mail on, the main domain's
`address` set also owns `MAIL_HOSTNAME`'s A record (its own records stop the
wildcard answering it). The mail records themselves exist once the Hub has
sent mailctl its first document (a few seconds after the Hub starts, or after
the first change in Settings → Mail); after that the daily timer keeps them
current. If mailctl doesn't answer yet, `dns setup` leaves the mail set out
with a warning, and `--only mail` refuses.

**Added domains** are written by the Hub through the domains service: turn
mail on for the domain in **Settings → Mail** ([Hub](../operations/hub.md#mail))
and its records follow, typically within a minute of every change. Turning
mail off makes the domain **drain** first: the MTA-STS policy says
`mode: none` for its full `max_age` (up to 7 days), then the MX goes and
`nomail` comes back (when it was there before).

**A domain that already has mail** elsewhere: Portcullis replaces its MX and
SPF records. DMARC starts at `p=none` for a domain that had an MX or SPF
before Portcullis, and at `p=reject` for one that had neither; it is raised
only when you accept the [promotion](../operations/mail.md#mta-sts-and-dmarc-promotion).

**DNSSEC and DANE.** The TLSA record (`_25._tcp.<MAIL_HOSTNAME>`) is
published only while the main zone's DNSSEC state is `secure`
([DNSSEC](dns.md#dnssec)); otherwise `mail status` says
`withheld: dnssec <state>` and nothing else changes.

**VPN-only mode.** The MTA-STS, autoconfig and autodiscover pages follow the
[VPN mode](../operations/vpn.md) like every core page: in mode `server` they
answer only over the VPN, so no MTA-STS policy is published (remote servers
fall back to opportunistic TLS, and DANE if the zone is signed). Mail itself
keeps working.

## Who gets a mailbox

Members of the Hub-managed group **`mail_users`** (rules and delegation work
on it like on any group). A person's login and first address is
`<username>@<primary domain>` (the main domain unless you pick an added one in
Settings → Mail); they get `<username>@<added domain>` too on each added
domain whose groups they are in. Identity is the LLDAP username and its
uuid, never the editable email field. Aliases, group lists and mailbox sizes
are set in the Hub ([Hub → Mail](../operations/hub.md#mail)).

`postmaster@` and `abuse@` of every mail domain go to the administrators
(`lldap_admin` members who have a mailbox). `dmarc-reports@`, `tls-reports@`
and `mailer-daemon@` are reserved.

## Mail clients

Nobody signs in to the mail server with their Portcullis sign-in. Each
person creates a **mail password** per device on their Sign-in page
(`https://people.<domain>/signin` → **Mail passwords**; at most 5, shown
once). Administrators can see and revoke them, never create one. See
[Hub → Mail passwords](../operations/hub.md#mail-passwords).

Clients then find the server in one of these ways:

- **Thunderbird and most desktop clients:** autoconfig
  (`autoconfig.<domain>`), from the address alone.
- **Outlook:** autodiscover (`autodiscover.<domain>`).
- **iPhone, iPad and Mac:** the **Download for iPhone, iPad or Mac** button
  next to a new mail password gives a `.mobileconfig` profile that sets up
  the account with that password (built in memory, never stored, unsigned:
  the device says "Not Verified", which is expected).
- **Everything else:** the SRV records, or by hand:

| Setting | Value |
|---------|-------|
| Incoming (IMAP) | `MAIL_HOSTNAME`, port **993**, SSL/TLS |
| Outgoing (SMTP) | `MAIL_HOSTNAME`, port **465**, SSL/TLS (or **587**, STARTTLS) |
| Username | the full primary address, e.g. `alice@example.com` |
| Password | the mail password |

POP3 isn't offered. Port 25 never accepts a login.

## Sending through a relay

When your provider won't open outbound port 25, or your address is in a
residential range, send through a smarthost. Set in `.env`, then run
`./portcullis mail enable` again:

```bash
MAIL_RELAY_HOST=smtp.relay.example.net
MAIL_RELAY_PORT=465                 # 465 = implicit TLS; anything else requires STARTTLS
MAIL_RELAY_USERNAME=portcullis
MAIL_RELAY_PASSWORD=...             # copied to secrets/mail/relay-password
MAIL_RELAY_SPF_INCLUDE=_spf.relay.example.net   # added to every domain's SPF
```

Every non-local recipient then goes through the relay. Receiving still
needs inbound port 25.

## LAN-only mail passwords

`./portcullis mail enable --lan-only true` (or
`MAIL_SUBMISSION_LAN_ONLY=true`) makes mail passwords work only from the
Hub's [Local networks](../operations/hub.md#local-networks): every password is
limited to them, and the server refuses a login from anywhere else. Port 25
stays public (other servers must reach you). Only the CLI sets it; Settings →
Mail shows it. It is refused under rootless Podman (below).

## Rootless Podman

Mail works under [rootless Podman](../operations/rootless-podman.md), with
two differences.

**The port sysctl.** Mail publishes 25, 465 and 587, below the usual
`ip_unprivileged_port_start=80`. `mail enable`, `up` and `upgrade` refuse
until it is 25:

```bash
# As root.
sysctl -w net.ipv4.ip_unprivileged_port_start=25
echo 'net.ipv4.ip_unprivileged_port_start=25' > /etc/sysctl.d/90-portcullis-mail.conf
```

Any local account may then bind ports from 25.

**Degraded mode.** Rootless Podman rewrites the client's address: every
connection seems to come from Podman's gateway. Portcullis then runs mail in
a degraded mode (`MAILCTL_CLIENT_IP=rewritten`, written by the CLI):

- SPF, reverse-DNS (iprev) and the IP blocklists are off for incoming mail;
- DMARC judges DKIM alignment only and never rejects;
- nobody is banned automatically (a ban would hit the gateway, so everyone);
- LAN-only mail passwords are refused ("LAN-only needs the real client
  address; rootless Podman rewrites it").

The doctor shows `mail_client_ip_rewritten` as a Warning for as long as it
lasts. Spam scoring by content, DKIM and the rest work as usual. If you need
the full checks, run mail on Docker.

## Kubernetes

Mail isn't available on Kubernetes yet. `./portcullis mail enable` exits with
"mail isn't available on Kubernetes yet (Docker or rootless Podman only)",
`up` and `upgrade` refuse a `COMPOSE_PROFILES` with `mail`, and Settings →
Mail is read-only.

## Check it works

```bash
./portcullis mail status                         # services, certificate, DKIM, policies, queue, checks
./portcullis mail test --to you@example.org      # an external address you can read
```

Open the test message's headers ("Show original", "View source") and look for
`dkim=pass`, `spf=pass` and `dmarc=pass` in `Authentication-Results`.
[Mail operations → Testing](../operations/mail.md#testing-your-install)
explains how to read them, how to check the spam filter, and how to use an
external tester.

## Turn mail off

```bash
./portcullis mail disable
```

It drains every mail domain through the Hub (MTA-STS `mode: none` for its
`max_age`, up to 7 days), and says so; run it again once
`./portcullis mail status` shows every domain off, and it removes the mail
records and the profile. `--force` removes everything now (senders with a
cached MTA-STS policy may bounce mail until it expires). The mail volumes are
kept.

## Settings in `.env`

| Variable | Default | Meaning |
|----------|---------|---------|
| `MAIL_HOSTNAME` | `mail.<domain>` | The mail server's name (written by `mail enable --hostname`) |
| `MAIL_SUBMISSION_LAN_ONLY` | `false` | [LAN-only mail passwords](#lan-only-mail-passwords) |
| `MAIL_DKIM_ROTATE` | `4320h` (180 days) | How often DKIM keys rotate |
| `MAIL_FORMER_RETENTION` | `720h` (30 days) | How long a former person's mailbox is kept ([Former mailboxes](../operations/mail.md#former-mailboxes-and-mail-export)) |
| `MAIL_RELAY_HOST`, `MAIL_RELAY_PORT`, `MAIL_RELAY_USERNAME`, `MAIL_RELAY_PASSWORD`, `MAIL_RELAY_SPF_INCLUDE` | empty | [Relay](#sending-through-a-relay) |
| `MAIL_SPAMHAUS_DQS_KEY` | empty | A [Spamhaus DQS](../operations/mail.md#blocklists-and-the-spamhaus-dqs-key) key (8–64 lowercase letters and digits) |
| `MAIL_ACME_CA_SERVER`, `MAIL_CAA_ISSUER` | empty | **Testing only**: another ACME CA (an `https://` directory URL) for the mail certificate, and its CAA issuer domain (pinned at `MAIL_HOSTNAME`; with `DNS_CAA` on, `mail cert` refuses without it). The mail certificate otherwise follows `ACME_CA_SERVER` and `ACME_STAGING` |
| `PORTCULLIS_MAIL_SUBNET` and the other `PORTCULLIS_MAIL*` network keys | `172.31.255.0/28`, `172.31.255.16/28` | The two mail networks' fixed addresses. Change them only if they collide with a host, LAN or VPN network |
| `MAILCTL_CLIENT_IP` | written by the CLI | `preserved` (Docker) or `rewritten` (rootless Podman). Never set it by hand |
