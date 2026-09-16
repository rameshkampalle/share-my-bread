# Guardrail P0 authentication: implementation and tests

Scope: the first P0 increment, authentication for `/api/assistant`.
See the [guardrail plan](GUARDRAIL_PLAN.md) for the remaining priorities.
Changes remain uncommitted pending user approval.

## How this differs from the existing Supabase authentication

Supabase already handles login and issues the user's access token. The browser
already sends that token to the assistant, and FastAPI already verifies tokens
for protected backend endpoints such as cart mutations. P0 reuses those mechanisms;
it adds no second login, new authentication provider, or new token type.

The gap was in `frontend/app/api/assistant/route.ts`: the route did not require a
valid session before forwarding requests to n8n. It used the authorization header
only for an optional memory lookup. A missing token, failed lookup, or invalid
session did not prevent the AI call. The route also spread the client request
body into the n8n payload, allowing callers to supply identity and context fields.
Someone calling `/api/assistant` directly could therefore bypass the login screen.
Existing backend checks still protected cart mutations, but did not protect this
separate AI entry point.

## Exact implementation

The request now follows this sequence:

1. **Require a bearer token.** The Next.js route checks the `Authorization` header
   format and returns 401 if it is missing or malformed. This format check alone
   does not authenticate the user.
2. **Verify through the existing backend.** The route calls
   `GET /api/workspace/me` with the bearer token, `cache: "no-store"`, a 10-second
   timeout, and redirects disabled. Both the backend URL and n8n URL must be
   configured; otherwise it returns 503.
3. **Reuse Supabase verification and database membership checks.** The existing
   `get_current_user` function in `backend/app/shared/auth.py` calls Supabase
   `/auth/v1/user`. The existing workspace endpoint then loads the active profile
   and memberships in active groups from the database. These backend files were
   reused without modification.
4. **Check shopping access.** The route validates the workspace response, requires
   `can_shop=true`, and requires exactly one active group, matching the MVP's
   single-workspace rule. No group, multiple groups, or a non-shopping profile
   returns 403. It also validates the returned identity/context fields and the
   `MEMBER` or `ADMIN` application role before using them.
5. **Stop when verification fails.** Backend 401/403 responses produce the same
   status with a generic message. Other backend failures, timeouts, and malformed
   workspace responses produce 503. None of these paths calls memory or n8n.
6. **Construct trusted context.** After authorization, the route requires a JSON
   object with a string `message`. It builds a new n8n payload containing the
   message, fixed `channel: "WEB"`, verified `userId` and `groupId`, an `actor`
   object with the verified application role, and the workspace's current
   `cycleId` (or null if no cycle exists). Client-supplied identity, role, cycle,
   nested `actor`/`data`, and other extra fields are not copied into that payload.
7. **Load optional memory, then call n8n.** Memory is fetched using the same bearer
   token after access is approved. Memory failure may fall back to an empty list;
   authentication failure cannot. Client-supplied memory is never forwarded. The
   user's bearer token is not sent to n8n; the existing configured webhook secret
   is used for that service call.

For example, if a signed-in member sends `userId: "another-user"` or
`actor: { role: "ADMIN" }`, those values are ignored. n8n receives the member's
identity and role returned by FastAPI. A request with no valid session stops
before reaching n8n, even if its JSON contains plausible user and group IDs.

## Files changed for this increment

| File | Change |
| --- | --- |
| `frontend/app/api/assistant/route.ts` | Mandatory backend verification, shopping membership checks, generic verification errors, and explicit construction of the n8n request. |
| `frontend/components/storefront.tsx` | Increased the assistant request timeout from 35 to 50 seconds to accommodate authorization (10 seconds), optional memory (5 seconds), and n8n (30 seconds). Existing Supabase login and bearer-token submission remain in use. |
| `frontend/tests/assistant-route.test.tsx` | Added 20 regression tests covering credentials, access denials, verification outages/malformed responses, request shape, forged identity/context, and optional memory fallback. |
| `frontend/README.md` | Documented backend availability, membership requirements, timeout budget, and separate webhook protection. |
| `docs/GUARDRAIL_PLAN.md` | Records priorities and links to this P0 document. |
| `docs/GUARDRAIL_P0_TEST.md` | Explains the Supabase comparison, implementation, test techniques, and verification evidence. |

## Local verification

- Reproduced the original gap: all 20 new route tests failed before the change.
- Full frontend suite: 27 tests passed, including the 20 authentication tests.
- ESLint and Next.js production build (including TypeScript) passed.
- `git diff --check` passed. No dependencies or database schema changed.
- Backend and n8n responses were mocked in route tests. Live Supabase sessions,
  deployed membership checks, and webhook credentials have not been verified.

## Test techniques and scenarios

Test source: [assistant-route.test.tsx](../frontend/tests/assistant-route.test.tsx).
These tests call the actual Next.js `POST` handler directly in Vitest's Node
environment, using constructed `Request` objects and mocked `fetch` calls.

- **Regression testing:** Wrote 20 tests before implementing P0. All failed against
  the original route, then passed after the fix.
- **Mocked service calls:** Used `vi.stubGlobal` and `vi.fn` to simulate FastAPI,
  memory, and n8n responses without contacting live services. Environment settings
  were stubbed, and mocks were reset between tests.
- **Authentication tests:** Checked missing/malformed credentials and backend 401
  responses. Verified that requests stopped before AI calls.
