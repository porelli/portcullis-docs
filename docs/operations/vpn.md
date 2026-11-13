# VPN-only Access

An app instance can be made **VPN-only**: it then answers only to devices
connected through a VPN that Portcullis knows, and only after the normal
Portcullis sign-in, from a device that belongs to the person who signed in.
The whole server can go the same way (`./portcullis vpn mode server`), or
only its admin surfaces (`admin`).

Portcullis has its own VPN, the **built-in** WireGuard VPN, and can also use
VPN apps from the Marketplace (Headscale) as **VPN providers**. Several can
be used at once. The interfaces are in
[contracts §3.3](../guides/integration-contracts.md#33-vpn-only-access-the-vpn-block-new-vpn),
[§4](../guides/integration-contracts.md#4-policy-file-hub-group-gate) and
[§16](../guides/integration-contracts.md#16-vpn-and-the-wg-service-new-vpn).

!!! note "A VPN never replaces sign-in"
    Being on a VPN is an extra condition, never a sign-in method or a factor.
    A VPN-only app still asks for the sign-in its
    [template](auth-policies.md) needs, its groups and path rules still
    apply, and a step-up is never skipped. A VPN app's own sign-in (Headscale's
    OIDC) never stands in for the Portcullis sign-in.

## The model

Core's **`wg` service** (one Go binary, userspace WireGuard on a gVisor
network stack: no capabilities, no TUN device, no kernel module) has two
roles:

- **The edge** (the VPN edge): every VPN's traffic to Portcullis goes through it. Each
  wired marketplace provider has its own TCP port on the edge, and the
  built-in VPN hands its connections over in-process. The edge checks every
  connection's client address against the provider's ranges and its
  current device list, then passes it to Traefik's VPN entrypoint
  `vpnsecure` with a PROXY v2 header. Traefik trusts PROXY headers only
  from `wg`.
- **The people role**: the built-in VPN (one WireGuard tunnel, UDP 51820 by
  default, tunnel `10.213.0.0/22`). Its clients reach exactly one thing:
  Portcullis over HTTPS (plus HTTP, which redirects, and its DNS resolver).
  It is a split tunnel, not a general VPN.

A VPN-only app has **five gates**, all of which must pass:

1. **No internet route.** The app's routers exist only on `vpnsecure`. On
   the internet entrypoint (`websecure`) its hostnames answer only a static
   page: "This app is only reachable over a Portcullis VPN. Connect your
   device and reload."
2. **The edge.** The connection came in through a provider's own path (its
   edge port from its gateway's address, or the built-in tunnel), from an
   address in that provider's ranges that is one of its current devices,
   and the provider's device list is fresh.
3. **Traefik's allowlist.** The app's routers accept only the ranges of the
   providers the app accepts (*Through*, below), matched on the connection's
   address, never a header.
4. **Portcullis sign-in**, unchanged.
5. **The device binding.** group-gate looks the address up in the provider's
   device list: the device must exist, be unexpired, and belong to the
   signed-in person. Otherwise it answers "this device isn't yours; sign in
   on your own device" (the owner's name is never shown), or, for a stale
   list, "your VPN's device list is out of date; try again in a minute".

Everything **fails closed**. With `wg` down, the Hub not publishing the
device lists (`vpn.json`, valid one hour and republished every 10 minutes), a
list that can't be read, or a provider whose list is stale, the affected
VPN-only apps are unreachable. They never fall back to the internet.

**Local networks never count.** Being on a [Local
network](hub.md#local-networks) (your LAN, a tailnet range you entered there)
is never a VPN address: only the binding above opens a VPN-only app.

## Built-in setup

The VPN service is off on a new install (compose profile `wg`). The Hub must
be running.

```bash
./portcullis vpn init                          # wg + the built-in VPN on UDP 51820, 10.213.0.0/22
./portcullis vpn init --port 51821             # another UDP port
./portcullis vpn init --subnet 10.213.4.0/22   # another tunnel network
./portcullis vpn init --builtin off            # only the edge, for marketplace VPNs
```

`vpn init` adds `wg` to `COMPOSE_PROFILES`, writes `PORTCULLIS_VPN_BUILTIN`,
`PORTCULLIS_VPN_PORT` and `PORTCULLIS_VPN_SUBNET` into `.env`, generates the
built-in VPN's key once (`secrets/wg/people.key`, never printed) and starts
`wg`, Traefik and the Hub. It refuses, writing nothing, a subnet that
overlaps a Docker network, Docker's default address pools (`172.16.0.0/12`,
`192.168.0.0/16`), under Podman Podman's pools (`10.88.0.0/16`,
`10.89.0.0/16`), Portcullis' core and VPN networks, the reserved link subnet
`10.214.0.0/24`, a Local network you entered in the Hub or a wired provider's
range, and suggests a free /22 in `10.213.0.0/16`. The Hub's default Local
networks only give a warning. Details: [CLI → vpn init](cli.md#vpn-init).

Then:

- **Open the UDP port** (51820 unless you changed it) in the server's
  firewall and your cloud provider's firewall. Clients use the main domain
  as the endpoint (`<domain>:51820`), so its A record must point at this
  server, which the [DNS plan](../setup/dns.md) already does.
- **Who may have devices**: Hub → **Settings → VPN** (below).
- **Add your own device** on `https://people.<domain>/vpn/`
  ([below](#devices-on-the-built-in-vpn)), or from the host with
  `./portcullis vpn add-device <you> <name>`.
- **Make apps VPN-only** on their instance page (**Overview → Access**).

`./portcullis vpn builtin off` switches the built-in VPN off later (its key
file is emptied, so its devices stop working) and `vpn builtin on` back on
(a new key when there is none). The edge, and every marketplace provider,
keeps running either way.

### Settings → VPN

The Hub's **Settings → VPN** shows the mode and public enrolment (read-only:
they are set on the host, [below](#modes-and-the-public-set)), whether the VPN
service is up, the built-in VPN's subnet, port and device count, any instance
stopped because a narrowing failed, and every provider (source, wired, ranges,
devices, map fresh or stale, each linking to its VPN tab). It sets:

| Setting | Default | Meaning |
|---------|---------|---------|
| VPN users group | empty (every person) | Who may use any Portcullis VPN. It gates every provider's devices: a person outside it can't add built-in devices, their built-in devices are revoked, and their marketplace devices drop out of the device lists |
| Devices per person | 10 (1–100) | Built-in devices only |
| Device expiry | `1y` | Built-in devices: `30d`, `90d`, `1y` or `never` (the API also takes a duration of at least 30 days) |

Saving is audited `vpn.settings`.

## Wiring a marketplace VPN

A Marketplace app whose template has a [`vpn:` block](../guides/manifest-reference.md#vpn)
(today: [Headscale](../apps/headscale.md)) can be wired as a **VPN provider**:
a second way into VPN-only apps. Installing it doesn't do that; you turn it on
per instance. With Headscale:

1. Run `./portcullis vpn init` first (`--builtin off` if you want only the
   tailnet): wiring is refused with "the VPN service isn't running: run
   ./portcullis vpn init on the host" while `wg` is down.
2. Create and enable a Headscale instance, then do its post-start step (its
   app page and the instance's notes): create a Headscale API key and paste
   it into the instance's **Headscale API key** setting. Without the key the
   gateway node doesn't register and the device list goes stale.
3. On the instance page, open the **VPN** tab, tick **Use for Portcullis
   access**, set the **refresh** if you want (how often the Hub asks the app
   for its devices, `15s`–`10m`, default `60s`) and **Save**. The Hub gives
   the provider a slot (its own edge port and gateway address) and restarts
   it with its gateway joined to the VPN network.
4. People register their Tailscale clients with Headscale, signing in
   through Portcullis. Only nodes of Headscale users who signed in through
   Portcullis count; nodes of local Headscale users never do.

The **VPN tab** then shows the ranges, the devices (and how many are
online), whether the map is fresh and when it was last refreshed, the hook's
last error, and every device **left out** with the reason:

| Reason | Meaning |
|--------|---------|
| `ipv6` | An IPv6 address: Portcullis matches IPv4 tunnel addresses only |
| `outside_ranges` | Not in the provider's ranges |
| `gateway` | The gateway node's own address |
| `expired` | Its expiry is past |
| `duplicate` | Two devices share the address: both are left out (doctor Problem) |
| `not a Portcullis person` | Its owner isn't an enabled person in the VPN users group |

Owners are matched by LLDAP username, or by the Keycloak user id mapped to
the LLDAP username, never by email. A provider of `source: static` (plain
WireGuard servers) has no device hook: the tab has **Static assignments**
where you assign an address to a person and a device name ("Traffic from
&lt;address&gt; counts as &lt;person&gt;'s device &lt;name&gt;"); the doctor reminds
you that such devices aren't proven to exist (`vpn_static_mapping`).

**DNS.** The tab lists the A records that point the Portcullis hostnames at
the provider's gateway. Headscale's DNS hook writes them into its MagicDNS
records, so tailnet clients reach this server through the gateway. A
provider with `dns: manual` asks you to configure them in the app by hand
and to click **I configured them**.

**Refusals when wiring** (`409`): a range that overlaps the built-in subnet,
the reserved link subnet, a reserved range (the core networks,
`172.16.0.0/12`, `192.168.0.0/16`, and under Podman `10.88.0.0/16` and
`10.89.0.0/16`), a Docker network or another wired provider. An overlap with
your Local networks is accepted, with a doctor Warning (those addresses also
reach LAN-only ports).

**Unwiring** asks first and lists the apps that accept only this provider:
they become unreachable (an empty, deny-all allowlist; doctor
`vpn_via_dead`), never reachable from the internet.

**What wiring opens.** Nothing that wasn't public: the provider's control
routers (Headscale's coordination and DERP, which clients need to connect)
stay on the internet in every mode, and its admin UI (Headplane) follows the
instance's access like any app. A provider's instance runs on this server
(its gateway joins the VPN network). Gateways that hold `NET_ADMIN`, run
privileged or get host devices are shown by the doctor
(`vpn_gateway_privileged`); Headscale's gateway runs in userspace without
them.

## Several VPNs and *Through*

Every live provider (the built-in VPN when on, every wired marketplace
provider) is a way into every VPN-only app by default. People use whichever
VPN they have; the binding is per device whatever the provider.

An instance's **Access** section (instance page, **Overview**) sets:

- **Reachable from**: *the internet (default)* or *only Portcullis VPNs*.
- **Through**: *every VPN provider*, or a subset (for example only
  *Portcullis VPN (built-in)*). Only providers that are live can be picked.
- In server mode, for an instance with [public exceptions](hub.md#public-exceptions):
  *Public links stay on the internet (server mode)* (doctor
  `vpn_public_links`).

**Save access** asks first and restarts the app. Making an app VPN-only, or
narrowing *Through*, takes effect at once. Making it reachable from the
internet widens access, so AI tools need a confirmation for it. Choosing VPN
with no live provider is refused ("wire a VPN first"); choosing VPN with no
provider at all leaves the app unreachable (doctor `vpn_no_providers`).

When the Hub can't apply a change that narrows an app's access (to VPN-only,
fewer providers, fewer ranges), it **stops the app** (data kept), raises
doctor `vpn_reach_failed_closed` and starts it again after the next
successful render. Settings → VPN lists such apps.

## Modes and the public set

Which **core** pages answer only over the VPN is a host setting, never a Hub
setting:

```bash
./portcullis vpn mode apps     # the default: core as usual; apps choose per instance
./portcullis vpn mode admin    # the admin surfaces VPN-only
./portcullis vpn mode server   # everything VPN-only but the public set
./portcullis vpn mode server --public-enrol false
```

| Mode | VPN-only | Still on the internet |
|------|----------|-----------------------|
| `apps` | the instances you set to VPN-only | every core page |
| `admin` | those, plus the Hub, the Keycloak admin console, LLDAP, the Traefik dashboard, Grafana (`metrics.<domain>`) and the MCP endpoints | the portal, people.&lt;domain&gt;, sign-in pages, setup links |
| `server` | every instance and every core page, except the public set | the public set |

**The public set in server mode:**

- the HTTP → HTTPS redirect on port 80 (certificates use DNS-01, so nothing
  else is needed for ACME);
- the built-in VPN's UDP port;
- every wired provider's control routers and the ports its template
  publishes (Headscale's coordination and DERP);
- the public links of instances with *Public links stay on the internet*;
- with public enrolment on (`PORTCULLIS_VPN_PUBLIC_ENROL=true`, the
  default): the enrolment surfaces, still behind sign-in: Keycloak's sign-in
  pages and the sign-in callback on `auth.<domain>` (never the admin
  console), setup links on `enroll.<domain>`, and people.&lt;domain&gt;'s
  `/vpn/` page, so a person can add a first device. Public enrolment never
  means unauthenticated.

With `--public-enrol false` only the UDP ports, the control routers and those
public links stay public. New built-in devices then come from an existing
device or from the host (`./portcullis vpn add-device`).

A VPN-only core page answers `/vpn-required` on the internet. group-gate also
denies those hosts on its internet paths, as a second layer.

!!! note "The MCP endpoints"
    In the `admin` and `server` modes the MCP endpoints (`mcp.<domain>`,
    `hub.<domain>/mcp`, `people.<domain>/mcp`) answer only over the VPN,
    but they never go through group-gate, so they aren't bound to the
    device's owner: any device on a Portcullis VPN reaches them. The MCP
    OAuth token is still required ([AI support](ai.md)).

The mode change writes `PORTCULLIS_VPN_MODE`, `PORTCULLIS_VPN_PUBLIC_ENROL`
and the core routers' entrypoint variables into `.env`, then recreates core.
The Hub shows the mode read-only and copies it into the policy. In `admin`
or `server` mode with one provider only, the doctor recommends the built-in
VPN as a second path (`vpn_single_provider`).

## Devices on the built-in VPN

People add their own devices on **`https://people.<domain>/vpn/`** (also
linked from the Sign-in page's **VPN devices** card). The page needs a
signed-in person in the VPN users group.

**Adding a device:**

1. Name it (1–64 characters) and click **Add device**.
2. Sign in again in the small window that opens (a fresh sign-in, at most
   5 minutes old, that the people page's template accepts).
3. The browser makes the WireGuard key pair itself (X25519, WebCrypto).
   Only the **public key** is sent; the Hub picks the device's address in the
   built-in subnet and answers the server's public key, endpoint, DNS and
   MTU.
4. The page shows the WireGuard configuration **once**, as text and as a
   QR code, both made in the browser. Import it into the WireGuard app now
   (scan the QR on a phone), then click **Done: I saved it**: the private key
   is overwritten and the panel emptied. Nothing is stored in the browser,
   and the Hub never sees the private key or the configuration.

The configuration is a split tunnel: `AllowedIPs = 10.213.0.1/32`,
`DNS = 10.213.0.1`, MTU 1280, `PersistentKeepalive = 25`. Only Portcullis
traffic goes through it.

**WireGuard apps.** Use the official WireGuard client: the WireGuard app on
Windows, macOS (App Store), iOS and Android (scan the QR code or import the
file), and on Linux `wg-quick` or NetworkManager (import the saved
configuration as a `.conf` file).

**Renew, rename, remove.** Each built-in device has **Renew** (a fresh sign-in
and a new key pair: the same device and address with a new key; the old
configuration stops working), **Rename** and **Remove**. A device expires
after the Settings expiry (one year by default); the doctor tells its owner
14 days before (`vpn_expiring`). Marketplace devices are listed too, read-only
("managed in Headscale tailnet"): manage them in their app.

Limits and refusals: at most the Settings' devices per person ("at most
&lt;n&gt; devices"), a public key another device uses, no fresh sign-in, a
person outside the VPN users group, or the built-in VPN off.

**From the host.** `./portcullis vpn add-device <user> <name>` makes a device
for any enabled person in the VPN users group: the key pair is made in the
`wg` container, only the public key goes to the Hub, and the configuration
and a terminal QR code are printed once. The private key is never on a
command line or in a file. Nobody can make a configuration for someone else
in the Hub's UI, and no AI tool creates one.

## Revocation

A removed device stops working, and its open connections are closed: the
edge re-checks every open connection against the current device lists on
every change and every 2 seconds. How soon a removal takes effect depends on
where the device lives:

| Where | How it is removed | Effect |
|-------|-------------------|--------|
| Built-in VPN | **Remove** on `/vpn/`, People → person → **Sign-in** → *VPN devices* (administrators and holders of `sign_in_help`), `./portcullis vpn revoke <id>`, the AI tool `remove_vpn_device`, or expiry | Within seconds: the Hub publishes at once, `wg` drops the peer and closes its connections. The address is quarantined for 7 days before it is given out again |
| Built-in VPN, the person left | Disabled or deleted in LLDAP, removed from the VPN users group, or deleted and re-created under the same name | At the Hub's next check (every 10 s): audited `vpn.device_removed` with the reason |
| Hook provider (Headscale) | Delete the node in the app | At the provider's next refresh (60 s by default), then within seconds |
| Hook provider, list stale | The hook fails, times out or the gateway is down | After `max(3 × refresh, 3 min)` (never more than 30 min) every device of that provider is denied, until the next good run |
| Static provider | **Remove** under Static assignments | Within seconds |

A mesh may hand a removed node's address to another person's node within
one refresh. The binding then fails (the owner isn't the signed-in person)
until the next refresh: it fails closed, never open. Open connections also
end after 12 hours, and after 1 hour without traffic.

The edge also caps connections: 1024 per provider, 128 per person across
their devices, 32 per client address; under pressure it closes the heaviest
person's idle sessions first ([hardening](hardening.md#vpn-wg-the-edge-and-gateways)).

## DNS caveats

- **Built-in VPN.** The configuration sets `DNS = 10.213.0.1`, the people
  role's resolver. It forwards every query (upstream `1.1.1.1` and `9.9.9.9`
  unless `PORTCULLIS_VPN_DNS_UPSTREAM` says otherwise) and rewrites only
  answers for Portcullis names that point at this server: A → `10.213.0.1`,
  AAAA → no data. So Portcullis names go through the tunnel and everything
  else resolves as usual.
- **DNSSEC-validating clients.** A rewritten answer can't validate: the
  resolver strips its signatures and never claims it validated. A device that
  validates DNSSEC itself (for example `systemd-resolved` with `DNSSEC=yes`)
  fails on rewritten names when your zone is signed
  ([DNSSEC](../setup/dns.md#dnssec)). Let the tunnel's resolver answer for
  those names unvalidated (`DNSSEC=allow-downgrade` or `no` for the WireGuard
  interface).
- **Browser DNS-over-HTTPS.** A browser with its own secure DNS (Firefox's
  DNS over HTTPS, Chrome's secure DNS) asks its own resolver, not the
  tunnel's: Portcullis names then resolve to the public address, and
  VPN-only apps show `/vpn-required`. Turn it off, or let it fall back to
  the system resolver.
- **IPv6.** Portcullis matches IPv4 tunnel addresses only.
- **Marketplace providers.** A failed DNS hook (doctor `vpn_dns_failed`)
  leaves the names resolving publicly: VPN-only apps then show
  `/vpn-required` on the tailnet too.

## Break-glass and the lock-out guard

In `admin` and `server` mode the Hub itself answers only over the VPN, so
losing every VPN would lock you out. Two things guard against it:

- **The lock-out guard.** `vpn mode admin` and `vpn mode server` refuse
  unless an administrator's (`lldap_admin`) device was online in the last
  10 minutes on the built-in VPN or a hook provider (static providers don't
  count). Connect a device first, or pass `--force`. The doctor reports
  `vpn_no_admin_device` when no administrator's device was seen in 30 days.
- **The break-glass.** On the host, `./portcullis vpn mode apps` puts every
  core page back on the internet. It works with `wg`, every VPN provider and
  the Hub down. `./portcullis status` names it whenever the mode isn't
  `apps`.

Provider control routers stay public in every mode, so marketplace clients
can always reconnect, and `./portcullis vpn add-device` on the host can
always make a built-in device for an administrator.

## What isn't covered

- **Not a general-purpose VPN.** The built-in VPN gives no LAN access, no
  exit node and no mesh: peers reach Portcullis' VPN entrypoint only.
  Marketplace VPNs keep doing what they do for people; Portcullis only uses
  their path to its gateway.
- **Non-HTTP ports** (Samba, Time Machine) over the VPN.
- **IPv6** inside the tunnels.
- **The LAN as equal to the VPN.** Local networks never open a VPN-only app.
- **Shared devices** (a tablet several people use): a device has one owner.
- **Marketplace VPN instances on another server**: a provider runs on this
  server. Server-to-server tunnels (the reserved `link` role, UDP 51821,
  `10.214.0.0/24`) aren't built yet.
- **Kubernetes**: not supported yet.
