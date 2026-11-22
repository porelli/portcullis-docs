# Kubernetes

!!! warning "EXPERIMENTAL"
    Kubernetes support is experimental. It is tested in CI on one pinned
    k3s release, on a single node, and it can change without notice. Few
    marketplace apps run on it yet ([Apps on Kubernetes](#apps-on-kubernetes)).
    For a production install, use rootful Docker or
    [rootless Podman](rootless-podman.md).

Portcullis can run on a **single-node k3s cluster** instead of a container
engine. Core runs as the Helm chart `charts/portcullis`, and the Hub deploys
app instances as Kubernetes objects. Templates don't change: the Hub
translates each instance's compose project into Deployments, Services,
PVCs, NetworkPolicies and Traefik objects.

The runtime is chosen once by `./portcullis init --runtime kubernetes` and
kept in `.env` as `CONTAINER_RUNTIME=kubernetes`. It is never detected and
never switched afterwards. To move an install between runtimes, back it up,
run a fresh `init` and restore ([below](#moving-to-kubernetes)).

The interfaces are pinned in the
[integration contracts](../guides/integration-contracts.md): §3.4 (the
translation), §5 "Traefik on Kubernetes", §6 "On Kubernetes" (the Roles,
the cluster guard, the admission policies), §11.2 (object names), §11.10
(compatibility) and §16.1 (the VPN).

## Namespaces

| Namespace | Holds | Pod security (PSA) |
|-----------|-------|--------------------|
| `portcullis` (`PORTCULLIS_NAMESPACE`) | core's services, its Secrets and ConfigMaps, the admission params | `restricted` |
| `portcullis-apps` (`PORTCULLIS_APPS_NAMESPACE`) | the app instances' Deployments, Jobs, Services, PVCs, Secrets, ConfigMaps and NetworkPolicies, and the Hub's helper and probe pods | `enforce: privileged`, `warn` and `audit: baseline`; the admission policies enforce the baseline instead (built-in PSA can't allow `hostPath` under a prefix) |
| `portcullis-edge` | every IngressRoute and Middleware, core's and the apps', and the apps' pinned ExternalName Services. It is the only namespace Traefik watches, and it holds no Secret | `restricted` |
| `portcullis-storage` | the volume provisioner and its helper pods | `enforce: privileged`, `warn` and `audit: baseline`, plus core's own admission policy `portcullis-storage-pods` |

Portcullis never adopts a namespace it didn't create. Each one carries the
label `app.kubernetes.io/managed-by=portcullis` and the annotation
`portcullis.io/install` = `PORTCULLIS_KUBE_INSTALL_ID`. A namespace of the
same name without them stops `init`.

## Requirements

- **One k3s node**, Kubernetes **1.33 or later**, the first release with
  `supplementalGroupsPolicy` on by default (host-path pods need it, below;
  an older cluster is refused: `Portcullis needs >= 1.33
  (supplementalGroupsPolicy Strict for host-folder pods)`). CI runs `v1.37.2+k3s1`,
  the default; the oldest supported line is pinned at `v1.33.13+k3s2`.
  Both are tested. Another
  distribution only gets a warning ("should work, not CI-tested"), but the
  checks below assume k3s's flags and ServiceLB.
- **IPv4 single-stack**, with one pod CIDR and one service CIDR. Dual-stack
  and IPv6 clusters are refused.
- **No AppArmor stacking of containerd's profile.** On hosts with
  `kernel.apparmor_restrict_unprivileged_unconfined=1` (Ubuntu 26.04 and
  similar), containerd's AppArmor profile denies the signals Postgres sends
  between its own processes, so Postgres never finishes starting
  (containerd#14485, k3s#13625). Portcullis refuses such a host; see
  [Troubleshooting](#postgres-never-starts-apparmor-stacking) for the two
  ways out.
- On the node, for the operator: `kubectl`, `helm`, `jq` and `curl`. The
  CLI runs on the node itself: it compares the node's local addresses with
  the public one.
- **Off-host backups:** the host's `restic`, version 0.19.1 or later
  ([Backups](backups.md#kubernetes)).
- **Local images only** (`PORTCULLIS_KUBE_IMAGES=local`, for development):
  `docker` or `podman` to build, and `sudo` for `k3s ctr images import`.

## Host preparation

Install k3s with these server flags:

| Flag | Why |
|------|-----|
| `--disable=traefik` | core ships its own Traefik |
| `--secrets-encryption` | Secrets are encrypted in k3s's datastore |
| `--kubelet-arg=pod-max-pids=1024` | the only per-pod process limit (compose's `pids_limit` isn't carried) |
| `--node-external-ip=<public IPv4>` | only when the public address is a second address on the node: otherwise ServiceLB rewrites client addresses |

Keep the network policy controller and ServiceLB on: don't pass
`--disable-network-policy` or `--disable=servicelb`.

For example, as a systemd unit (the shape CI uses, with the binary
downloaded from the k3s release and checked against its sha256):

```bash
# As root.
/usr/local/bin/k3s server --disable=traefik --secrets-encryption \
  --kubelet-arg=pod-max-pids=1024 --write-kubeconfig-mode=0600
```

Then give the operator the kubeconfig:

```bash
mkdir -p ~/.kube
sudo cat /etc/rancher/k3s/k3s.yaml > ~/.kube/config   # context "default"
chmod 600 ~/.kube/config
kubectl --context default get nodes
```

**Firewall.** Allow ports 6443 (the Kubernetes API) and 10250 (the kubelet)
only from the addresses that administer the cluster. `status` and the Hub's
doctor (`kube_api_public`) warn when either answers on the public address.
Portcullis never changes a firewall.

## Install

```bash
git clone https://github.com/porelli/portcullis.git && cd portcullis
./portcullis init --runtime kubernetes --kube-context default --domain example.com
```

`--kube-context` is required. The CLI never uses the current context:
every `kubectl` and `helm` call names `PORTCULLIS_KUBE_CONTEXT`. `init`
detects the cluster's networks and writes these keys into `.env`:

| Key | Value |
|-----|-------|
| `PORTCULLIS_KUBE_CONTEXT` | the context you named |
| `PORTCULLIS_NAMESPACE`, `PORTCULLIS_APPS_NAMESPACE` | `portcullis`, `portcullis-apps` |
| `PORTCULLIS_POD_CIDR`, `PORTCULLIS_SERVICE_CIDR`, `PORTCULLIS_KUBE_API_ENDPOINTS` | detected. Every later command checks them against the cluster and refuses a different network, naming both values |
| `PORTCULLIS_KUBE_INSTALL_ID` | a new UUID: the namespaces' owner |
| `PORTCULLIS_KUBE_IMAGES` | `registry` (below) |
| `PORTCULLIS_TRAEFIK_SERVICE_IP`, `PORTCULLIS_TRAEFIK_VPN_SERVICE_IP`, `PORTCULLIS_WG_EDGE_SERVICE_IP` | fixed ClusterIPs: the service network's address + 20, 21 and 22, in its static band |

Before deploying anything, `init`, `up`, `upgrade` and `restore` run the
**host checks**. They refuse while one fails, listing every failure under
`this cluster isn't ready for Portcullis (docs: operations/kubernetes):`.
They check:

- `kubectl` and `helm` are present, the context exists and the cluster answers;
- Kubernetes 1.33 or later;
- k3s's flags (read from the node's `k3s.io/node-args`): `--secrets-encryption`, `--disable=traefik`, no `--disable-network-policy`, ServiceLB on. On k3s, node-args it can't read fail the check; on another distribution they only warn;
- the kubelet's `podPidsLimit` is 1024;
- IPv4 single-stack with one pod CIDR and one service CIDR, the same as `.env`;
- the three fixed ClusterIPs are inside the static band and not taken by another Service (a Services list it can't read fails);
- the four namespaces are absent or this install's;
- AppArmor: `kernel.apparmor_restrict_unprivileged_unconfined` isn't `1`
  while AppArmor is on and containerd's profile is loaded
  ([Troubleshooting](#postgres-never-starts-apparmor-stacking)). This is
  checked on this host when the node is this host; otherwise it only warns
  that you must check the node yourself.

Two more checks only warn: client addresses (a public address that is
local but not published by ServiceLB suggests `--node-external-ip=<pub>`),
and ports 6443 or 10250 answering on the public address.

`init` writes the default namespaces. To use other ones, run
`init --env-only --runtime kubernetes --kube-context <ctx>` first, change
`PORTCULLIS_NAMESPACE` or `PORTCULLIS_APPS_NAMESPACE` in `.env`, then run
`init`: the admission bindings follow the apps namespace. The edge and
storage namespaces are fixed.

Then comes the **cluster setup**, idempotent and server-side:

1. the four namespaces with their PSA labels;
2. the storage: the provisioner `portcullis.io/local-path` in
   `portcullis-storage` (its only egress is the API endpoints) and two
   StorageClasses, `portcullis-core` (reclaim `Retain`) and
   `portcullis-apps` (reclaim `Delete`). Volumes live under
   `/var/lib/portcullis-storage` on the node;
3. Traefik's CRDs (the chart's pinned bundle);
4. the admission policies and their params
   ([Security & Hardening → Kubernetes](hardening.md#kubernetes)): new
   bindings are created first and proved live, and only then are the old
   ones removed;
5. a check that `portcullis-edge` holds no Secret.

After that the CLI must prove that the cluster **enforces
NetworkPolicies**: its probe pods, in the namespace
`portcullis-netpol-probe`, need a denied and an allowed connection. Until
the probe passes, nothing is deployed (`NetworkPolicy enforcement isn't
proven (see above): nothing is deployed`). Finally `init` installs the
release and runs the usual steps: Vault, PKI, Keycloak, OIDC clients and
the Hub. Last, it installs **`portcullis-kube-check.timer`**, which
refreshes the cluster check every 6 hours ([Day to day](#day-to-day)).

**Images.** With `PORTCULLIS_KUBE_IMAGES=registry` (the default) every
image is resolved to a digest before anything is deployed, and the release
runs by digest. Core's own images (`group-gate`, `enroll`, `domains`,
`mcp-gate`, `wg`) come from `ghcr.io/porelli/portcullis-<service>`, because
k3s has no image builder. With `local` (CI and development) the CLI builds
them from the checkout with `docker build`, or `podman build --format
docker`, and imports them into k3s's containerd.

## Day to day

The commands are the same as on Docker:

- **`up`** syncs `.env`, the secrets and the config files into Secrets and
  ConfigMaps, re-runs the cluster setup and the NetworkPolicy probe, and
  runs `helm upgrade --install --wait` (up to 10 minutes). Then it writes
  the **cluster check** the Hub reads (the ConfigMap
  `portcullis-cluster-check`: the apps namespace's PSA labels and the
  admission bindings — eleven with high availability's, listed in the
  CLI's `KUBE_BINDINGS`).
- **The cluster check expires.** The Hub refuses every runtime operation
  once the check is more than 24 hours old. `init` installs
  `portcullis-kube-check.timer` (system units, every 6 hours, after
  `k3s.service` when this host runs k3s), which runs
  [`./portcullis kube check`](cli.md#kube-check). Check it with
  `systemctl list-timers portcullis-kube-check.timer`. Without systemd,
  `init` warns: run `./portcullis kube check` from cron at least every
  20 hours.
- **`down`** scales every Deployment of the core and apps namespaces to 0.
  It never runs `helm uninstall`: the release, its PVCs and its Secrets
  stay.
- **`upgrade`** works as on Docker, with the release applied again.
- **`status`** prints `runtime: kubernetes <version> (context <ctx>)`, the
  host checks' warnings and failures, and the core pods. It fails while the
  NetworkPolicy probe isn't proven, an admission binding is missing, an
  app Service has a core Service's name, or a Deployment of the core or
  apps namespace is crashing: a container waiting in `CrashLoopBackOff`,
  `Error` or an image-pull backoff, or restarted in the last 10 minutes and
  not ready again (`kubernetes: <ns>/<deployment> is crashing (<reason>,
  <n> restarts): kubectl -n <ns> logs deploy/<deployment> --previous`). A
  pod list it can't read fails closed. It also warns once the cluster check
  is 20 hours old, and fails when it is missing, failed or 24 hours old.
- The CLI reaches Vault and Keycloak through `kubectl port-forward` on the
  server's loopback. `lldap-ui` is a port-forward to LLDAP's UI.

## Apps on Kubernetes

The Hub judges every template and instance before it deploys it. The
Marketplace card shows **Kubernetes: works**, **limited** or **not
available**, with the reasons in its tooltip, and the instance page lists
them. Creating, restoring into a new id, enabling or restarting an app
that isn't available is refused before anything is created:
`<id> can't run on Kubernetes: <reasons>`. Limited apps run. The reasons
are listed in
[contract §3.4](../guides/integration-contracts.md#34-compose-on-kubernetes-new-kubernetes).

**Today 5 of 51 templates work:** `docs`, `firefox-sync`, `mealie`,
`paperless` and `vikunja` (the templates repo's `tests/runtime.txt`). Most
of the others are refused for one reason only: a service mounts a named
volume but has no numeric `user:`. On Kubernetes a volume is owned by the
service's uid, so such a template needs a `user:` before it can run.
Others use host networking (`netbird`), `extra_hosts` (`ai-chat`,
`headscale`), a non-numeric user (`nextcloud`), or host devices and
`/run/udev` (`scrutiny`, `zigbee2mqtt`).

How the parts of an instance map:

- **Volumes** are PVCs of the StorageClass `portcullis-apps`. The
  provisioner creates each volume's directory with the owner, group and
  mode from the PVC's annotations, and leaves a PVC without valid
  annotations `Pending` (`portcullis-setup REFUSED: <why>` in its log). A
  new PVC is seeded from the image, as Docker seeds a named volume.
- **Template files** become one ConfigMap per instance,
  `<instance>--tpl-<hash>`, mounted read-only.
- **Shared folders** are `hostPath` mounts, only under the bind roots
  (`HUB_OVERRIDE_BIND_ROOTS`). A pod with a host path runs non-root: every
  container needs a numeric user above 0, a group above 0 (never group 0,
  also not as `fsGroup` or a supplemental group) and no privilege
  escalation, and the pod sets `supplementalGroupsPolicy: Strict` (the Hub
  does), so no group from the image's `/etc/group` is added, so a service that binds a shared folder needs a numeric
  non-root `user:`.
- **Published ports** are `LoadBalancer` Services on ServiceLB, with
  `externalTrafficPolicy: Local` and no node port. A **LAN only** port gets
  source ranges from the Local networks' IPv4 entries, and no Service at
  all when there are none. A core port (80, 443, the VPN port, 8000, 8081,
  8443, 8444) is refused.
- **Routes**: the Hub renders an instance's Traefik labels as on Docker and
  converts them into IngressRoutes and Middlewares in `portcullis-edge`.
  App routes are on `websecure` or `vpnsecure` only.
- **Backends**: Traefik can't read the apps namespace, so for each Service
  a route uses the Hub writes an ExternalName Service `<instance>--<svc>`
  in `portcullis-edge`, pointing at exactly
  `<instance>--<svc>.portcullis-apps.svc.cluster.local`, the instance's own
  Service there. Routes name it without a namespace: Traefik runs with
  cross-namespace references off, ExternalName Services on and safe naming
  on, and the edge admission policy admits only that exact shape.
- **Isolation**: each instance gets its own NetworkPolicies (deny by
  default). Routed ports admit only Traefik, an AI companion's port only
  `mcp-gate`, and egress to the internet excludes the cluster's networks
  and the nodes.
- **Backups** in the Hub work as on Docker: the Hub copies a volume
  through a short-lived helper pod and streams it over `exec`.

- **Instance ids** may not contain `--` (on every runtime): it separates
  an instance from its objects' names, so another instance's names could
  otherwise equal this one's.

## Usage on Kubernetes

The Hub's [Usage](hub.md#usage) page reads each app container's CPU and
memory from the cluster's metrics API (metrics-server, which k3s bundles;
the Hub's Role may read pod metrics in the apps namespace, nothing else).
Network, disk IO and processes stay **not measured**: they need
node-level access the Hub is never given. Without metrics-server the page
and the doctor say "the cluster has no metrics API (metrics-server)".
Storage: each volume is measured by a read-only helper pod; writable layers
and images are not measured. The core services show **not measured on
Kubernetes yet** (the Hub has no access to the core namespace).

## The cluster guard

The Hub doesn't trust the cluster until its own checks hold, at start,
every 60 seconds and before every deploy:

1. the in-cluster configuration loads, and the CLI's cluster check says
   `ok` and is at most 24 hours old;
2. its permissions in the apps and edge namespaces are exactly its two
   Roles, and it has nothing in the core namespace;
3. the admission self-test: forbidden objects, dry-run, are each rejected
   by their own binding;
4. its own NetworkPolicy probe: a denied and an allowed connection.

Until all four hold, every runtime operation answers `503 the cluster is
not verified: <why>`. `GET /api/runtime` (admins) shows the context, the
admission result and the probe result
([Hub → Kubernetes](hub.md#kubernetes)).

## VPN

The VPN service works on Kubernetes with the same commands. One `wg` pod
serves every role, NetworkPolicies keep the roles apart, and the built-in
WireGuard port is a LoadBalancer Service. See
[VPN → Kubernetes](vpn.md#kubernetes).

## Moving to Kubernetes

A backup taken on Docker or Podman restores onto Kubernetes (CI tests
Docker → Kubernetes):

1. On the old install, take a backup: `./portcullis backup` (or `--offsite`).
2. Prepare the node as in [Host preparation](#host-preparation), clone core
   and run `./portcullis init --runtime kubernetes --kube-context <ctx>`
   with the same domain.
3. Copy the backup directory over and run
   `./portcullis restore --yes <backup-dir>`, or
   `./portcullis restore --from-offsite`.

`init` must come first: the runtime is never detected as `kubernetes`, and
the restore always keeps this host's `CONTAINER_RUNTIME` and every
`PORTCULLIS_KUBE_*` key ([Backups → Moving between runtimes](backups.md#moving-between-runtimes)).
Check [Apps on Kubernetes](#apps-on-kubernetes) first: an app that isn't
available there can't be started after the move.

## Troubleshooting

### Postgres never starts (AppArmor stacking)

On a host with `kernel.apparmor_restrict_unprivileged_unconfined=1`, k3s's
containerd gives each container a stacked AppArmor label that its profile's
signal rules don't match. Every signal inside a container is denied, and
Postgres, which signals its own processes, never finishes recovery. This is
upstream bug containerd#14485 (k3s#13625). The host checks refuse such a
host with:

```
this cluster isn't ready for Portcullis (docs: operations/kubernetes):
  - kernel.apparmor_restrict_unprivileged_unconfined=1 with containerd's AppArmor profile: containers get a stacked label its signal rules don't match, so signals inside them are denied and Postgres never finishes starting (containerd#14485, k3s#13625). Either run sudo sysctl -w kernel.apparmor_restrict_unprivileged_unconfined=0 and keep it in /etc/sysctl.d/ (this relaxes an Ubuntu hardening for unprivileged profile changes), or wait for a k3s with the fix
```

While containerd's profile isn't loaded yet (k3s loads it when it starts),
the same setting only gets a warning. Portcullis never changes this setting
itself. Pick one:

- **Set the sysctl to 0**, now and at boot. This relaxes an Ubuntu
  hardening that restricts unprivileged processes from changing AppArmor
  profiles:

    ```bash
    sudo sysctl -w kernel.apparmor_restrict_unprivileged_unconfined=0
    echo 'kernel.apparmor_restrict_unprivileged_unconfined = 0' \
      | sudo tee /etc/sysctl.d/60-portcullis-apparmor.conf
    ```

- **Use a k3s release that has the fix**: one whose bundled containerd
  includes the fix for containerd#14485. Then reinstall k3s with the flags
  of [Host preparation](#host-preparation).

Then run `./portcullis init` (or `up`) again.

## Limits

- **Deleting the apps or edge namespace by hand hangs.** The cluster's
  namespace controller isn't exempt from the admission policies, so a
  manual `kubectl delete ns portcullis-apps` (or `portcullis-edge`) waits
  on core's objects there (`portcullis.io/owner: core`, such as
  `default-deny`) until you delete them with the CLI's identity (the
  kubeconfig context in `.env`). No Portcullis command deletes those
  namespaces.

- One node, IPv4 only, k3s as the tested distribution.
- Most marketplace templates are refused today (above).
- No `extra_hosts`, host networking, host devices, `privileged`, TUN or
  `NET_ADMIN`, replicas above 1, or binds outside the shared-folder roots.
- `pids_limit` isn't carried: the kubelet's 1024 per pod applies.
- The VPN's `link` role and VPN-only access to the Kubernetes API aren't
  available.
- `./portcullis backup schedule` still writes units that require
  `docker.service`, and `lldap-ui` still checks for the `docker` command.
  On a host without Docker, schedule `./portcullis backup --offsite` with
  your own timer for now.