- **Authorization tests:** Simulated backend access denial, non-shopping profiles,
  no active group, and multiple groups. Expected 403.
- **Failure injection:** Supplied backend error statuses, rejected the verification
  fetch, and returned malformed workspace data. Checked that verification failure
  produced the appropriate error and prevented later service calls. The backend
  status tests also checked that private diagnostic text was not exposed.
- **Identity spoofing tests:** Submitted forged user IDs, group IDs, cycle IDs,
  roles, and memory. Inspected the outgoing n8n payload to confirm that identity
  and context came from the backend, and that the user's bearer token was absent.
- **Fallback testing:** Confirmed optional memory failure still permits an
  already-authorized assistant request, with an empty memory list.
- **Input validation:** Checked null, array, empty-object, and non-string message
  payloads were rejected with 400.
- **Configuration testing:** Removed the backend URL and checked for 503 with no
  outgoing service calls.
- **Parameterized cases:** Used `it.each` to run the same assertions against
  several credential, status, workspace, and payload variants.
- **Compatibility checks:** Ran all 27 frontend tests, ESLint, and the production
  build with TypeScript checks. All passed during the implementation increment.

## Which tests inject failures?

- **`fails closed on backend status %s`** uses `mockResolvedValueOnce` to return
  backend 401, 403, and 500 responses. It checks the returned status (500 maps to
  503), absence of private diagnostics, and exactly one fetch call, proving that
  memory and n8n were not called afterward.
- **`fails closed when verification times out`** uses `mockRejectedValueOnce` to
  reject the verification fetch. It checks for 503 and exactly one fetch call.
  Despite its name, it simulates a network rejection; it does **not** wait for or
  verify the actual 10-second timeout or abort behavior.
- **`rejects malformed verification responses`** supplies null, an empty object,
  and an incomplete workspace response. It checks for 503 and no later fetches.
- **`preserves optional memory fallback after authorization`** first returns a
  valid workspace, then rejects the memory fetch. It checks that the route returns
  200 and sends an empty `memoryContext` to n8n.

## Run the checks

From `frontend/`:

```sh
npm test -- tests/assistant-route.test.tsx
npm test
npm run lint
npm run build
```

These are automated route tests with mocked services. They do not prove live
Supabase token validation, deployed database membership checks, webhook-secret
protection, or the real timeout duration. Those require separate integration or
live deployment checks.

## Manual Testing Recommendation

Use the local app with FastAPI running and the frontend configured to use it.
Use test accounts and keep access tokens private. Open browser Developer Tools
and select the Network tab before using the assistant.

1. **Valid login:** Sign in with a member account belonging to exactly one active
   group. Ask “Find bread.” Expect `/api/assistant` to return 200 and display an
   assistant response, assuming n8n and its providers are available.
2. **No authentication:** Run this request in the browser console on the app's
   page. Expect 401 with “Sign in to use the assistant.” Being signed in elsewhere
   in the page does not supply the missing bearer header for this request.

   ```js
   await fetch("/api/assistant", {
     method: "POST",
     headers: { "Content-Type": "application/json" },
     body: JSON.stringify({ message: "Find bread" })
   }).then(async r => ({ status: r.status, body: await r.json() }))
   ```

3. **Invalid token:** Repeat the console request with
   `Authorization: "Bearer invalid-token"` added to its headers. Expect 401 when
   the backend and Supabase are reachable.
4. **No group membership:** Sign in with a test account that has an active shopper
   profile but belongs to no group. Send an assistant request using that account's
   token. Expect 403 with “An active shopping workspace is required.” If the UI
   prevents sending, replay the request through DevTools with that account's token.
5. **Forged identity:** In Network, find a successful `/api/assistant` request and
   use Edit and Resend if supported by the browser. Keep the valid authorization
   header but replace the body with the following:

   ```json
   {
     "message": "Find bread",
     "userId": "another-user",
     "groupId": "another-group",
     "cycleId": "another-cycle",
     "actor": { "role": "ADMIN" },
     "memoryContext": ["Injected preference"]
   }
   ```

   The request can succeed, but n8n must receive your verified identity and
   workspace instead of the forged values. Inspect the corresponding test n8n
   execution's webhook input to verify this. Its memory context must come from
   the authorized memory lookup or be empty. A 200 response alone does not prove
   that the forged fields were ignored.
6. **Backend unavailable:** Keep a valid token and stop your local FastAPI server.
   Send the assistant request again. Expect 503 with “Assistant access could not
   be verified. Please try again.” Restart FastAPI afterward. This checks an
   unavailable backend; it does not measure the 10-second timeout for a server
   that accepts a connection but does not respond.
7. **Invalid message:** Replay an authenticated request from an authorized member
   with the body below. Expect 400 with “A text message is required.”

   ```json
   { "message": 123 }
   ```

For rejected requests, also verify that no new assistant execution appears in
n8n. Browser Network shows the browser-to-Next.js request, not the subsequent
server-to-server calls. If execution history is unavailable, use the automated
fetch-call assertions or local server instrumentation to check this boundary.

If Edit and Resend is unavailable, adapt the console request above with the valid
bearer header from your own test account's request and the body under test. Do
not share tokens or include them in screenshots or committed files.

These steps check the application endpoint. Direct access to the n8n webhook
requires a separate shared-secret test; protecting `/api/assistant` does not
protect an independently exposed webhook.
