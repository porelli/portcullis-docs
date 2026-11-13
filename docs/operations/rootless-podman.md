# Rootless Podman

Portcullis runs on rootful Docker or on **rootless Podman** (5.4 or later).
Under rootless Podman the whole stack (core, the Hub and every app instance)
runs as one dedicated, unprivileged host account, the **operator**. Nobody
needs root after a one-time host preparation.

There is one compose file and one CLI for both runtimes. `./portcullis init`
picks the runtime once and writes it into `.env` as `CONTAINER_RUNTIME`. It is
never switched afterwards: to move an install to the other runtime, back it
up, run a fresh `init` and restore ([below](#moving-between-runtimes)).

## Why

Every hardening item holds the same on both runtimes: the two socket proxies
with the same allowlists, internal networks, pinned addresses,
`no-new-privileges`, all capabilities dropped, read-only root filesystems,
memory and process limits, and images pinned by digest.

What changes is where an escape lands. Under rootful Docker, anything that
breaks out of a container, or that gets the Hub's power to create any
container, is host root. Under rootless Podman it is the unprivileged
operator account. The details are in
[Security & Hardening → Rootless Podman](hardening.md#rootless-podman).

The cost is a handful of host features an unprivileged account can't have:
host devices, real source addresses for UDP clients, and ports below a
sysctl (see [Limits](#limits) and the [per-app table](#apps-under-rootless-podman)).

## Host preparation

Do this once, as root. Use a dedicated account for Portcullis (here
`portcullis`). It owns the checkout and needs no `sudo`.

| Item | What it needs | Required |
|------|---------------|----------|
| Dedicated user | not root, owns the checkout | yes |
| Subordinate ids | at least 65536 subuids and 65536 subgids (container ids up to 65534 are used) | yes |
| One user namespace | `containers.conf` doesn't set `userns` (no `auto`, no `keep-id`): every container shares the same mapping | yes |
| cgroups v2 delegation | `memory` and `pids` delegated to the user's systemd manager (systemd's default) | yes |
| Lingering | `loginctl enable-linger`: healthchecks and the start at boot need the user manager running while nobody is logged in | yes |
| User units | `podman.socket` and `podman-restart.service` enabled for the operator | yes |
| Low ports | `net.ipv4.ip_unprivileged_port_start=80`, so Traefik can publish 80 and 443 | yes |
| Network pool | the operator's `~/.config/containers/containers.conf` says, under `[network]`, exactly `default_subnet_pools = [{"base" = "10.89.0.0/16", "size" = 24}]`, and no file in `containers.conf.d` sets `default_subnet_pools`. Portcullis reserves `10.88.0.0/16` (Podman's default network) and `10.89.0.0/16` against [VPN](vpn.md) ranges, so every network Podman creates must come from there: an address in a VPN provider's range could otherwise be a container's | yes |
| `tun` module | loaded at boot, only for marketplace VPN gateways that use a TUN device ([below](#vpn-under-rootless-podman)) | — |
| Versions | Podman 5.4 or later, passt, the Docker CLI and its compose plugin (no Docker daemon) | yes |
| AppArmor (Ubuntu) | pasta's profile accepts SIGTERM from the `podman` profile (`signal (receive) set=(term) peer=podman,`), checked only where both profiles exist. Without it Podman can't stop its network process when the last container leaves a network, and `down` / `restore` / `upgrade` fail with "rootless netns: kill network process: permission denied" ([Launchpad #2154379](https://bugs.launchpad.net/ubuntu/+source/apparmor/+bug/2154379)) | yes |
| Client addresses | `nft` or `iptables` installed, so forwarded TCP keeps the client's address | recommended |
| SELinux | enforcing is supported | — |

`./portcullis init`, `up`, `upgrade` and `restore` check every required
item first and refuse while one fails, listing each failure.
`./portcullis status` shows the same checks.

!!! note "Port 80 for everyone"
    `ip_unprivileged_port_start=80` lets **any** local account bind ports
    80–1023, not only the operator. That is acceptable on a server dedicated
    to Portcullis. Apps that publish a port below the value (the DNS apps on
    53) are refused unless you lower it further ([Limits](#limits)).

Portcullis requires Podman ≥ 5.4. Supported host releases: Ubuntu 26.04 or
later, Debian 13 or later, current Fedora, RHEL 10 or later. Older LTS
releases (Ubuntu 24.04, Debian 12) ship Podman 4.x and are not supported.

### Debian and Ubuntu

```bash
# As root.
apt-get update
apt-get install -y podman passt uidmap nftables systemd-container

# The Docker CLI and compose plugin only (no Docker daemon), from Docker's
# apt repository: https://docs.docker.com/engine/install/debian/ (or /ubuntu/)
# describes how to add it. Then:
apt-get install -y docker-ce-cli docker-compose-plugin

# The operator account, without sudo.
useradd --create-home --shell /bin/bash portcullis

# Subordinate ids (useradd usually adds a range already; check first).
grep '^portcullis:' /etc/subuid /etc/subgid \
  || usermod --add-subuids 100000-165535 --add-subgids 100000-165535 portcullis

# Keep the user manager running without a login (healthchecks, start at boot).
loginctl enable-linger portcullis

# Let unprivileged accounts publish ports from 80.
echo 'net.ipv4.ip_unprivileged_port_start=80' > /etc/sysctl.d/80-portcullis.conf
sysctl --system

# Pin Podman's network pool in the operator's own containers.conf (not a
# containers.conf.d drop-in): Portcullis reserves 10.88.0.0/16 and
# 10.89.0.0/16 against VPN ranges. If the file already has a [network]
# section, put the line there instead.
install -d -o portcullis -g portcullis ~portcullis/.config ~portcullis/.config/containers
printf '[network]\ndefault_subnet_pools = [{"base" = "10.89.0.0/16", "size" = 24}]\n' \
  >> ~portcullis/.config/containers/containers.conf
chown portcullis:portcullis ~portcullis/.config/containers/containers.conf

# Only for marketplace VPN gateways with a TUN device (NetBird, WireGuard
# servers): load the tun module now and at boot.
modprobe tun && echo tun > /etc/modules-load.d/tun.conf

# Ubuntu only (its AppArmor profiles for podman and pasta): let Podman stop
# pasta, its network process. The rule goes into the profile's local file;
# if usr.bin.pasta has no `include if exists <local/usr.bin.pasta>` line,
# add it inside the profile itself instead.
if [ -f /etc/apparmor.d/usr.bin.pasta ] && [ -f /etc/apparmor.d/podman ]; then
  echo 'signal (receive) set=(term) peer=podman,' >> /etc/apparmor.d/local/usr.bin.pasta
  apparmor_parser -r /etc/apparmor.d/usr.bin.pasta
fi
```

### Fedora and RHEL

```bash
# As root.
dnf install -y podman passt shadow-utils nftables systemd-container \
  policycoreutils-python-utils

# The Docker CLI and compose plugin only (no Docker daemon), from Docker's
# repository: https://docs.docker.com/engine/install/fedora/ (or /rhel/)
# describes how to add it. Then:
dnf install -y docker-ce-cli docker-compose-plugin

useradd --create-home portcullis

grep '^portcullis:' /etc/subuid /etc/subgid \
  || usermod --add-subuids 100000-165535 --add-subgids 100000-165535 portcullis

loginctl enable-linger portcullis

echo 'net.ipv4.ip_unprivileged_port_start=80' > /etc/sysctl.d/80-portcullis.conf
sysctl --system

# Pin Podman's network pool in the operator's own containers.conf (not a
# containers.conf.d drop-in): Portcullis reserves 10.88.0.0/16 and
# 10.89.0.0/16 against VPN ranges. If the file already has a [network]
# section, put the line there instead.
install -d -o portcullis -g portcullis ~portcullis/.config ~portcullis/.config/containers
printf '[network]\ndefault_subnet_pools = [{"base" = "10.89.0.0/16", "size" = 24}]\n' \
  >> ~portcullis/.config/containers/containers.conf
chown portcullis:portcullis ~portcullis/.config/containers/containers.conf

# Only for marketplace VPN gateways with a TUN device (NetBird, WireGuard
# servers): load the tun module now and at boot.
modprobe tun && echo tun > /etc/modules-load.d/tun.conf
```

SELinux can stay enforcing. Core's own files are handled for you
([SELinux](#selinux)). Shared folders are not: label each one once, as root,
before you assign it in the Hub:

```bash
semanage fcontext -a -t container_file_t '/srv/media(/.*)?'
restorecon -R /srv/media
```

### As the operator

Sign in as the operator with a real login session (SSH, or
`machinectl shell portcullis@` from root), not `su` or `sudo -u`, so that
`XDG_RUNTIME_DIR` and the user manager are set up:

```bash
systemctl --user enable --now podman.socket podman-restart.service

# Checks: the mapping, delegation and lingering.
podman unshare cat /proc/self/uid_map        # 0 <your uid> 1, then 1 <subuid start> 65536
cat /sys/fs/cgroup/user.slice/user-$(id -u).slice/user@$(id -u).service/cgroup.controllers
                                             # must list memory and pids
loginctl show-user "$USER" -p Linger         # Linger=yes
grep default_subnet_pools ~/.config/containers/containers.conf
                                             # default_subnet_pools = [{"base" = "10.89.0.0/16", "size" = 24}]
```

Without the pool line `init`, `up`, `upgrade` and `restore` refuse with
"containers.conf: Podman's network pools aren't pinned (…): add under
[network] in ~/.config/containers/containers.conf: default_subnet_pools =
[{"base" = "10.89.0.0/16", "size" = 24}]", and `status` shows the same line.
Set it before the first `init`: networks Podman made earlier keep their
addresses.

## Install

As the operator, clone the core repository into the operator's home and run
`init` with the runtime, as in the [Quick Start](../setup/quickstart.md):

```bash
git clone https://github.com/porelli/portcullis.git
cd portcullis
./portcullis init --runtime podman
```

`init` writes `CONTAINER_RUNTIME=podman` and
`PORTCULLIS_ENGINE_SOCKET=/run/user/<uid>/podman/podman.sock` into `.env`.
`--runtime podman` is needed only when a Docker engine also answers on the
host: Docker wins the detection otherwise ([CLI → init](cli.md#init)).

From then on every `./portcullis` command works as on Docker. The CLI points
the Docker CLI at the operator's Podman socket itself, and checks on every
run that the engine answering is Podman. `./portcullis status` starts with a
line such as:

```
runtime: podman 5.6.2 rootless, uid 1001, subuid 100000+65536, ports ≥ 80
```

Two differences in daily work:

- **Host-side owners.** Container id 0 is the operator, and container id
  `n` (1–65535) is host id `subuid start + n − 1`. A file the Hub (uid 10001
  in the container) owns shows up on the host as `110000` with the range
  above. When the CLI asks you to fix an owner it says
  `podman unshare chown …` instead of `sudo chown …`.
- **Backup timer.** `./portcullis backup schedule --systemd` writes **user**
  units for the operator's systemd manager
  ([CLI → backup schedule](cli.md#backup-schedule)).

## Apps under rootless Podman

The Hub checks every app before it deploys it. The Marketplace card and the
instance page show **Rootless: works**, **limited** or **not available**, with
the reasons. An app that is not available can't be created or started; a
limited one runs with the limits named. Under Docker no badge is shown
([Hub → Rootless Podman](hub.md#rootless-podman)).

| Feature | Under rootless Podman |
|---------|-----------------------|
| Core stack, sign-in methods, people, sessions, domains and certificates, AI support, monitoring | works |
| Socket proxies, Traefik's Docker provider | works (Podman's own API is always denied) |
| App backups and restores, core `backup` and `restore` | works (archives are the same on both runtimes) |
| Shared folders and the fixer | works, with conditions: folders owned by a host account outside the operator's id range are refused per path (run `sudo chown -R '<uid>:<gid>' '<path>'` once), and on SELinux hosts each folder needs a label |
| File sharing (Samba, Time Machine) on 445 | works; [Time Machine discovery](#time-machine-discovery) is unverified |
| Apps that trust identity headers | works (they trust Traefik's pinned address, as on Docker) |
| Host networking (NetBird's relay) | limited: published ports must stay at or above the sysctl |
| Apps that publish UDP | limited: clients appear with a rewritten source address |
| Host ports below `ip_unprivileged_port_start` (DNS on 53 at the default 80) | not available, unless you lower the sysctl to that port |
| Host devices, raw disk access (`SYS_RAWIO`, `SYS_ADMIN`) | not available |
| Ids above 65535 | not available (outside the mapping) |
| Other added capabilities inside the container (for example `CHOWN` in a setup step) | works: they act only on mapped ids |

The app templates at the default port start (80):

| App | Status | Why |
|-----|--------|-----|
| AdGuard Home, Pi-hole | not available | DNS on host port 53 (TCP and UDP) is below the port start |
| Scrutiny | not available | needs `SYS_RAWIO` for raw disk access (even with no disk set) |
| ESPHome, motionEye, Zigbee2MQTT | limited | their device slots can't pass host devices: use a network device (an ESPHome device over the network, network cameras, a network Zigbee coordinator) |
| NetBird | limited | host networking for the relay, and its STUN and relay ports are UDP |
| Headscale | works | its VPN gateway runs in userspace, with no TUN device or capability |
| Every other template | works | |

The templates repository commits this classification in `tests/rootless.txt`,
so any change to it shows up in review.

## VPN under rootless Podman

Core's VPN service `wg` ([VPN-only access](vpn.md)) is the same on both
runtimes: userspace WireGuard, no capability, no TUN device, no `sysctls`.
Its UDP port (51820) goes through Podman's port forwarder, which rewrites
the outer source address; that is harmless, because WireGuard authenticates
peers by key and replies go back the same way.

A **marketplace VPN gateway** that uses a TUN device and `NET_ADMIN` (NetBird,
plain WireGuard servers) is **limited** ("uses TUN/NET_ADMIN inside the
rootless network namespace (prefer a userspace mode)"). It works:
`NET_ADMIN` in a rootless container acts only inside the container's own
network namespace, where the client makes its tunnel device and routes, and
nothing reaches host networking. The host needs the `tun` module loaded
(`modprobe tun`, and `/etc/modules-load.d/tun.conf` for boot, as in
[Host preparation](#host-preparation)). The doctor still shows such gateways
(`vpn_gateway_privileged`). Headscale's gateway runs in userspace and needs
neither.

## Moving between runtimes

The runtime is never switched in place. A backup taken on one runtime
restores on the other: ids inside the archives are container ids, which are
the same on both.

1. On the old install, take a backup: `./portcullis backup` (or
   `./portcullis backup --offsite`).
2. Prepare the new host, or a fresh operator account on the same host with
   the old stack stopped (`./portcullis down`), as in
   [Host preparation](#host-preparation).
3. Clone core and run `./portcullis init --runtime podman` (or
   `--runtime docker`) with the same domain.
4. Copy the backup directory over and run
   `./portcullis restore --yes <backup-dir>`, or
   `./portcullis restore --from-offsite`.

The restore keeps the new host's `CONTAINER_RUNTIME` and
`PORTCULLIS_ENGINE_SOCKET` and never takes them from the backup
([CLI → restore](cli.md#restore)). App instances come back from their own
backups in the Hub, as after any restore ([Backups](backups.md#moving-between-runtimes)).

## SELinux

Under Podman with SELinux enforcing, the CLI adds a small compose overlay,
`docker-compose.podman-selinux.yml`, on its own. It relabels bind mounts of
core's files with the narrowest label that works:

- `Z` (private) when one service mounts the path;
- `z` (shared) only when several services mount it or a path above or below
  it, and on `templates/` and `appfiles/` (app instances mount subdirectories
  of them, which the Hub labels `z` too).

Nothing labels the checkout itself, `secrets/`, `backups/` or `.env` (or a
parent of them). The Hub's `.:/project:ro` becomes a 1 MiB tmpfs there, with
`group-gate/group-gate-map.conf` bound into it. The two socket proxies run
with `label=disable` because a confined container can't connect to the
operator's Podman socket, and the CLI's own short-lived helpers that
bind-mount host files (`restore`, `backup --offsite`) also run with
`label=disable` under Podman: those helpers are not SELinux-confined.

The Hub never relabels user data: shared folders under `/srv`, `/mnt`,
`/media` or home directories, and the engine socket, keep their labels.
Label shared folders yourself (`semanage fcontext` and `restorecon`,
[above](#fedora-and-rhel)); the Hub's doctor reports a folder without the
`container_file_t` label (`selinux_label_missing`) with those two commands.

## Time Machine discovery

Time Machine discovery (Bonjour, through the host's Avahi) is unverified
under rootless Podman: the template writes its service file into the
host's Avahi directory, which the operator account must be able to write.
If the Mac doesn't find the share, connect by address: in Finder,
**Go → Connect to Server**, `smb://<server>/<share>`, then choose it in
Time Machine settings ([File Sharing](file-sharing.md)).

## Limits

- **No host devices.** An unprivileged account can't pass a device node or
  raw disk access to a container. Apps that need them are not available.
  An empty device slot (the default) is fine: the app is limited.
- **UDP sources.** Published UDP ports, and connections to published
  loopback ports, see a rewritten source address. Per-client data (a DNS
  app's query log, rate limits) sees one address. Remote TCP keeps the
  client's address when `nft` or `iptables` is installed. Portcullis never
  trusts the gateway address: identity headers are trusted only from
  Traefik's pinned address.
- **Ports below the sysctl.** An app that publishes a host port below
  `net.ipv4.ip_unprivileged_port_start` is refused, and the message names
  the sysctl. Lowering it (to 53 for DNS) allows the app, and lets any local
  account bind ports from that value.
- **Resource limits need delegation.** Without the `memory` and `pids`
  controllers delegated to the operator's user manager (cgroups v1, or a
  changed systemd default), `init`, `up`, `upgrade` and `restore` refuse:
  limits are never dropped silently. The Hub's doctor reports an app
  container that runs without its limits (`limits_not_enforced`).
- **Only rootless Podman.** Rootful Podman and rootless Docker are not
  supported. The Hub's shared-folder fixer refuses rootless Docker and
  userns-remap.
- **Restarts.** Under Podman, core and instance services run with `restart:
  always`, because `podman-restart.service` starts only that policy. A core
  container stopped by hand comes back at boot. Containers come back after a
  reboot through `podman-restart.service` and lingering, both part of the
  host preparation. Manual `docker compose ...` commands bypass both
  `DOCKER_HOST` and the Podman overlays, so use `./portcullis` instead (or
  export what `runtime_export` sets).
- **A restarted `podman.socket`.** The two socket proxies keep the socket
  they started with. After `podman.socket` restarts they can't reach the
  engine and turn unhealthy; `./portcullis status` says so, and
  `./portcullis up` (or `upgrade`) restarts an unhealthy proxy.
- **`lldap-ui`.** Container addresses aren't reachable from the host under
  rootless Podman, so `./portcullis lldap-ui` starts a short-lived forwarder
  published on `127.0.0.1:17170` (`LLDAP_UI_PORT` changes it) and prints the
  SSH tunnel to that port; the forwarder is removed when the command ends.
