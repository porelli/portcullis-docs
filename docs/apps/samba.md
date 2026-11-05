# 📂 Samba

> File sharing over SMB, a home folder per person and up to 8 shared folders, each person with their own file-share password

**Category:** storage  
**Tags:** `files`, `smb`, `samba`, `nas`, `file-sharing`  
**Website:** <https://github.com/ServerContainers/samba>  
**Source:** <https://github.com/ServerContainers/samba>

## Authentication

| Property | Value |
|----------|-------|
| **Method** | `custom` |
| **SSO** | :x: No |
| **Group Access** | :white_check_mark: |
| **Group Admin** | :x: |
| **Access Group** | `users_samba` |

!!! info "Auth Notes"
    No web page: file sharing over SMB. Each member of users_samba creates their own file-share password on My apps (people.<domain>) after a fresh passkey sign-in, and gets the share Home, their own folder <homes>/<username> (owned by their Hub uid, mode 0700). Up to 8 shared folders (slots 1-8): the admin assigns a slot a shared folder (Settings -> Shared folders), a share name and reader and writer groups. Readers can read, writers can also write, nobody else in the instance can open it; files land as <the person's uid>:<the folder's gid> (force group), mode 0660, directories 2770. To share a folder with everyone who has access, pick users_samba as its reader group. The password is shown once; the Hub keeps only its NT hash on the hub_secrets volume, mounted read-only here, never in a backup. Someone who leaves the access group, or whose account is deleted, loses the password at once, and someone who leaves a share's groups loses that share at once: the Hub's hook removes the account or the share and ends their open sessions within seconds (a change made directly in LLDAP within about a minute). Image: ServerContainers samba (smbd-only, Samba 4.23 on Alpine); its /container/scripts/entrypoint.sh never runs, so none of its ACCOUNT_*, GROUP_*, SAMBA_* or AVAHI_* variables does anything (setting one is ignored; an ACCOUNT_* would only put a password in docker inspect). The container starts with portcullis-sync --boot (shared with the Time Machine template), which writes the whole smb.conf, the passdb (smbpasswd on tmpfs) and the Unix accounts from the Hub's people file and hash files, then runit supervises smbd alone (no nmbd, avahi or wsdd2). The image has no default account. SMB is hardened and verified: SMB3 only (3.1.1), encryption and signing required, NTLMv2 only, no guest or anonymous access, no NetBIOS, port 445 only, hosts allow = the Hub's Local networks (an empty list keeps the instance from starting); testparm must show exactly these values or smbd doesn't start. Publish 445 on the LAN or VPN only (lan_only); Docker's published ports bypass ufw. Capabilities: cap_drop ALL, then CHOWN (a new person's home folder is created and given to their uid), SETUID and SETGID (smbd acts as each person with the folder's group; the Hub's files and each folder's size are read as their owner, a privilege drop with runit's chpst instead of DAC_OVERRIDE / DAC_READ_SEARCH, which this container never has) and NET_BIND_SERVICE (port 445). no-new-privileges. The root filesystem isn't read-only: portcullis-sync writes /etc/passwd, /etc/group and /etc/shadow (each person's Unix account and the pfg<gid> group of each shared folder) and the start writes runit's service directory (/run/portcullis-sv); the hashes, the passdb and Samba's state are on tmpfs, and /shares is a small tmpfs, so a slot without a shared folder has nothing to serve. A healthcheck reports unhealthy while smb.conf no longer verifies or smbd isn't running. A home folder that belongs to a former account (an account deleted and created again gets a new uid) is never served; the File sharing tab and the doctor show it. Share names are refused, case-insensitively, when Samba reserves them (global, homes, printers, print$, ipc$, home) or another slot has the same name; the doctor shows it. Bonjour is off by default: people connect with the smb:// address shown on My apps (Finder → Go → Connect to Server). Bonjour opt-in mounts the host's Avahi services directory at /portcullis/avahi and writes portcullis-<instance>.service there, not the image's fixed samba.service (two instances would overwrite each other). Upstream tags name the Alpine and Samba versions (smbd-only-a<alpine>-s<samba>-r<n>): Dependabot follows them.

## Images

Pinned by version tag and digest; Dependabot proposes updates.

| Service | Image | Digest |
|---------|-------|--------|
| `samba` | `ghcr.io/servercontainers/samba:smbd-only-a3.24.3-s4.23.8-r0` | `sha256:04fb3bd3da74…` |

## Settings

Options an admin sets in the Hub's [settings panel](../operations/hub.md#app-settings) (person-entered ones: each person, on [My apps](../operations/hub.md#my-apps)). **Scope** and **Applies** are explained in the [Manifest Reference](../guides/manifest-reference.md#settings).

| Setting | Type | Scope | Applies | Description |
|---------|------|-------|---------|-------------|
| **File-share password** | `person_secret` | per person | `live` | Each person's own password for their Home share and the shared folders they may use, created on My apps. The Hub keeps only its NT hash. |
| **File owner id** | `person_id` | per person | `restart` |  |
| **Home folders** | `path` | instance | `restart` | Host directory holding every person's home folder (&lt;username&gt;, owned by their uid, mode 0700), shared as Home. Empty = a Docker volume. Mounted at `/homes` (rw). [Shared folder](../operations/hub.md#shared-folders) ready: writes as uid each person's (`uid`), gid each person's (`uid`); joins the folder's group itself, from `PORTCULLIS_FOLDER_GID_HOMES`. [Doctor](../operations/hub.md#doctor) check: the filesystem needs `xattr` and not on `nfs`, `cifs`, `fuse` (macOS clients store metadata in extended attributes). |
| **Share 1 folder** | `path` | instance | `restart` | The shared folder slot 1 serves (assign it under Settings → Shared folders). Files are written as each person's uid with the folder's group. Not served without a name and a reader or writer group. Mounted at `/shares/1` (rw). [Shared folder](../operations/hub.md#shared-folders) ready: writes as uid each person's (`uid`), gid ?; joins the folder's group itself, from `PORTCULLIS_FOLDER_GID_SHARE1_FOLDER`. [Doctor](../operations/hub.md#doctor) check: the filesystem needs `xattr`, `acl` and not on `nfs`, `cifs`, `fuse` (macOS clients store metadata in extended attributes; the folder's group needs ACLs). |
| **Share 1 name** | `string` | instance | `live` | The name people see (smb://&lt;address&gt;/&lt;name&gt;). Not global, homes, printers, print$, ipc$ or home, and not another slot's name. |
| **Share 1 readers** | `groups` | instance | `live` | Groups whose members can read share 1. |
| **Share 1 writers** | `groups` | instance | `live` | Groups whose members can read and write share 1. |
| **Share 2 folder** | `path` | instance | `restart` | The shared folder slot 2 serves (assign it under Settings → Shared folders). Files are written as each person's uid with the folder's group. Not served without a name and a reader or writer group. Mounted at `/shares/2` (rw). [Shared folder](../operations/hub.md#shared-folders) ready: writes as uid each person's (`uid`), gid ?; joins the folder's group itself, from `PORTCULLIS_FOLDER_GID_SHARE2_FOLDER`. [Doctor](../operations/hub.md#doctor) check: the filesystem needs `xattr`, `acl` and not on `nfs`, `cifs`, `fuse` (macOS clients store metadata in extended attributes; the folder's group needs ACLs). |
| **Share 2 name** | `string` | instance | `live` | The name people see (smb://&lt;address&gt;/&lt;name&gt;). Not global, homes, printers, print$, ipc$ or home, and not another slot's name. |
| **Share 2 readers** | `groups` | instance | `live` | Groups whose members can read share 2. |
| **Share 2 writers** | `groups` | instance | `live` | Groups whose members can read and write share 2. |
| **Share 3 folder** | `path` | instance | `restart` | The shared folder slot 3 serves (assign it under Settings → Shared folders). Files are written as each person's uid with the folder's group. Not served without a name and a reader or writer group. Mounted at `/shares/3` (rw). [Shared folder](../operations/hub.md#shared-folders) ready: writes as uid each person's (`uid`), gid ?; joins the folder's group itself, from `PORTCULLIS_FOLDER_GID_SHARE3_FOLDER`. [Doctor](../operations/hub.md#doctor) check: the filesystem needs `xattr`, `acl` and not on `nfs`, `cifs`, `fuse` (macOS clients store metadata in extended attributes; the folder's group needs ACLs). |
| **Share 3 name** | `string` | instance | `live` | The name people see (smb://&lt;address&gt;/&lt;name&gt;). Not global, homes, printers, print$, ipc$ or home, and not another slot's name. |
| **Share 3 readers** | `groups` | instance | `live` | Groups whose members can read share 3. |
| **Share 3 writers** | `groups` | instance | `live` | Groups whose members can read and write share 3. |
| **Share 4 folder** | `path` | instance | `restart` | The shared folder slot 4 serves (assign it under Settings → Shared folders). Files are written as each person's uid with the folder's group. Not served without a name and a reader or writer group. Mounted at `/shares/4` (rw). [Shared folder](../operations/hub.md#shared-folders) ready: writes as uid each person's (`uid`), gid ?; joins the folder's group itself, from `PORTCULLIS_FOLDER_GID_SHARE4_FOLDER`. [Doctor](../operations/hub.md#doctor) check: the filesystem needs `xattr`, `acl` and not on `nfs`, `cifs`, `fuse` (macOS clients store metadata in extended attributes; the folder's group needs ACLs). |
| **Share 4 name** | `string` | instance | `live` | The name people see (smb://&lt;address&gt;/&lt;name&gt;). Not global, homes, printers, print$, ipc$ or home, and not another slot's name. |
| **Share 4 readers** | `groups` | instance | `live` | Groups whose members can read share 4. |
| **Share 4 writers** | `groups` | instance | `live` | Groups whose members can read and write share 4. |
| **Share 5 folder** | `path` | instance | `restart` | The shared folder slot 5 serves (assign it under Settings → Shared folders). Files are written as each person's uid with the folder's group. Not served without a name and a reader or writer group. Mounted at `/shares/5` (rw). [Shared folder](../operations/hub.md#shared-folders) ready: writes as uid each person's (`uid`), gid ?; joins the folder's group itself, from `PORTCULLIS_FOLDER_GID_SHARE5_FOLDER`. [Doctor](../operations/hub.md#doctor) check: the filesystem needs `xattr`, `acl` and not on `nfs`, `cifs`, `fuse` (macOS clients store metadata in extended attributes; the folder's group needs ACLs). |
| **Share 5 name** | `string` | instance | `live` | The name people see (smb://&lt;address&gt;/&lt;name&gt;). Not global, homes, printers, print$, ipc$ or home, and not another slot's name. |
| **Share 5 readers** | `groups` | instance | `live` | Groups whose members can read share 5. |
| **Share 5 writers** | `groups` | instance | `live` | Groups whose members can read and write share 5. |
| **Share 6 folder** | `path` | instance | `restart` | The shared folder slot 6 serves (assign it under Settings → Shared folders). Files are written as each person's uid with the folder's group. Not served without a name and a reader or writer group. Mounted at `/shares/6` (rw). [Shared folder](../operations/hub.md#shared-folders) ready: writes as uid each person's (`uid`), gid ?; joins the folder's group itself, from `PORTCULLIS_FOLDER_GID_SHARE6_FOLDER`. [Doctor](../operations/hub.md#doctor) check: the filesystem needs `xattr`, `acl` and not on `nfs`, `cifs`, `fuse` (macOS clients store metadata in extended attributes; the folder's group needs ACLs). |
| **Share 6 name** | `string` | instance | `live` | The name people see (smb://&lt;address&gt;/&lt;name&gt;). Not global, homes, printers, print$, ipc$ or home, and not another slot's name. |
| **Share 6 readers** | `groups` | instance | `live` | Groups whose members can read share 6. |
| **Share 6 writers** | `groups` | instance | `live` | Groups whose members can read and write share 6. |
| **Share 7 folder** | `path` | instance | `restart` | The shared folder slot 7 serves (assign it under Settings → Shared folders). Files are written as each person's uid with the folder's group. Not served without a name and a reader or writer group. Mounted at `/shares/7` (rw). [Shared folder](../operations/hub.md#shared-folders) ready: writes as uid each person's (`uid`), gid ?; joins the folder's group itself, from `PORTCULLIS_FOLDER_GID_SHARE7_FOLDER`. [Doctor](../operations/hub.md#doctor) check: the filesystem needs `xattr`, `acl` and not on `nfs`, `cifs`, `fuse` (macOS clients store metadata in extended attributes; the folder's group needs ACLs). |
| **Share 7 name** | `string` | instance | `live` | The name people see (smb://&lt;address&gt;/&lt;name&gt;). Not global, homes, printers, print$, ipc$ or home, and not another slot's name. |
| **Share 7 readers** | `groups` | instance | `live` | Groups whose members can read share 7. |
| **Share 7 writers** | `groups` | instance | `live` | Groups whose members can read and write share 7. |
| **Share 8 folder** | `path` | instance | `restart` | The shared folder slot 8 serves (assign it under Settings → Shared folders). Files are written as each person's uid with the folder's group. Not served without a name and a reader or writer group. Mounted at `/shares/8` (rw). [Shared folder](../operations/hub.md#shared-folders) ready: writes as uid each person's (`uid`), gid ?; joins the folder's group itself, from `PORTCULLIS_FOLDER_GID_SHARE8_FOLDER`. [Doctor](../operations/hub.md#doctor) check: the filesystem needs `xattr`, `acl` and not on `nfs`, `cifs`, `fuse` (macOS clients store metadata in extended attributes; the folder's group needs ACLs). |
| **Share 8 name** | `string` | instance | `live` | The name people see (smb://&lt;address&gt;/&lt;name&gt;). Not global, homes, printers, print$, ipc$ or home, and not another slot's name. |
| **Share 8 readers** | `groups` | instance | `live` | Groups whose members can read share 8. |
| **Share 8 writers** | `groups` | instance | `live` | Groups whose members can read and write share 8. |
| **Address people connect to** | `string` | instance | `live` | The server's name or IP address on your network, shown on My apps. |
| **Host Avahi services directory (Bonjour)** | `path` | instance | `restart` | For Bonjour advertising: the host's Avahi services directory (usually /etc/avahi/services, writable by root). Empty = no advertising. Turn Advertise off before clearing this setting, or the file stays there. Mounted at `/portcullis/avahi` (rw). [Shared folder](../operations/hub.md#shared-folders) ready: writes as runs as root; the Hub adds the folder's group (`group_add`). |
| **Advertise with Bonjour** | `bool` | instance | `live` | Writes portcullis-&lt;instance&gt;.service into the Avahi directory above so Macs see the server in Finder. Advertising shows the server to everyone on the local network. Turn it off before clearing the directory. Default: `false`. |

## Host Ports

Ports this app binds on the host. Collisions with other enabled apps block enable; each binding can be rebound or disabled from the Hub UI.

| Port | Protocol | Default | Container | Required | Notes |
|------|----------|---------|-----------|----------|-------|
| **SMB** | `tcp` | `445` | `445` | :x: | [LAN only](../operations/hub.md#local-networks): the doctor warns when it is reachable from outside the local networks |
