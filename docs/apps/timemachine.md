# 🕰 Time Machine

> Mac backups over SMB, one backup share per person with their own file-share password

**Category:** storage  
**Tags:** `backup`, `time-machine`, `macos`, `smb`, `samba`  
**Website:** <https://github.com/mbentley/docker-timemachine>  
**Source:** <https://github.com/mbentley/docker-timemachine>

## Authentication

| Property | Value |
|----------|-------|
| **Method** | `custom` |
| **SSO** | :x: No |
| **Group Access** | :white_check_mark: |
| **Group Admin** | :x: |
| **Access Group** | `users_timemachine` |

<div class="admonition info">
<p class="admonition-title">Auth Notes</p>
<p>No web page: file sharing over SMB. Each member of <code>users_timemachine</code> creates their own file-share password on My apps and gets one Time Machine share in their own folder.</p>
<p><strong>People and shares:</strong> each member of <code>users_timemachine</code> creates their own file-share password on My apps (<code>people.&lt;domain&gt;</code>) after a fresh passkey sign-in, and gets one Time Machine share, <code>&lt;prefix&gt;-&lt;username&gt;</code>, in their own folder <code>&lt;storage&gt;/&lt;username&gt;</code> (owned by their Hub uid, mode 0700).</p>
<p><strong>Passwords:</strong> the password is shown once. The Hub keeps only its NT hash on the <code>hub_secrets</code> volume, mounted read-only here, never in a backup. Someone who leaves the access group, or whose account is deleted, loses the password at once: the Hub's <code>credential_change</code> hook removes the account and ends their open sessions within seconds (a removal made directly in LLDAP within about a minute).</p>
<p><strong>Image:</strong> mbentley/timemachine (smb variant, Samba 4.23 on Alpine). Its <code>/entrypoint.sh</code> never runs. The container starts with <code>portcullis-sync --boot</code> (shared with the Samba template), which writes the whole <code>smb.conf</code>, the passdb (smbpasswd on tmpfs) and the Unix accounts from the Hub's people file and hash files; then s6 supervises smbd alone (no nmbd, avahi or dbus). The image's default <code>timemachine</code> account is never created.</p>
<p><strong>SMB is hardened and verified:</strong> SMB3 only (3.1.1), encryption and signing required, NTLMv2 only, no guest or anonymous access, no NetBIOS, port 445 only, <code>hosts allow</code> = the Hub's Local networks (an empty list keeps the instance from starting). <code>testparm</code> must show exactly these values or smbd doesn't start. Publish 445 on the LAN or VPN only (<code>lan_only</code>); Docker's published ports bypass ufw.</p>
<p><strong>Capabilities:</strong> <code>cap_drop: ALL</code>, then:</p>
<ul>
<li><code>CHOWN</code>: a new person's folder is created and given to their uid.</li>
<li><code>SETUID</code> and <code>SETGID</code>: smbd acts as each person; the Hub's files and each folder's size are read as their owner, a privilege drop instead of <code>DAC_OVERRIDE</code> / <code>DAC_READ_SEARCH</code>, which this container never has.</li>
<li><code>NET_BIND_SERVICE</code>: port 445.</li>
</ul>
<p><code>no-new-privileges</code>. The root filesystem isn't read-only: <code>portcullis-sync</code> writes <code>/etc/passwd</code>, <code>/etc/group</code> and <code>/etc/shadow</code> (each person's Unix account) and the start writes its copy of <code>/etc/s6</code> (<code>/run/portcullis-s6</code>). The hashes, the passdb and Samba's state are on tmpfs. A healthcheck reports unhealthy while <code>smb.conf</code> no longer verifies or smbd isn't running.</p>
<p><strong>Backup size limit:</strong> Time Machine keeps backups within it (Samba's <code>fruit:time machine max size</code>, cooperative, not a hard quota).</p>
<p>A folder that belongs to a former account (an account deleted and created again gets a new uid) is never served; the File sharing tab and the doctor show it.</p>
<p><strong>Bonjour</strong> is off by default: people connect with the <code>smb://</code> address shown on My apps (Finder → Go → Connect to Server, then System Settings → Time Machine → Add Backup Disk).</p>
<p><strong>Updates:</strong> upstream tags are dated (<code>smb-YYYYMMDD</code>); Dependabot follows the digest.</p>
</div>

## AI support

**No AI support:** Serves files to people's computers over SMB; there is no app API for an AI to act through.

## Images

Pinned by version tag and digest; Dependabot proposes updates.

| Service | Image | Digest |
|---------|-------|--------|
| `timemachine` | `mbentley/timemachine:smb-20261104` | `sha256:0085d47ff4ee…` |

## Settings

Options an admin sets in the Hub's [settings panel](../operations/hub.md#app-settings) (person-entered ones: each person, on [My apps](../operations/hub.md#my-apps)). **Scope** and **Applies** are explained in the [Manifest Reference](../guides/manifest-reference.md#settings).

| Setting | Type | Scope | Applies | Description |
|---------|------|-------|---------|-------------|
| **File-share password** | `person_secret` | per person | `live` | Each person's own password for their Time Machine share, created on My apps. The Hub keeps only its NT hash. |
| **File owner id** | `person_id` | per person | `restart` |  |
| **Backup size limit** | `size` | per person | `live` | Time Machine keeps backups within this size (not a hard quota). Default: `500GiB`. [Doctor](../operations/hub.md#doctor) check: a group row should set it (Most people should get a deliberate limit). |
| **Backup storage** | `path` | instance | `restart` | Host directory holding every person's backup folder (&lt;username&gt;, owned by their uid, mode 0700). Empty = a Docker volume. Mounted at `/opt` (rw). Per-person folders: writes as each person's own uid (`uid`) and private group (`uid`); one `<username>` folder per person, mode `0700` (it can't be a [shared folder](../operations/hub.md#shared-folders)). [Doctor](../operations/hub.md#doctor) check: the filesystem needs `xattr` and not on `nfs`, `cifs`, `fuse` (Time Machine stores metadata in extended attributes). [Doctor](../operations/hub.md#doctor) check: no other app may write the same folder (Backup bundles must not be written by other apps). |
| **Share name prefix** | `string` | instance | `live` | Each person's share is &lt;prefix&gt;-&lt;username&gt;. Default: `TimeMachine`. |
| **Address people connect to** | `string` | instance | `live` | The server's name or IP address on your network, shown on My apps. |
| **Host Avahi services directory (Bonjour)** | `path` | instance | `restart` | For Bonjour advertising: the host's Avahi services directory (usually /etc/avahi/services, writable by root). Empty = no advertising. Turn Advertise off before clearing this setting, or the file stays there. Mounted at `/portcullis/avahi` (rw). [Shared folder](../operations/hub.md#shared-folders) ready: writes as root; the Hub adds the folder's group (`group_add`). |
| **Advertise with Bonjour** | `bool` | instance | `live` | Writes portcullis-&lt;instance&gt;.service into the Avahi directory above so Macs see the shares in Finder and Time Machine. Advertising shows every share name, which contains usernames, to everyone on the local network. Turn it off before clearing the directory. Default: `false`. |
| **Shown in Finder as** | `enum` | instance | `restart` | Choices: `TimeCapsule8,119`, `MacPro7,1`. Default: `TimeCapsule8,119`. |

## Host Ports

Ports this app binds on the host. Collisions with other enabled apps block enable; each binding can be rebound or disabled from the Hub UI.

| Port | Protocol | Default | Container | Required | Notes |
|------|----------|---------|-----------|----------|-------|
| **SMB** | `tcp` | `445` | `445` | :x: | [LAN only](../operations/hub.md#local-networks): the doctor warns when it is reachable from outside the local networks |
