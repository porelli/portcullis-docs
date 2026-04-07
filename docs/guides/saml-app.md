# SAML Integration

This guide shows how to integrate a SAML-capable application with Portcullis, using Nextcloud as a worked example. The same pattern applies to any app that supports SAML 2.0.

## Overview

```
User (YubiKey) --> Traefik --> App
                                |
                                v  SAML SSO
                             Keycloak (IdP)
                                |
                                v  user lookup
                              LLDAP
```

The user authenticates at the Traefik layer (via mTLS or WebAuthn). The app then uses SAML to verify the user's identity via Keycloak, which looks up users in LLDAP.

## Step 1: Deploy the App

Create a Docker Compose file for the app (or use its template from the catalog). The key Traefik labels are:

```yaml
services:
  nextcloud:
    image: nextcloud:29-apache
    environment:
      NEXTCLOUD_ADMIN_USER: admin
      NEXTCLOUD_ADMIN_PASSWORD: ${NEXTCLOUD_ADMIN_PASSWORD:-changeme}
      NEXTCLOUD_TRUSTED_DOMAINS: "nextcloud.${PORTCULLIS_DOMAIN}"
    networks:
      - portcullis
    labels:
      traefik.enable: "true"
      traefik.http.routers.nextcloud.rule: "Host(`nextcloud.${PORTCULLIS_DOMAIN}`)"
      traefik.http.routers.nextcloud.entrypoints: websecure
      traefik.http.routers.nextcloud.tls.options: authaware@file
      traefik.http.routers.nextcloud.middlewares: security-headers@file
      traefik.http.services.nextcloud.loadbalancer.server.port: "80"

networks:
  portcullis:
    external: true
```

Note: SAML apps handle their own authentication flow with Keycloak, so they do not need the `portcullis-auth@docker` forward-auth middleware.

## Step 2: Register the App as a SAML Client in Keycloak

### 2a. Open Keycloak Admin

Navigate to `https://auth.<your-domain>/admin/` and log in with your admin credentials. Select the **portcullis** realm from the dropdown.

### 2b. Create a New SAML Client

1. Navigate to **Clients** and click **Create client**
2. Set:
   - **Client type**: SAML
   - **Client ID**: `https://nextcloud.<your-domain>/apps/user_saml/saml/metadata`
   - Click **Next**
3. On the next screen:
   - **Name**: Nextcloud
   - **Root URL**: `https://nextcloud.<your-domain>`
   - **Valid redirect URIs**: `https://nextcloud.<your-domain>/*`
   - Click **Save**

### 2c. Configure SAML Settings

In the client settings, go to the **Settings** tab:

- **Name ID format**: username
- **Force name ID format**: ON
- **Sign assertions**: ON
- **Signature algorithm**: RSA_SHA256
- **SAML signature key name**: KEY_ID

Go to the **Keys** tab:

- **Client signature required**: OFF (unless the app is configured to sign requests)

### 2d. Add Attribute Mappers

Go to **Client scopes**, click the client's dedicated scope, then **Add mapper** and select **By configuration**:

**Email mapper:**

- Mapper type: User Property
- Name: `email`
- Property: `email`
- SAML Attribute Name: `urn:oid:0.9.2342.19200300.100.1.3`
- SAML Attribute NameFormat: URI Reference

**Username mapper:**

- Mapper type: User Property
- Name: `username`
- Property: `username`
- SAML Attribute Name: `urn:oid:0.9.2342.19200300.100.1.1`
- SAML Attribute NameFormat: URI Reference

**Display name mapper:**

- Mapper type: User Property
- Name: `displayName`
- Property: `firstName`
- SAML Attribute Name: `urn:oid:2.16.840.1.113730.3.1.241`
- SAML Attribute NameFormat: URI Reference

### 2e. Note the IdP Metadata URL

You will need this when configuring the app:

```
https://auth.<your-domain>/realms/portcullis/protocol/saml/descriptor
```

## Step 3: Configure the App for SAML

