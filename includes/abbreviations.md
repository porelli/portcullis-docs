*[Group Access]: Restricts app hostnames to members of the access group via group-gate
*[Group access]: Restricts app hostnames to members of the access group via group-gate
*[GROUP ACCESS]: Restricts app hostnames to members of the access group via group-gate
*[group_access]: Manifest flag enabling group-gate restriction to the access group
*[Group Admin]: Maps the admin group to the app's admin role
*[Group admin]: Maps the admin group to the app's admin role
*[GROUP ADMIN]: Maps the admin group to the app's admin role
*[group_admin]: Manifest flag enabling admin group mapping
*[access_group]: LLDAP group required for app access (default: users_<app>)
*[admin_group]: LLDAP group granting admin privileges (default: admin_<app>)
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
*[Traefik]: Reverse proxy terminating TLS and routing requests by subdomain
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
*[policy file]: JSON file mapping subdomains to groups, auth policies, and expiries
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
