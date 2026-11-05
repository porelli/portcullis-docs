# File Sharing

Portcullis provides SMB3 file sharing through the Samba and Time Machine templates. Each person creates their own file-share password after a fresh passkey sign-in, sees it once, and can regenerate or revoke it at any time.

## How It Works

- **Per-person passwords:** Each person has their own password for file sharing, separate from their Portcullis sign-in. Admins list and revoke credentials but never create them (an admin who created one would have seen it).
- **Self-service:** People create and regenerate their passwords on [My apps](hub.md#my-apps) (`https://people.<domain>`). A fresh hardware sign-in (passkey touch) is required for each create or regenerate.
- **No web page:** File-sharing apps serve only SMB3 (no HTTP), so they appear without hostnames in the app catalog.
- **Hub-allocated ids:** Each person gets a stable Unix uid (20000–59999), allocated once and never reused. Files land as `<person's uid>:<folder's gid>`.

## Apps

| App | What it serves |
|-----|----------------|
| **Samba** | Eight configurable share slots (readers/writers per slot, each pointing at a shared folder) plus a private Home share per person |
| **Time Machine** | One private backup share per person with a size limit |

Both use hardened SMB3 (encryption required, NTLMv2 only, SMB2 refused) and trust only the Local networks you configure.

## Setup

### 1. Enable Users & Groups

File sharing needs [Users & Groups](../setup/quickstart.md#step-5-create-users): an LLDAP instance and a directory sync interval. Without it, the file-sharing templates don't appear in the catalog.

### 2. Configure Local Networks

File sharing should only be reachable from your LAN or VPN. Go to **Hub → Settings → Local networks** and list the CIDRs that count as local:

- **Default:** RFC 1918 (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), IPv6 ULA (`fc00::/7`) and the Tailscale range (`100.64.0.0/10`).
- **Empty list** (`[]`): loopback only. File sharing then refuses to start (the Hub writes `PORTCULLIS_LOCAL_NETWORKS` empty, and the templates fail closed).

Save the list, and every enabled file-sharing app restarts.

### 3. Create an Instance

Create a Samba or Time Machine instance from the catalog. Give it a name (e.g. `samba-office`) and choose whether to use the default hostname on the main domain or pick an enrolled domain.

File-sharing apps have `instances: multi`, so you can run several Samba or Time Machine instances for different groups.

### 4. Configure It

Each app has settings:

**Samba:**

- **Connect address** (required): the hostname or IPv4 address people connect to (e.g. `nas.home.arpa` or `192.168.1.10`). IPv6 addresses and single-label names like `nas` are refused.
- **Home folders:** the host directory holding each person's private folder (`<username>`, owned by their uid, mode `0700`), shared as `Home`. Empty = a Docker volume.
- **Eight share slots:** for each slot, a [shared folder](hub.md#shared-folders) assignment (the host path), a share name (what people see in `smb://<address>/<name>`), and reader/writer groups (expanded to the members with access to the instance).

**Time Machine:**

- **Connect address** (required): as above.
- **Backup storage:** the host directory holding each person's backup folder. Empty = a Docker volume.
- **Backup size limit:** per person (cooperative: Time Machine prunes to fit).
- **Share name prefix:** each person's share is `<prefix>-<username>` (default `TimeMachine`).

Both apps also have:

- **Username rule:** usernames the app can serve (a pattern plus reserved names). A person whose username fails sees "File sharing isn't available for your username: …" on My apps, with no button.
- **Bonjour (optional):** advertise shares to the local network. Off by default. Enable it by mounting your host's Avahi services directory (e.g. `/var/run/avahi-daemon/services`) and ticking "Advertise". macOS and iOS clients then see the shares in Finder → Network. **Warning:** advertising shows every share name and username to the local network. Turn it off before clearing the Avahi directory.

### 5. Bind the Port

Each app publishes port 445/tcp, marked `lan_only: true`. The Hub's [doctor](hub.md#doctor) warns if the bind makes it reachable from outside your local networks:

- **Bound to `0.0.0.0`:** Warning. The doctor offers a one-click rebind to a LAN address you type.
- **Bound to a public address:** Problem.

Ports on `0.0.0.0` or `::` bypass host firewalls like ufw, so rebind to a LAN address or make sure your router blocks port 445 from the internet.

## Connecting

Once the app is enabled, people visit [My apps](hub.md#my-apps) (`https://people.<domain>`) and:

1. Click [Create password] on the app's card.
2. A popup asks them to touch their passkey (a **fresh** sign-in, even if they signed in seconds ago).
3. The password is shown **once** as 6 groups of 4 characters joined by `-` (29 characters total, e.g. `a2bC-d3eF-g4hJ-…`). The dashes are part of the password.
4. After "I've saved it", the password disappears from the DOM. It is never shown again and never logged.

The card then shows:

- **smb://{connect address}/Home** (Samba)
- **smb://{connect address}/TimeMachine-{username}** (Time Machine)
- **smb://{connect address}/{share name}** (for each Samba share the person may use)

### macOS

1. Open **Finder → Go → Connect to Server** (`⌘K`).
2. Enter the server address: `smb://<address>`.
3. Click **Connect**.
4. Choose **Registered User**, enter your **username** (lowercase, the one shown on My apps) and the **file-share password** (not your Portcullis passkey).
5. Select the share (Home, or the share name).

macOS then mounts it in `/Volumes/<share name>`.

**Time Machine:**

1. Connect to the server as above and mount your share (`TimeMachine-<username>`).
2. Open **System Settings → General → Time Machine**.
3. Click **+** (Add Backup Disk).
4. Select your share.
5. Time Machine keeps backups within the size limit you set in the Hub.

### Windows

1. Open **File Explorer**.
2. In the address bar, type `\\<address>\<share>` (e.g. `\\nas.home.arpa\Home`).
3. Press Enter.
4. Enter your **username** (lowercase) and **file-share password**.
5. Tick **Remember my credentials** if you want Windows to save it.

Windows then shows the share in This PC → Network Locations.

**Mapping a drive letter:**

1. Right-click **This PC** → **Map network drive**.
2. Choose a drive letter.
3. Enter the folder: `\\<address>\<share>`.
4. Tick **Reconnect at sign-in**.
5. Click **Finish** and enter your credentials.

## Managing People

**People should be managed through the Hub's [Users & Groups](hub.md#users-groups-tab), not directly in LLDAP.** Here's why:

- **Hub-made changes** (removing a member, deleting a user or group) revoke file-share passwords **at once**, with no delay.
- **LLDAP-direct changes** (e.g. removing a user from a group in LLDAP's web UI) are caught by the evaluator's 60-second tick. The worst case is **about 60 seconds plus the revocation hook**, measured at 3–9 seconds in CI (contract §13.16, task 18 report). Direct password changes in LLDAP sign the user out of Keycloak but **do not** revoke their file-share password.
- **Writer demoted to reader:** When a Samba share's writer group loses a member or is emptied, that person's write access ends in about **3.6 seconds** (task 18 report).

Revocation always:

1. Removes the hash file from the `hub_secrets` volume.
2. Runs the instance's `credential_change` hook (timeout: 8 seconds). The hook ends the person's open SMB sessions.
3. If the hook times out or the instance isn't running, the Hub stops the app (`compose down`) and starts it again in the background.

## Security

### Password Storage

- **Never in clear text:** The password is shown once, then zeroed in memory. The Hub stores only its **NT hash** (MD4 over the UTF-16LE encoding of the dashed password, as a 32-character hex file).
- **Never logged or backed up:** Neither the password nor the hash appears in `state.yaml`, logs, the audit, hook output, or any backup (instance or core).
- **Secrets volume:** Hashes live on their own volume (`hub_secrets`), never on `hub_data`. It is **not backed up** and is **emptied** by a core restore (`./portcullis restore`).

The passdb and Samba's state directories are on tmpfs (`/var/lib/samba`, `/var/cache/samba`, `/run/samba`, `/run/portcullis`), so no hash ever reaches a Docker volume or an instance backup.

### Hardened SMB

Both templates enforce exactly these settings in `smb.conf` (contracts §13.17):

```ini
[global]
server min protocol = SMB3
server smb encrypt = required
server signing = mandatory
ntlm auth = ntlmv2-only
lanman auth = no
map to guest = never
restrict anonymous = 2
disable netbios = yes
smb ports = 445
wide links = no
hosts allow = <Local networks, space-separated>
hosts deny = 0.0.0.0/0 ::/0
```

And for every share:

```ini
guest ok = no
```

The container exits 4 (restart loop) if `testparm -s` shows any other value, so the image's own config switches are dead. SMB2, NTLMv1, guest access and unencrypted sessions are all refused.

See also [Hardening](hardening.md#file-sharing) for the capabilities and container configuration.

### Hosts Allow and the Userland Proxy

**Residual:** A client whose connection Docker relays through its **userland proxy** arrives from the bridge gateway (inside `172.16.0.0/12`), so it passes `hosts allow` whatever its own address. This happens when:

- An IPv6 client connects to an IPv4-only container, or
- Another container uses the published port.

To avoid it:

- Disable the userland proxy: set `"userland-proxy": false` in `/etc/docker/daemon.json` and restart Docker, or
- Publish only on a LAN address (rebind the port in the Hub), or
- Narrow Local networks to your real LAN (removing `172.16.0.0/12` if your LAN doesn't use it).

**To be verified on the test server (Task 20):** Whether source addresses are preserved for published IPv4 ports.

## Credentials

### Viewing Them

**Admins** see every credential on the instance's File sharing tab (Hub Management):

- **Status:** none, active (with the creation date), voided (by a restore), revoked (self / admin / leave / deleted), or unavailable (username doesn't meet the rule).
- **Person ids:** each person's Unix uid.
- **Per-person values:** their displayed person-scope settings (e.g. the Time Machine size limit).
- **Former members' folders:** top-level directories in per-person trees (Home, Time Machine storage) whose owner isn't the person's current uid, with sizes (or "size unknown").
- **Last sync:** when the revocation hook last ran (ok / skipped / failed).

### Regenerating

A person regenerates their password by clicking [Regenerate] on My apps. The new password replaces the old one **at once**, and their open SMB sessions end. macOS prompts for the new password; running Time Machine backups stop.

### Revoking

- **Self:** A person clicks [Revoke] on their own card. No fresh sign-in needed. Their hash file and metadata go, and the hook ends their sessions.
- **Admin:** An admin clicks [Revoke] on the File sharing tab. Same effect, audited with the admin as actor.
- **Automatic:** The Hub revokes when the person leaves the instance's access group, is removed from a share's reader or writer group, or their account is deleted (reasons: `leave`, `deleted`). These are immediate (Hub-made) or caught within about 60 seconds (LLDAP-direct).

A revoked credential is **destroyed**, not paused. Coming back means creating a new password.

### Restores

- **Instance restore** (`POST /api/instances/{id}/restore`): Every active credential of the instance is voided (`reason: restore`, audited `credential.void_restore` with the count). My apps then shows "Your password was reset by a restore on <date>; create a new one."
- **Core restore** (`./portcullis restore`): The `hub_secrets` volume is **emptied** (removed and re-created with its labels and ownership). The Hub detects it at start via the **secrets epoch** (a random 16-byte value in both `state.yaml` and `<secrets>/.epoch`). Every credential of every instance is voided, every hash file deleted, and every person-id pool's next uid advances by 1000 (so a pool restored from an older `state.yaml` never hands out a uid that files may already carry). People create new passwords on My apps.

Both restores also stop every running app that mounts `hub_secrets` **before** the volume is touched, so a restored start never sees an old hash. The Hub never starts them again (drift shows them down); an admin re-enables them from the Hub.

## Filesystems

Per-person trees (Home, Time Machine storage) and Samba share folders need:

- **Extended attributes:** macOS clients store metadata (Finder tags, resource forks) in `com.apple.*` xattrs.
- **Not NFS, CIFS or FUSE:** The Hub can't keep ownership consistent where a server or VM host decides it, or under virtiofs.

The Hub's [doctor](hub.md#doctor) checks these when you assign a shared folder or run Check path. For Samba shares, it also checks ACL support (needed for the folder's group ownership).

If your folder is **its own filesystem** (a ZFS dataset or btrfs subvolume), the one-click fix can't touch it: the Hub refuses a different mount. **Fix it on the host:** `chown -R <uid>:<uid>` the folder, then `chmod 0700` it, where `<uid>` is the person's id from the File sharing tab.

