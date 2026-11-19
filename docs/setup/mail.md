# Mail Server

Portcullis can run a full mail server for the main domain and for every
[added domain](dns.md#adding-extra-domains) you turn mail on for: sending and
receiving, a spam filter, SPF, DKIM and DMARC that pass and align, MTA-STS,
TLS reports, DANE when the main zone is signed, your LLDAP people as
mailboxes, aliases and group lists, and one mail password per device.

The mail server is a **mail provider**: an app from the Marketplace whose
template declares a `mail:` block, wired by a full administrator into the
server's one **mail slot**. Core and the Hub run the slot and know no mail
server: core keeps the mail certificate, TLSA, the HELO SPF, the slot's
networks and volumes, LAN-only and the CLI; the Hub drives the provider
through the provider API, writes its DNS and checks every rule itself. The
first provider is [Stalwart](../apps/stalwart.md) (the upstream image,
unmodified and pinned, with Portcullis' `mailctl` as its adapter), and
`./portcullis mail enable` wires it for you.

Day-to-day work (wiring, switching, DKIM, policies, backups,
troubleshooting) is on [Mail operations](../operations/mail.md); the
interfaces are in
[contracts §19](../guides/integration-contracts.md#19-mail-provider-api-new-mail-provider).

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
| **About 1.5 GiB of free memory** (Stalwart) | The `stalwart` app caps Stalwart at 1 GiB, its adapter at 256 MiB and its resolver at 128 MiB |

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

Portcullis never probes port 25: the provider learns that outbound 25 is
blocked from its own delivery history (every delivery of the last 24 hours
timing out or refused). Until something has been sent the doctor only says
"not known yet".

## Turn mail on

```bash
./portcullis mail enable
```

`mail enable` is idempotent: re-run it any time. It:

1. refuses on Kubernetes, with a DNS provider Portcullis can't write, with
   `MAIL_IPV6` set, LAN-only under rootless Podman, and under rootless
   Podman without the [port sysctl](#rootless-podman);
2. **opens the mail slot**: writes `PORTCULLIS_MAIL=on`, `MAIL_HOSTNAME`
   (`--hostname`, default `mail.<domain>`) and `MAIL_SUBMISSION_LAN_ONLY`
   (`--lan-only`), and prepares the slot's networks and volumes;
3. issues the **mail certificate** for `MAIL_HOSTNAME` through your DNS
   provider, with its own ACME account and its own key (never Traefik's
   wildcard key, so a compromised mail server can't impersonate
   `auth.<domain>`), and pins a CAA record at `MAIL_HOSTNAME` to that
   account;
4. restarts the Hub and the domains service with the slot open;
5. prints what the provider may do (the warning below) and asks you to type
   the instance id, `stalwart` (`--yes` accepts it), then has the Hub
   install the `stalwart` app from the default source when it isn't
   installed and **wire** it ([Wiring a provider](../operations/mail.md#wiring-a-provider)):
   every mail password is voided first, then the provider gets its ports,
   its secrets and the certificate;
6. offers to install the daily mail timer (`--yes` installs it without
   asking).

The warning, word for word:

> This app becomes the mail server for every person and every mail domain.
> It gets public ports 25, 465, 587 and 993, writes the mail DNS records of
> every mail domain, creates and checks the mail passwords of every person
> in mail_users, sends mail to the internet (outbound SMTP), and can read
> every mailbox.

| Option | Meaning |
|--------|---------|
| `--hostname H` | The mail server's name (the MX of every mail domain, the certificate, the PTR you set). Default `mail.<domain>` |
| `--lan-only true\|false` | Mail passwords work only from the Hub's Local networks ([below](#lan-only-mail-passwords)) |
| `--provider stalwart\|none` | The provider to install and wire (default `stalwart`); `none` opens the slot only |
| `--yes` | Accept the typed confirmation and install the daily timer without asking |

**Another provider, or wiring from the Hub.** With `--provider none` the
slot opens and nothing is wired. Install a mail server from the Marketplace
(the "Mail server" badge), open the instance's **Mail** tab and wire it there
([Hub → Mail](../operations/hub.md#mail)): it needs a full administrator, a
fresh sign-in with a security key and the typed instance id.

Then install the timer if you didn't (it renews the mail certificate,
moves the TLSA rollover on and rewrites the main domain's mail records):

```bash
./portcullis mail schedule --systemd   # prints the two install commands
```

!!! warning "The daily timer is required"
    Without `portcullis-mail.timer` the mail certificate is never renewed and
    the main domain's mail records (its DKIM keys included) are never
    rewritten. `./portcullis mail status` and the doctor
    (`mail_timer_missing`) warn after 36 hours without a run.

## DNS

Every mail domain gets one record set, `mail` ([Record sets](dns.md#record-sets)):
the MX, SPF, DKIM, DMARC, MTA-STS, TLS reporting, the client SRV records and,
for the main domain, core's HELO SPF and DANE TLSA record. `mail` replaces
the `nomail` set while mail is on. The provider proposes each domain's
records; the Hub and the domains service check them against fixed rules
before anything is written (only mail names, never A, AAAA, CAA, NS, DS or
TLSA from the provider, and DMARC never below the domain's floor).

**The main domain** is written by the CLI only:

```bash
./portcullis dns setup             # MAIL_HOSTNAME's address now, the mail records too once the provider has them
./portcullis dns setup --only mail # just the mail records
```

Run `dns setup` right after `mail enable`: with mail on, the main domain's
`address` set also owns `MAIL_HOSTNAME`'s A record (its own records stop the
wildcard answering it). The mail records themselves exist once the Hub has
sent the provider its first document (right after the wiring, or after the
first change in Settings → Mail); after that the daily timer keeps them
current. If the Hub can't give them yet, `dns setup` leaves the mail set out
with a warning, and `--only mail` refuses ("no mail provider is wired:
nothing to write for --only mail" when nothing is wired).

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
([DNSSEC](dns.md#dnssec)); otherwise nothing else changes.

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
residential range, send through a smarthost. Set it in **Settings → Mail →
Relay, DKIM rotation and former accounts** ([Hub → Mail](../operations/hub.md#settings-mail)):
host, port, user, SPF include and password. Port 465 means implicit TLS, any
other port requires STARTTLS, the password is write-only, and the SPF
include is added to every mail domain's SPF. Saving a relay change needs a
fresh sign-in with your security key, and is never possible through MCP or
AI. Every non-local recipient then goes through the relay. Receiving still
needs inbound port 25.

## LAN-only mail passwords

`./portcullis mail enable --lan-only true` (or
`MAIL_SUBMISSION_LAN_ONLY=true`, then `./portcullis up`) makes mail
passwords work only from the Hub's
[Local networks](../operations/hub.md#local-networks): every password is
limited to them (at most 64 networks, never "anywhere": a public IPv4 range
at most a /16, a public IPv6 one at most a /32, private ranges as wide as
their block; IPv6 within ULA, link-local or global unicast and never one of
the ranges that embed IPv4 addresses), and the server refuses a login from
anywhere else. The Hub checks every password the provider reports and
revokes one that reaches beyond the Local networks. Port 25 stays public
(other servers must reach you). Only the CLI sets it; Settings → Mail shows
it. It is refused under rootless Podman (below).

## Rootless Podman

Mail works under [rootless Podman](../operations/rootless-podman.md), with
two differences.

**The port sysctl.** Mail publishes 25, 465 and 587, below the usual
`ip_unprivileged_port_start=80`. `mail enable`, `up` and `upgrade` refuse
until it is 25, and the Hub refuses to wire a provider:

```bash
# As root.
sysctl -w net.ipv4.ip_unprivileged_port_start=25
echo 'net.ipv4.ip_unprivileged_port_start=25' > /etc/sysctl.d/90-portcullis-mail.conf
```

Any local account may then bind ports from 25.

**Degraded mode.** Rootless Podman rewrites the client's address: every
connection seems to come from Podman's gateway. The provider then runs in a
degraded mode (`client_ip: rewritten` in the Hub's document; core writes
`PORTCULLIS_MAIL_CLIENT_IP=rewritten` for the Hub):

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
`up` and `upgrade` refuse while the slot is open, the Hub refuses to wire a
provider, and Settings → Mail says "Mail isn't available on Kubernetes yet
(Docker or rootless Podman only)".

## Check it works

```bash
./portcullis mail status                         # the provider, its checks, the certificate, TLSA, the timer
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

It unwires the provider through the Hub and drains every mail domain
(MTA-STS `mode: none` for its `max_age`, up to 7 days), and says so; run it
again once `./portcullis mail status` shows every domain off, and it removes
the main domain's mail records and closes the slot (`PORTCULLIS_MAIL=off`).
`--force` unwires now (senders with a cached MTA-STS policy may bounce mail
until it expires). The provider instance and its data are kept (delete it
from the Hub if you don't need it), and so are `MAIL_HOSTNAME`'s A record and
its CAA pin: delete them by hand if you don't need them.

## Settings in `.env`

| Variable | Default | Meaning |
|----------|---------|---------|
| `PORTCULLIS_MAIL` | `off` | `on` (exactly) opens the mail slot. Written by `mail enable` / `mail disable` |
| `MAIL_HOSTNAME` | `mail.<domain>` | The mail server's name (written by `mail enable --hostname`) |
| `MAIL_SUBMISSION_LAN_ONLY` | `false` | [LAN-only mail passwords](#lan-only-mail-passwords) |
| `MAIL_ACME_CA_SERVER`, `MAIL_CAA_ISSUER` | empty | **Testing only**: another ACME CA (an `https://` directory URL) for the mail certificate, and its CAA issuer domain (pinned at `MAIL_HOSTNAME`; with `DNS_CAA` on, `mail cert` refuses without it). The mail certificate otherwise follows `ACME_CA_SERVER` and `ACME_STAGING` |
| `PORTCULLIS_MAIL_API_SUBNET`, `PORTCULLIS_MAIL_API_IP_RANGE`, `PORTCULLIS_MAIL_API_HUB_IP`, `PORTCULLIS_MAIL_API_PROVIDER_IP` | `172.31.255.16/28`, `172.31.255.24/29`, `.18`, `.19` | The provider API network's fixed addresses. Change them only if they collide with a host, LAN or VPN network |

The relay, the DKIM rotation (`dkim_rotate`, default 180 days) and how long
former mailboxes are kept (`former_retention`, default 30 days) are Hub
settings ([Hub → Mail](../operations/hub.md#mail)); a provider's own options,
such as Stalwart's Spamhaus DQS key, are its app's
[settings](../apps/stalwart.md#settings).
