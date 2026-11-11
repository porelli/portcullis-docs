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
*[mtls]: Mutual TLS: the amr of a YubiKey certificate sign-in, and the auth method of apps whose sign-in is a certificate at the TLS handshake
*[mTLS]: Mutual TLS: a certificate presented at the TLS handshake (Portcullis calls them YubiKey and browser certificates)
*[LoA]: Keycloak's Level of Authentication; Portcullis doesn't use levels (sign-in templates decide)
*[acr]: OIDC Authentication Context Class Reference; Portcullis doesn't use it (amr and sign-in templates decide)
*[amr]: Authentication Methods Reference - the sign-in methods used in the session (pwd, spk, dpk, hwk, mtls, file; inv for a setup link)
*[hwk]: amr of a security key passkey (a YubiKey touch)
*[group-gate]: Per-request authorization middleware checking revocation, groups and path groups, then the sign-in template
*[LLDAP]: Light LDAP directory server storing users and groups
*[Keycloak]: Identity provider handling passkeys, YubiKey and browser certificates, and OIDC/SAML
*[Traefik]: Reverse proxy terminating TLS and routing requests by hostname
*[oauth2-proxy]: Forward authentication service redirecting to Keycloak for sign-in
*[OIDC]: OpenID Connect - authentication layer on top of OAuth 2.0
*[SAML]: Security Assertion Markup Language - XML-based SSO protocol
*[PIV]: Personal Identity Verification - YubiKey smartcard standard
*[WebAuthn]: Web Authentication API for FIDO2 passkeys
*[passkey]: FIDO2 credential — a YubiKey or another security key, used for passwordless sign-in
*[FIDO2]: Modern passwordless authentication standard
*[CRL]: Certificate Revocation List - lists revoked YubiKey or browser certificates (one per certificate authority)
*[delta CRL]: Incremental CRL containing only changes since the last full CRL
*[DNS-01]: ACME challenge proving domain control via DNS TXT records
*[ACME]: Automated Certificate Management Environment - protocol for issuing certificates
*[wildcard certificate]: TLS certificate valid for all subdomains (*.domain)
*[policy file]: JSON file (version 6) with the sign-in methods and templates, and full hostnames mapped to templates, groups and expiries
*[public exception]: Unauthenticated paths for share links (off by default)
*[public exceptions]: Unauthenticated paths for share links (off by default)
*[share token]: URL token granting anonymous access to a specific resource
*[share tokens]: URL tokens granting anonymous access to specific resources
*[step-up]: Asking for one more sign-in method (pc_method) when the session doesn't meet the app's template
*[setup link]: One-time invite URL for enrolling a user's first passkey
*[setup links]: One-time invite URLs for enrolling users' first passkeys
*[delegated permission]: Permission granted to non-admins to manage people (edit_details, invite, remove, sign_in_help)
*[delegated permissions]: Permissions granted to non-admins to manage people (edit_details, invite, remove, sign_in_help)
*[edit_details]: Delegated permission to update user profile fields
*[rule-based group]: Group whose membership is computed from user attributes
*[rule-based groups]: Groups whose membership is computed from user attributes
*[added by hand]: In a rule-based group whatever the rule says, through an entry with a reason (and an optional end) set on the group's page
*[kept out]: Left out of a rule-based group although the rule matches, through an entry with a reason (and an optional end) set on the group's page
*[group page]: A group's page on people.<domain> (#groups/<group>), the only place its membership changes
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
*[main domain]: The primary Portcullis domain (PORTCULLIS_DOMAIN)
*[main-domain host]: A hostname under the main domain (<label>.<main domain>)
*[extra-domain host]: A hostname on an added domain
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
*[file-share password]: Per-person SMB password each person creates on My apps after a fresh sign-in; the Hub keeps only its NT hash
*[file-share passwords]: Per-person SMB passwords each person creates on My apps after a fresh sign-in; the Hub keeps only their NT hashes
*[fresh auth]: A new sign-in, with a method the governing template accepts, within the last 5 minutes, proven to the Hub with an ID token
*[router-less]: A custom-auth template with no Traefik router (no web page), such as the SMB file-sharing templates
*[secrets epoch]: Random value the Hub keeps both in state.yaml and on the hub_secrets volume; a mismatch voids every file-share password
*[share slot]: One of the Samba template's eight fixed shared-folder shares (share1–share8)
*[share slots]: The Samba template's eight fixed shared-folder shares (share1–share8)
*[MCP]: Model Context Protocol - how AI clients such as Claude call tools of an app
*[mcp-gate]: Core service that checks every MCP request (token, population, tool policy, limits, confirmations) and forwards it as the person
*[companion]: The MCP server of an app (built in, or the upstream's or a vetted community image) that the AI talks to through mcp-gate
*[companions]: The MCP servers of apps (built in, or upstream or vetted community images) that the AI talks to through mcp-gate
*[AI page]: An ai-chat instance (LibreChat): a chat app whose models come from the admin's providers and whose tools are "all my apps"
*[All my apps]: The one MCP endpoint (https://mcp.<domain>/mcp) that merges every app a person can use with AI, plus their Portcullis account
*[Portcullis MCP]: The Hub's own MCP server: hub.<domain>/mcp for administrators, people.<domain>/mcp for everyone
*[identity mode]: How a person's identity reaches an app's MCP companion: app_token, identity_headers or app_oauth
*[app_token]: AI identity mode: the Hub mints a per-person app credential that mcp-gate injects on every call
*[identity_headers]: AI identity mode: mcp-gate sends the person's identity headers plus a caller secret only the companion knows
*[app_oauth]: AI identity mode: the app is its own MCP OAuth server; mcp-gate is not in the path
*[revoke_all]: AI hook action revoking every Portcullis-minted AI credential of a companion, for every person
*[model provider]: An LLM endpoint (LiteLLM, OpenAI-compatible, Anthropic, OpenAI, Google, Azure OpenAI) an AI page sends chats to
*[PKCE]: Proof Key for Code Exchange - binds an OAuth authorization code to the client that asked for it
*[op record]: Operation record stored per instance (ops/<id>.json) with progress steps, what was created, and the outcome
*[point of no return]: The step after which an operation can no longer be stopped (only delete has one: the first volume removal)
*[sign-in method]: One of six ways to sign in (password, synced passkey, browser certificate, device-bound passkey, security key passkey, YubiKey certificate), switched on or off for the whole server
*[sign-in methods]: The six ways to sign in (password, synced passkey, browser certificate, device-bound passkey, security key passkey, YubiKey certificate), each switched on or off for the whole server
*[sign-in template]: A named rule over sign-in methods (all of / any of, nested), with a score out of 5
*[sign-in templates]: Named rules over sign-in methods (all of / any of, nested), each with a score out of 5
*[pc_method]: Step-up parameter naming the one sign-in method Keycloak should ask for
*[add-stronger]: Settings switch allowing a person to add a stronger sign-in method than the one they signed in with
*[sign_in_help]: Delegated permission to help people reset their sign-in: send a setup link, remove passkeys, revoke certificates (never a password)
*[Sign-in page]: Each person's page for their sign-in methods, certificates and sign-in history, at people.<domain>/signin
*[YubiKey certificate]: A sign-in certificate on a YubiKey (PIV), issued by the internal certificate authority's pki_int; amr mtls
*[YubiKey certificates]: Sign-in certificates on YubiKeys (PIV), issued by the internal certificate authority's pki_int; amr mtls
*[browser certificate]: A sign-in certificate in a .p12 file installed in a browser, issued by the internal certificate authority's pki_file; amr file
*[browser certificates]: Sign-in certificates in .p12 files installed in browsers, issued by the internal certificate authority's pki_file; amr file
*[pki_file]: Vault mount of the browser certificate CA (an intermediate of the internal certificate authority)
*[pki_int]: Vault mount of the YubiKey certificate CA (an intermediate of the internal certificate authority)
*[internal certificate authority]: Portcullis's own CA in Vault (root, pki_int, pki_file) that issues YubiKey and browser certificates
*[Internal certificate authority]: Portcullis's own CA in Vault (root, pki_int, pki_file) that issues YubiKey and browser certificates
*[website certificate]: The HTTPS certificate browsers check (Let's Encrypt), as opposed to YubiKey and browser certificates
*[sign-in history]: A person's sign-ins, step-ups, failures, apps opened and help received, merged from Keycloak events, group-gate's opened log and the Hub's audit
*[added domain]: An extra domain added in Hub Settings → Domains (the domains service manages its records and website certificate)
*[added domains]: Extra domains added in Hub Settings → Domains (the domains service manages their records and website certificates)
