*[Group Access]: Restricts an instance's hostnames to members of its access group via group-gate
*[Group access]: Restricts an instance's hostnames to members of its access group via group-gate
*[GROUP ACCESS]: Restricts an instance's hostnames to members of its access group via group-gate
*[group_access]: Manifest flag enabling group-gate restriction to the access group
*[Group Admin]: Maps the admin group to the app's admin role
*[Group admin]: Maps the admin group to the app's admin role
*[GROUP ADMIN]: Maps the admin group to the app's admin role
*[group_admin]: Manifest flag enabling admin group mapping
*[access_group]: LLDAP group required for app access (default instance: users_<app>; other instances: users_<instance-id>)
*[admin_group]: LLDAP group granting admin privileges (default instance: admin_<app>; other instances: admin_<instance-id>)
*[path_groups]: Per-path group requirements within an app
*[admin_paths]: App paths requiring admin group membership
*[forward-auth]: Auth method where Traefik delegates authentication to oauth2-proxy and authorization to group-gate
*[header-auth]: Auth method where apps trust identity headers from Traefik
*[native-oidc]: Auth method where apps implement OpenID Connect directly
*[native-OIDC]: Auth method where apps implement OpenID Connect directly
*[mtls]: Mutual TLS authentication using client certificates
*[mTLS]: Mutual TLS authentication using client certificates
*[LoA]: Level of Authentication: 1 = signed in with a passkey or client certificate, 2 = hardware-backed (hwk), 3 = client certificate (mtls)
*[acr]: The requested/achieved LoA in OIDC (hwk, mtls)
*[amr]: Authentication Methods Reference - how the user authenticated (hwk, mtls)
*[hwk]: Hardware key authentication method (passkey/FIDO2)
*[group-gate]: Per-request authorization middleware checking groups, policies, and revocation
*[LLDAP]: Light LDAP directory server storing users and groups
*[Keycloak]: Identity provider handling WebAuthn, X.509, and OIDC/SAML
*[Traefik]: Reverse proxy terminating TLS and routing requests by hostname
*[oauth2-proxy]: Forward authentication service redirecting to Keycloak for sign-in
*[OIDC]: OpenID Connect - authentication layer on top of OAuth 2.0
*[SAML]: Security Assertion Markup Language - XML-based SSO protocol
*[PIV]: Personal Identity Verification - YubiKey smartcard standard
*[WebAuthn]: Web Authentication API for FIDO2 passkeys
*[passkey]: FIDO2 credential — a YubiKey or another security key, used for passwordless sign-in
*[FIDO2]: Modern passwordless authentication standard
*[CRL]: Certificate Revocation List - lists revoked client certificates
*[delta CRL]: Incremental CRL containing only changes since the last full CRL
*[DNS-01]: ACME challenge proving domain control via DNS TXT records
*[ACME]: Automated Certificate Management Environment - protocol for issuing certificates
*[wildcard certificate]: TLS certificate valid for all subdomains (*.domain)
*[policy file]: JSON file (version 5) mapping full hostnames to groups, auth policies, and expiries
*[public exception]: Unauthenticated paths for share links (off by default)
*[public exceptions]: Unauthenticated paths for share links (off by default)
*[share token]: URL token granting anonymous access to a specific resource
*[share tokens]: URL tokens granting anonymous access to specific resources
*[step-up]: Prompting for additional authentication when current session is insufficient
*[setup link]: One-time invite URL for enrolling a user's first passkey
*[setup links]: One-time invite URLs for enrolling users' first passkeys
*[delegated permission]: Permission granted to non-admins to manage people (edit_details, invite, remove)
*[delegated permissions]: Permissions granted to non-admins to manage people (edit_details, invite, remove)
*[edit_details]: Delegated permission to update user profile fields
*[rule-based group]: Group whose membership is computed from user attributes
*[rule-based groups]: Groups whose membership is computed from user attributes
*[tombstone]: Deleted user record preventing name reuse
*[tombstones]: Deleted user records preventing name reuse
*[extra domain]: Additional domain served alongside the primary Portcullis domain
*[extra domains]: Additional domains served alongside the primary Portcullis domain
*[people page]: Users & Groups interface at people.<domain> (any signed-in user)
*[People page]: Users & Groups interface at people.<domain> (any signed-in user)
*[socket proxy]: Docker API gateway that exposes only the endpoints a service needs
*[socket proxies]: Docker API gateways that expose only the endpoints services need
*[instance]: An independent deployment of a template with its own data, settings, and groups
*[instances]: Independent deployments of a template with their own data, settings, and groups
*[default instance]: The instance of a template whose id equals the template id
*[enrolled domain]: Extra domain served by Portcullis with its own wildcard certificate
*[enrolled domains]: Extra domains served by Portcullis with their own wildcard certificates
*[main domain]: The primary Portcullis domain (PORTCULLIS_DOMAIN)
*[main-domain host]: A hostname under the main domain (<label>.<main domain>)
*[extra-domain host]: A hostname on an enrolled domain
*[immutable host]: Host router whose hostname cannot be changed after instance creation
*[host router]: Traefik router with a Host() rule alone, defining an instance hostname
*[access role]: Keycloak client role enforcing access group membership for native-OIDC apps
*[My apps]: Tab on people.<domain> where each person sees their own app settings and enters their own values
*[person-entered]: A setting each person enters for themselves on My apps (scope person_entered)
*[data file]: JSON (or tsv) file the Hub writes for an app's settings and bind-mounts read-only into the app
*[data files]: JSON (or tsv) files the Hub writes for an app's settings and bind-mounts read-only into the app
*[privileged option]: A per-person setting that grants a privilege; per-group values only from groups delegates can't steer
*[privileged options]: Per-person settings that grant a privilege; per-group values only from groups delegates can't steer
*[fixer helper]: Short-lived container the Hub starts from its own image to scan or fix a shared folder's ownership (no network, only the mode's capabilities)
*[LAN only]: A template port that should be reachable only from the local networks; the Hub's doctor judges its binding
*[file-share password]: Per-person SMB password each person creates on My apps after a fresh passkey sign-in; the Hub keeps only its NT hash
*[file-share passwords]: Per-person SMB passwords each person creates on My apps after a fresh passkey sign-in; the Hub keeps only their NT hashes
*[fresh auth]: A new hardware sign-in (passkey or hardware certificate) within the last 5 minutes, proven to the Hub with an ID token
*[router-less]: A custom-auth template with no Traefik router (no web page), such as the SMB file-sharing templates
*[secrets epoch]: Random value the Hub keeps both in state.yaml and on the hub_secrets volume; a mismatch voids every file-share password
*[share slot]: One of the Samba template's eight fixed shared-folder shares (share1–share8)
*[share slots]: The Samba template's eight fixed shared-folder shares (share1–share8)
*[MCP]: Model Context Protocol - how AI clients such as Claude call tools of an app
*[mcp-gate]: Core service that checks every MCP request (token, population, tool policy, limits, confirmations) and forwards it as the person
*[companion]: The MCP server of an app (built in, or the upstream's or a vetted community image) that the AI talks to through mcp-gate
*[companions]: The MCP servers of apps (built in, or upstream or vetted community images) that the AI talks to through mcp-gate
*[AI page]: An ai-chat instance (LibreChat): a chat app whose models come from the admin's providers and whose tools are "all my apps"
