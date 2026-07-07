# CRITICAL-01 Design Doc: Permission-Aware Retrieval

**Finding:** `source_acl="channel:slack:C-private"` is not enforced. Ask only checks `if acl == "private"`. Channel-scoped content leaks to unauthorized users. Reproduced: executive compensation visible to any user.

**Severity:** CRITICAL (Fortune 100 blocker — data leakage)

**Status:** Design doc — implementation needs integration with provider APIs.

---

## Current State (Verified by Execution)

```python
# ask_pipeline.py:1081 — the ONLY ACL check
acl = getattr(s, "source_acl", "public")
if acl == "private":
    if not user_email:
        continue  # fail-closed
    viewers = s.metadata.get("viewers", [])
    if s.actor != user_email and user_email not in viewers:
        continue  # skip
```

**What this catches:** `"private"` ACL (actor or explicit viewers only).

**What this MISSES:**
- `"channel:slack:C123456"` — Slack channel membership
- `"channel:github:team:engineering"` — GitHub team membership
- `"jira:project:PROJ"` — Jira project access
- `"confluence:space:ENG"` — Confluence space access
- Any non-`"public"`, non-`"private"` ACL value — treated as `public` by default (the opposite of fail-closed)

**Reproduction (executed this session):**
```
source_acl = "channel:slack:C-private"
user_email = "employee@acme.com"  # NOT a member of C-private
→ evidence_count = 1  (LEAKS "Executive compensation is 10M")
```

---

## Proposed Solution: Deny-by-Default ACL Resolution

### Core Principle

**Any ACL that is not exactly `"public"` is deny-by-default.** The system must resolve membership before showing evidence. If membership cannot be verified, the evidence is hidden.

### ACL Types and Resolution Strategy

```python
class ACLResolver:
    """Resolves whether a user can access a signal based on source_acl.

    Deny-by-default: any ACL that is not 'public' requires explicit
    membership verification. If verification fails or is unavailable,
    the signal is hidden (P6: fail-closed).
    """

    def can_access(self, signal: ExecutionSignal, user_email: str) -> bool:
        acl = getattr(signal, "source_acl", "public")

        # Public — anyone can see
        if acl == "public":
            return True

        # Private — actor or explicit viewers
        if acl == "private":
            return self._check_private(signal, user_email)

        # Channel-scoped — requires membership resolution
        if acl.startswith("channel:"):
            return self._check_channel_membership(acl, user_email)

        # Team/project/space-scoped — requires provider API call
        if acl.startswith(("team:", "project:", "space:")):
            return self._check_provider_membership(acl, user_email)

        # Unknown ACL type — DENY (fail-closed)
        logger.warning("Unknown ACL type: %s — denying access (fail-closed)", acl)
        return False

    def _check_private(self, signal, user_email: str) -> bool:
        if not user_email:
            return False  # fail-closed
        viewers = signal.metadata.get("viewers", [])
        return signal.actor == user_email or user_email in viewers

    def _check_channel_membership(self, acl: str, user_email: str) -> bool:
        """Resolve channel membership.

        Format: channel:slack:C123456, channel:github:team:engineering

        Resolution options (in priority order):
        1. Pre-synced membership cache (fast, may be stale)
        2. Live provider API call (slow, always current)
        3. If neither available — DENY (fail-closed)
        """
        parts = acl.split(":", 2)
        if len(parts) < 3:
            return False  # malformed ACL — deny

        provider = parts[1]  # "slack", "github", etc.
        scope_id = parts[2]  # "C123456", "team:engineering", etc.

        # Option 1: check pre-synced membership cache
        if self._membership_cache:
            cache_key = f"{provider}:{scope_id}:{user_email}"
            if cache_key in self._membership_cache:
                return self._membership_cache[cache_key]

        # Option 2: live API call (if provider client available)
        if self._provider_clients and provider in self._provider_clients:
            try:
                return self._provider_clients[provider].check_membership(
                    scope_id, user_email
                )
            except Exception as e:
                logger.warning("Membership check failed for %s: %s — denying", acl, e)
                return False  # fail-closed

        # Option 3: cannot verify — DENY
        logger.info(
            "Cannot verify membership for ACL %s, user %s — denying (fail-closed)",
            acl, user_email,
        )
        return False
```