This section uses Nextcloud as an example. Adapt the field names for your specific app.

### 3a. Enable the SAML Plugin

In Nextcloud, enable the **SSO & SAML authentication** app:

```bash
docker compose exec nextcloud php occ app:enable user_saml
```

### 3b. Configure SAML Settings

In Nextcloud's **Administration settings** under **SSO & SAML authentication**:

**General:**

- **Attribute to map the UID to**: `urn:oid:0.9.2342.19200300.100.1.1`

**Identity Provider Data:**

- **Identifier of the IdP entity**: `https://auth.<your-domain>/realms/portcullis`
- **URL target of the IdP where the SP will send the Authentication Request**: `https://auth.<your-domain>/realms/portcullis/protocol/saml`
- **URL Location of IdP where the SP will send the SLO Request**: `https://auth.<your-domain>/realms/portcullis/protocol/saml`
- **Public X.509 certificate of the IdP**: Download from the SAML descriptor URL (Step 2e), extract the `<ds:X509Certificate>` value, and paste it

**Service Provider Data:**

- **Identifier of the SP entity**: `https://nextcloud.<your-domain>/apps/user_saml/saml/metadata`

**Attribute mapping:**

- **Attribute to map the displayname to**: `urn:oid:2.16.840.1.113730.3.1.241`
- **Attribute to map the email address to**: `urn:oid:0.9.2342.19200300.100.1.3`

### 3c. Test SAML Login

1. Open a private/incognito window
2. Go to `https://nextcloud.<your-domain>`
3. You should see a "Login with SSO" button or be redirected automatically
4. Keycloak authenticates via WebAuthn (or client certificate if mTLS is enabled)
5. You are logged into the app

## Step 4: Optional -- LDAP User Backend

For richer user integration (groups, quotas, etc.), you can also configure the app's LDAP backend to read from LLDAP directly:

| Setting | Value |
|---------|-------|
| **Host** | `lldap` (Docker service name) |
| **Port** | `3890` |
| **User DN** | `uid=admin,ou=people,<your-base-dn>` |
| **Password** | Your LLDAP admin password |
| **Base DN** | Your `LLDAP_BASE_DN` value |
| **User object class** | `person` |
| **Username attribute** | `uid` |
| **Email attribute** | `mail` |
| **Group object class** | `groupOfUniqueNames` |

This way, users and groups from LLDAP appear directly in the app, while SAML handles the authentication flow.

## General SAML Pattern

The same steps apply to any SAML-capable application:

1. Deploy the app behind Traefik (no forward-auth middleware needed)
2. Create a SAML client in Keycloak with the app's entity ID and ACS URL
3. Configure attribute mappers for email, username, and display name
4. Point the app's SAML settings at Keycloak's IdP metadata
5. Test the SSO flow

## Troubleshooting

### "Invalid signature" on SAML response

- Ensure the IdP certificate in the app matches the one from Keycloak's SAML descriptor
- Check that "Sign assertions" is ON in the Keycloak client config

### User not found after SAML login

- Verify the UID attribute mapping matches between Keycloak and the app
- Check that the user exists in LLDAP and has synced to Keycloak (Keycloak admin panel, Users, search for the username)

### SAML loop / redirect issues

- Ensure the app's trusted domains configuration includes your full domain
- Check that the entity ID in Keycloak matches exactly what the app sends
- Verify the ACS URL is correct in Keycloak's Valid Redirect URIs

### Mixed content / proxy issues

For apps behind a reverse proxy, you typically need to configure the app to know it is behind HTTPS. For Nextcloud, add to `config.php`:

```php
'overwriteprotocol' => 'https',
'overwrite.cli.url' => 'https://nextcloud.<your-domain>',
'trusted_proxies' => ['172.16.0.0/12', '10.0.0.0/8'],
```

Other apps have similar settings (e.g., `FORCE_HTTPS`, `TRUST_PROXY`, `SECURE_PROXY_SSL_HEADER`).
