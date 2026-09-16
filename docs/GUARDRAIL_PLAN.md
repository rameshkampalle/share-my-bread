# Guardrail implementation plan

Branch: `feature-guardrail`. Commit only after user approval.

The existing boundary remains: AI searches and proposes; FastAPI owns authorization,
stock checks, transactions, and confirmed mutations.

## Priorities

| Priority | Guardrail | Implementation and acceptance criteria |
| --- | --- | --- |
| P0 | Authenticate assistant requests | Require a verified session, active shopper profile, and membership in an active group before invoking n8n. Derive actor and group context server-side. Denied requests never reach AI or memory services. |
| P0 | Limit abuse and AI spend | Shared per-user/IP quotas, bounded request sizes, maximum agent iterations, daily spending limits. Replace per-process voice quotas when scaling. |
| P0 | Validate input and output strictly | One schema across Next.js, n8n, and FastAPI; align quantity limits (workflow currently 9,999 versus API 99); reject malformed responses and unknown fields; avoid raw upstream errors. |
| P1 | Bind confirmation to the exact proposal | Store proposals scoped to user/cycle with items, quoted prices, and expiry; confirm once; changed contents or prices require renewed confirmation. |
| P1 | Strengthen retry protection | Bind idempotency keys to request hashes, reject conflicting reuse, handle simultaneous retries consistently, and protect other consequential mutations. |
| P1 | Contain prompt injection | Restrict model tools to search/proposals; treat catalogue text, memory, and transcripts as data; validate product IDs/names against the catalogue; enforce permissions outside the model. |
| P1 | Gate releases on safety tests | Run safety evaluations in CI. Cover cross-group access, fabricated products, injected instructions, expired proposals, duplicate confirmations, stock races, and provider failure. |
| P2 | Privacy and grocery safeguards | Verify memory consent, retention, and deletion; never invent allergen/dietary claims; clarify when catalogue information is unknown. |

## First increment: P0 authentication

Status: implemented locally; awaiting user review and commit approval.

- Use the existing FastAPI `/api/workspace/me` endpoint to verify the bearer token
  through Supabase Auth and obtain the active profile and active group memberships.
- Require `can_shop=true` and exactly one active workspace, matching the current
  single-workspace MVP. Reject ambiguous membership rather than selecting a group.
- Construct the n8n payload explicitly. Never forward client-supplied user IDs,
  roles, group IDs, cycle IDs, nested actor/data objects, or memory context.
- Derive the actor and current cycle from the verified workspace response.
- Return 401 for missing/invalid sessions, 403 for denied access, and 503 when
  verification is unavailable or malformed. Do not fall back to anonymous access.
- Preserve optional memory fallback only after mandatory authorization succeeds.
- Test the route with mocked backend/n8n responses, then run frontend tests, lint,
  and production build. Live deployment verification remains separate.

This increment does not implement quotas, comprehensive AI response schemas, or
proposal persistence. The n8n webhook must separately enforce its shared-secret
credential; this route does not secure direct access to an unprotected webhook.

## P0 implementation and test details

See [Guardrail P0 authentication: implementation and tests](GUARDRAIL_P0_TEST.md)
for the Supabase authentication comparison, exact implementation, changed files,
test techniques, named failure-injection tests, and local verification results.

## References

- [Supabase: verified user lookup](https://supabase.com/docs/reference/javascript/auth-getuser)
- [OWASP: excessive agency](https://genai.owasp.org/llmrisk/llm062025-excessive-agency/)
