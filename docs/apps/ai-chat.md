# 💬 AI Chat

> The AI page — chat with all your Portcullis apps, with the models your administrator chose (LibreChat)

**Category:** ai  
**Tags:** `ai`, `chat`, `llm`, `mcp`, `librechat`  
**Website:** <https://www.librechat.ai/>  
**Source:** <https://github.com/danny-avila/LibreChat>

## Authentication

| Property | Value |
|----------|-------|
| **Method** | `native-oidc` |
| **SSO** | :white_check_mark: Yes |
| **Group Access** | :white_check_mark: |
| **Group Admin** | :x: |
| **Access Group** | `users_ai-chat` |
| **Subdomain** | `ai` |

<div class="admonition info">
<p class="admonition-title">Auth Notes</p>
<p>LibreChat 0.8.8, an AI chat for members of <code>users_ai-chat</code>: they sign in through Keycloak and chat with the providers selected on the instance's AI tab, with one MCP server, &quot;All my apps&quot;.</p>
<p><strong>Sign-in:</strong> through Keycloak, OpenID only (no password login, no local sign-up, no password reset).</p>
<ul>
<li>Only members of <code>users_ai-chat</code> get in: the Hub's Keycloak access role refuses everyone else, and LibreChat itself requires the access group in the ID token's <code>groups</code> claim.</li>
<li>Accounts are keyed on the token's <code>sub</code>; the name shown is the LLDAP username.</li>
<li>Nobody is a LibreChat administrator (OpenID accounts are plain users), and the configuration comes only from the Hub.</li>
</ul>
<p><strong>The AI side:</strong> one MCP server, &quot;All my apps&quot; (<code>https://mcp.&lt;domain&gt;/mcp</code>), reached with each person's own OAuth token of the instance's <code>ai-chat-mcp</code> client (scope <code>mcp:all</code>): each person connects once and consents in Keycloak; nobody can add other MCP servers.</p>
<ul>
<li>Nothing a person does makes the server fetch a URL they chose: agents have no actions (OpenAPI calls), web search, code interpreter, file search or OCR, and of LibreChat's built-in tools only the calculator is offered.</li>
<li>Conversations can't be shared (no shared links, public or not), and a link can't submit a prompt by itself.</li>
</ul>
<p><strong>Models:</strong> the providers selected on the instance's AI tab (Hub <strong>Settings → AI</strong>), each shown under its label. Everyone who can open the instance can use every provider selected for it, and what they send, and what their apps return, goes to that provider; give a group other providers with another ai-chat instance and its own access group.</p>
<ul>
<li>Kinds: OpenAI-compatible servers and LiteLLM, OpenAI, Anthropic (LibreChat's native Messages API client), Google (Gemini through Google's OpenAI-compatible API, <code>https://generativelanguage.googleapis.com/v1beta/openai</code> unless the provider sets its own base URL) and Azure OpenAI deployment groups.</li>
<li>AWS Bedrock isn't offered: LibreChat takes Bedrock credentials only from its own fixed variables, never as a configuration reference.</li>
</ul>
<p><strong>Keys</strong> are never written to a file: <code>librechat.yaml</code> holds <code>${VAR}</code> references LibreChat expands from its environment.</p>
<ul>
<li>A provider with per-person keys asks each person for their own key (not possible for Azure OpenAI: the instance refuses to start).</li>
<li>A provider whose key isn't set yet is left out until it is.</li>
</ul>
<p><strong>Upgrades:</strong> LibreChat's <code>api</code> and <code>config</code> services share one image. MongoDB stays on 7.0 (MongoDB 8 refuses Linux kernels 6.19 to 7.0.13); its majors and Meilisearch minors move by hand with LibreChat's own compose file (the search index is rebuilt from MongoDB).</p>
</div>

## Routing

Traefik routers from `compose.yml`. The Hub replaces the TLS tier with the one derived from the app's [access policy](../operations/auth-policies.md#traefik-tls-tier).

| Router | Host | Paths | TLS tier | Forward-auth + group-gate |
|--------|------|-------|----------|---------------------------|
| `ai` | `ai.<domain>` | all | `authaware@file` | :x: |

## AI support

This template is an **AI page**: an MCP client people chat in, connected to "All my apps" as each person. Its models come from the model providers in Hub Settings → AI (see [The AI page](../operations/ai.md#the-ai-page)).

| Provider kind | Per instance |
|---------------|--------------|
| OpenAI-compatible (`openai_compatible`) | several |
| LiteLLM (`litellm`) | several |
| Azure OpenAI (`azure_openai`) | several |
| Anthropic (`anthropic`) | one |
| OpenAI (`openai`) | one |
| Google (`google`) | one |

Not an app the AI acts in: The AI page itself: it is an MCP client, not an app the AI drives.

Why this choice, and what to know: [AI support → AI Chat](../operations/ai.md#ai-ai-chat).

## Images

Pinned by version tag and digest; Dependabot proposes updates.

| Service | Image | Digest |
|---------|-------|--------|
| `api` | `ghcr.io/librechat-ai/librechat:v0.8.8` | `sha256:5b706bcee1ca…` |
| `config` | `ghcr.io/librechat-ai/librechat:v0.8.8` | `sha256:5b706bcee1ca…` |
| `meilisearch` | `getmeili/meilisearch:v1.35.1` | `sha256:8b57fc3c7f46…` |
| `mongodb` | `mongo:7.0.48` | `sha256:9896df581dfd…` |

## Environment Variables

Per-app variables in the generated `.env`; `random` ones are generated by the Hub on first enable:

| Variable | Description | Generation |
|----------|-------------|------------|
| `AI_CHAT_OIDC_SECRET` | LibreChat sign-in client secret (Keycloak client ai-chat) | `random` |
| `AI_CHAT_MCP_SECRET` | Secret of the ai-chat-mcp client (all my apps) | `random` |
| `AI_CHAT_SESSION_SECRET` | LibreChat OpenID session secret | `random` |
| `AI_CHAT_JWT_SECRET` | LibreChat access token signing secret | `random` |
| `AI_CHAT_JWT_REFRESH_SECRET` | LibreChat refresh token signing secret | `random` |
| `AI_CHAT_CREDS_KEY` | First half of LibreChat's credentials encryption key | `random` |
| `AI_CHAT_CREDS_KEY_2` | Second half of LibreChat's credentials encryption key | `random` |
| `AI_CHAT_CREDS_IV` | LibreChat's credentials encryption IV | `random` |
| `AI_CHAT_MONGO_PASSWORD` | MongoDB password | `random` |
| `AI_CHAT_MEILI_MASTER_KEY` | Meilisearch master key | `random` |

## Keycloak Clients

**AI Chat** (`ai-chat`)

Redirect URI: `https://{{HOST_AI}}/oauth/openid/callback`

**AI Chat (all my apps)** (`ai-chat-mcp`)

Redirect URI: `https://{{HOST_AI}}/api/mcp/portcullis/oauth/callback`

## Access URLs

- **AI Chat**: `https://{{HOST_AI}}`
