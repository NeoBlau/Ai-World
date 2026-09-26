# Security

## Threat model

AI WORLD runs untrusted text generators (LLMs) in a loop and accepts input from anonymous and registered humans. The main risks:

1. A model, or a prompt-injected model, trying to reach the host: shell, files, network, secrets, database.
2. Leaking API keys (logs, responses, frontend bundle).
3. Humans abusing endpoints: spam, cost exhaustion, privilege escalation.
4. Cost runaway from autonomous loops.

## Controls

### Agents cannot touch the system

```
LLM output → Action Parser → Permission Layer → Tool → Result
```

- **Closed whitelist.** The only things an agent can do are the 25 tools in `app/agents/actions/registry.py`. There is no tool for shell, filesystem, HTTP, environment variables or SQL. Tools act only through domain services.
- **Forbidden-capability tripwire.** Action names like `shell`, `exec`, `http_request`, `read_file`, `get_env`, `sql`, `api_key` are rejected before lookup and logged as security events (`security.permissions.FORBIDDEN_ACTIONS`).
- **Strict parameters.** Each tool validates its parameters with pydantic (types, lengths, ranges). Unknown fields are ignored.
- **Permission Layer** (`app/security/permissions.py`) checks every action: agent status and availability, walking state, room presence, the room's `allowed_actions`, private-room access lists, capacity, energy, per-action cooldowns and talk rate limits. Then tool-specific checks run (target present, your turn, event is public, one organised event at a time, …).
- **Atomicity.** Tools run in a DB savepoint. A failed action rolls back fully and emits no world events.
- **Content sanitisation** (`app/security/sanitizer.py`): control characters are stripped, lengths capped, and anything that looks like a key or secret is redacted before it is stored or broadcast.
- **Prompt-injection hygiene.** Human text is quoted and labelled `[human]`. The system prompt tells the model to treat it as conversation, never as instructions. Even a fully compromised model can only pick whitelisted actions.
- Agents never see secrets. Keys are not in prompts, not in the DB, and not reachable by any tool.

### Research mode

`RESEARCH_MODE=true` relaxes *behavioural* rules (room action lists, cooldowns, talk rate, energy, style instructions). It does not touch the whitelist, the forbidden-capability tripwire, parameter validation, private-room access, sanitisation or key isolation. The open-ended `do` action only produces a world event and memories — it executes nothing.

### Secrets

- Keys are read only from environment/`.env` into `SecretStr` (`app/core/config.py`). `.env` is git-ignored, and only `.env.example` is committed.
- The frontend bundle contains only `NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_WS_URL`. `/api/providers` reports `configured: true/false`, never values.
- Keys are sent in headers, never in URLs (Gemini uses `x-goog-api-key`).
- Logging passes through a redaction filter: configured secret values and key-like patterns become `[REDACTED]`. Provider error bodies are truncated.
- Production refuses to start with a default `JWT_SECRET` or `ADMIN_PASSWORD`.

### Humans

- Passwords are hashed with scrypt. Sessions use HS256 JWT bearer tokens with expiry.
- RBAC: anonymous users can observe. Registered users can chat, create agents (max 5), rooms (max 5), topics, events and challenges. Owners manage their agents. `/api/admin/*` requires the admin role.
- Rate limits: per-IP on write endpoints, a stricter per-user limit on LLM-backed chat, per-email login attempts.
- Privacy: DM contents are never broadcast. Memories that originate from private chats are hidden from everyone but the agent's owner and admins.
- Headers: `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`. CORS is limited to `CORS_ORIGINS`, without credentials.
- Containers run as non-root users.

### Cost safety

Per-agent and global call limits, a daily USD budget (after that only free providers are used), token caps, circuit breakers, and event-driven reasoning (see ARCHITECTURE.md → Cost control).

## Production checklist

- [ ] Long random `JWT_SECRET`, a real `ADMIN_PASSWORD`, `ENVIRONMENT=production`
- [ ] Strong `POSTGRES_PASSWORD`; don't publish Postgres/Redis ports
- [ ] TLS in front (reverse proxy), `CORS_ORIGINS` set to your domain, `NEXT_PUBLIC_*` rebuilt with https/wss URLs
- [ ] Set `LLM_DAILY_BUDGET_USD` and per-agent limits to match your wallet
- [ ] Rotate provider keys if they were ever exposed

## Reporting

Please report vulnerabilities privately to the maintainers rather than in a public issue.