### Integration Points

#### 1. AskPipeline._search_signals (and _visible_signals)

```python
# CRITICAL-01 fix: replace the simple acl == "private" check
# with full ACL resolution via ACLResolver
from maestro_oem.acl_resolver import ACLResolver

class AskPipeline:
    def __init__(self, ...):
        self._acl_resolver = ACLResolver(
            membership_cache=self._load_membership_cache(),
            provider_clients=self._init_provider_clients(),
        )

    def _user_can_see_signal(self, signal, user_email):
        return self._acl_resolver.can_access(signal, user_email)
```

#### 2. RecallEngine._user_can_see_signal

Same pattern — replace the simple check with `ACLResolver.can_access()`.

#### 3. SituationBuilder (CRITICAL-03 fix)

When building the SituationSnapshot, filter signals through `ACLResolver` first. The snapshot is permission-aware from construction.

#### 4. Whisper generation

Filter signals through `ACLResolver` before generating whispers.

### Membership Cache

The membership cache is a SQLite table synced periodically from provider APIs:

```sql
CREATE TABLE channel_membership (
    provider TEXT NOT NULL,      -- "slack", "github", etc.
    scope_id TEXT NOT NULL,      -- "C123456", "team:engineering"
    user_email TEXT NOT NULL,    -- "alice@acme.com"
    is_member INTEGER NOT NULL,  -- 1 or 0
    synced_at TEXT NOT NULL,     -- ISO timestamp
    PRIMARY KEY (provider, scope_id, user_email)
);
```

Sync strategy:
- On OAuth connection: fetch all channels/spaces/teams for the user
- Periodically (every 1 hour): re-sync membership for active orgs
- On-demand: when an ACL check misses the cache, trigger a live API call + cache the result

### Fallback When No Provider Client

When no provider client is available (dev mode, or provider not connected):
- `"channel:*"` ACLs → DENY (cannot verify membership)
- Log loudly: "Membership cannot be verified — evidence hidden"
- This is P6: fail-closed

---

## Migration Strategy

### Phase 1: ACLResolver + deny-by-default (1 session)

Create `maestro_oem/acl_resolver.py`. Replace the `acl == "private"` check in AskPipeline and RecallEngine with `ACLResolver.can_access()`. Unknown ACL types → deny. Write tests for: public, private, channel-scoped (no cache → deny), channel-scoped (cache hit → allow/deny).

### Phase 2: Membership cache (2 sessions)

Create `ChannelMembershipStore` (SQLite). Add sync logic to OAuthManager: on connection, fetch channel/team membership. Add periodic re-sync. Write tests for cache hit/miss/expiry.

### Phase 3: Live API fallback (2 sessions)

Add `check_membership()` to each provider client (Slack, GitHub, Jira, etc.). Wire into ACLResolver as fallback when cache misses. Write tests with mocked provider APIs.

### Phase 4: Integration test (1 session)

End-to-end: user A in channel C1, user B not in C1. Signal with `source_acl="channel:slack:C1"`. Verify user A sees it, user B doesn't. Verify fail-closed when no provider client.

---

## Risks

1. **Performance:** Live API calls on every ACL check would be too slow. Mitigation: membership cache with 1-hour TTL, on-demand refresh.
2. **Stale cache:** User leaves a channel but cache still shows membership. Mitigation: periodic re-sync + cache TTL. Acceptable risk — better than the current leak.
3. **Provider API rate limits:** Slack/GitHub have rate limits. Mitigation: batch membership checks, cache aggressively.
4. **Dev mode:** No provider clients available. Mitigation: deny-by-default (fail-closed). Dev mode uses `"public"` ACLs only.

---

## Success Criteria

- [ ] `source_acl="channel:slack:C-private"` → denied for non-members
- [ ] `source_acl="channel:slack:C-private"` → allowed for members (via cache or API)
- [ ] Unknown ACL type → denied (fail-closed)
- [ ] No provider client → denied (fail-closed)
- [ ] The audit's reproduction (executive compensation) → denied for `employee@acme.com`
- [ ] Integration test: user A sees channel-scoped evidence, user B does not

## Estimated Effort

6 sessions (4 phases)
