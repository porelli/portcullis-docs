# The Portcullis CLI

`portcullis` is a small command-line tool for macOS, Linux and Windows. With
it you sign in to your Portcullis server once in your browser and get SSH
certificates for the hosts you may reach, loaded into your ssh-agent. Hosts
are set up with the same binary (`portcullis host …`, see
[SSH Access](../operations/ssh-access.md)).

It is not the server CLI: `./portcullis` in the server's checkout is a
different tool, for the people who run the server.

## Install

Download the archive for your system from the
[Hub's GitHub releases](https://github.com/porelli/portcullis-hub/releases)
(the version matching your Portcullis Hub; the people page links to it):
`portcullis_<version>_<os>_<arch>.tar.gz` (`.zip` on Windows), for
`darwin`, `linux` and `windows` on `amd64` and `arm64`. Unpack it and put
`portcullis` on your `PATH`.

### Verify the download

Every release has a `SHA256SUMS` file and a Sigstore bundle per archive:

```
sha256sum --check --ignore-missing SHA256SUMS
cosign verify-blob \
  --bundle portcullis_<version>_linux_amd64.tar.gz.sigstore.json \
  --certificate-identity-regexp '^https://github.com/porelli/portcullis-hub/' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  portcullis_<version>_linux_amd64.tar.gz
```

The archives also carry GitHub build provenance
(`gh attestation verify <archive> -R porelli/portcullis-hub`).

### macOS Gatekeeper and Windows SmartScreen

The binaries are not yet notarized by Apple or signed with Authenticode
(those need developer accounts the project doesn't have yet). So:

- **macOS** may say the app "cannot be opened because the developer cannot
  be verified". After verifying the download as above, remove the quarantine
  flag: `xattr -d com.apple.quarantine ./portcullis`.
- **Windows** SmartScreen may warn about an unrecognised app. After
  verifying the download, choose *More info → Run anyway*.

Only do this for a file whose checksum and signature you verified.

## Sign in

```
portcullis login example.com
```

1. The CLI reads your server's public settings
   (`https://people.example.com/api/cli/v1/config`) and remembers the domain.
2. It opens your browser on the Portcullis sign-in page. Sign in with your
   YubiKey, security key or passkey. You always sign in again here, even if
   your browser already has a session: SSH certificates need a fresh sign-in.
3. The browser says "You can close this tab". The CLI makes a new key in
   memory, gets one certificate per host group, and loads key and
   certificates into your ssh-agent until they expire (8 hours by default).

Then `ssh alice@web-1.example.com` just works.

Options:

| Option | What it does |
|---|---|
| `--method <id>` | ask for one sign-in method, e.g. `--method security_key` when a host group needs a YubiKey |
| `--key <file.pub>` | sign an existing key instead (it must be in your agent), e.g. a FIDO key `~/.ssh/id_ed25519_sk.pub`: then every SSH connection needs a touch |
| `--write-files` | also write the private key (0600) when you have no ssh-agent; it is useless after the certificates expire and `logout` deletes it |
| `--no-browser` | print the sign-in URL instead of opening a browser (open it in a browser on this machine) |
| `--ca-file <pem>` | trust an extra CA, for a test server on staging certificates (or `PORTCULLIS_CA_FILE`); there is no way to skip TLS checks |
| `--domain <d>` | pick one of several configured servers |
| `--debug` | print request lines, with codes and keys redacted |

Exit codes: 0 ok, 1 error, 2 usage, 3 signed in but no certificate issued
(the reasons are printed, e.g. "prod needs a YubiKey: sign in with --method
security_key"), 4 refused, 5 Portcullis unreachable.

## Other commands

| Command | What it does |
|---|---|
| `portcullis status` | the certificates in your agent: host group, principals, expiry, key type (no network) |
| `portcullis logout [--revoke]` | removes the Portcullis keys from your agent and deletes the written files; `--revoke` also revokes this login's certificates (needs a fresh sign-in) |
| `portcullis ssh-config [--install]` | prints, or adds after a y/N question, `Include ~/.ssh/portcullis/*/config` to `~/.ssh/config` |
| `portcullis open [<name>]` | opens `https://<name>.<domain>/` (or the portal) in your browser |
| `portcullis version` | the version and API version (no network) |

## What it writes

- `~/.ssh/portcullis/<domain>/` (0700): `id.pub`, one `<host group>-cert.pub`
  per certificate, `known_hosts` (the server's host CA, scoped to each
  group's names) and `config` (one `Match host …` block per host group).
- Your settings in your user config directory, `portcullis/config.json`
  (0600, no secrets).
- **Nothing secret**: no token, no password, and no private key unless you
  asked for `--write-files`. The CLI talks only to your Portcullis server and
  its own `127.0.0.1` listener: no telemetry, no update checks.

Run `portcullis ssh-config --install` once so `ssh` reads the written config.

## Browser sessions and cookies (FAQ)

**Does `portcullis login` sign my browser in too?** Yes, the browser you
signed in with keeps its Portcullis session, so opening apps afterwards
(`portcullis open grafana`) is silent when the session meets their rules.

**Can the CLI put a session into another browser or profile, or give a
script my cookie?** No, by design. Browsers keep their cookie jars apart,
and the Portcullis cookie is a ticket for every app on the domain that can't
be limited to one. Handing it to scripts would make it something to steal.

**Can it sign me in to apps with their own login (Gitea, Nextcloud…)?** No:
those keep their own sessions. Use their own API tokens.
