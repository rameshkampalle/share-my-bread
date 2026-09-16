# Increment 2: NeMo input/output integration

The Next.js assistant route now supports two server-configured modes:

- `guarded` (default): input check -> optional memory -> n8n -> output check.
  Missing configuration, malformed decisions, or check failures stop processing.
- `baseline`: explicitly selects the existing unguarded workflow for baseline
  collection. The request body cannot select this mode. Use only in isolated tests.

The P0 branch has not been merged. This increment protects the service-to-service
check endpoint with a secret, but does not replace application authentication.
Integrate P0 before exposing the assistant publicly. Keep the n8n webhook itself
protected; this wrapper cannot prevent direct calls to an exposed webhook.

## Implementation

- `frontend/lib/guardrails.ts` calls `/api/guardrails/check` with a dedicated
  server-only secret. It validates decisions and never sends that secret to n8n.
- `frontend/app/api/assistant/route.ts` checks the message before memory/n8n.
  Checked input replaces the original input; nested client data and actor fields
  are not forwarded in guarded mode. Output checks inspect the entire JSON
  envelope, including candidate and product names. Safe JSON is returned unchanged.
- Rewritten structured output is withheld, not used to alter proposal items.
  Proposals missing confirmation are withheld even if the judge approves them.
- `backend/app/api/guardrails.py` requires the service secret before loading NeMo.
  Input sizes and stages are validated. Responses are not cached.
- `backend/app/services/guardrails.py` loads versioned YAML and injects a Gemini
  judge into the real NeMo `LLMRails` engine. `check_async` checks only the supplied
  message direction; it never runs shopping generation or tools.
- Block decisions produce a fixed structured refusal. Service errors return
  generic 503 responses without raw model output, prompts, or provider diagnostics.
- Optional memory remains untrusted context. Inspecting its retrieval and n8n
  tool execution is increment 3/4 work, not accomplished by this outer wrapper.

The browser timeout is 80 seconds: two checks (up to 20 seconds each), optional
memory (5 seconds), and n8n (30 seconds), plus overhead. The model client has no
retries and a 10-second timeout; each NeMo check has a 15-second deadline. Cold
initialization can exceed the first frontend deadline; warm the service before
rollout. Hosting request-duration limits must support the complete request.

## Configure and run

From `backend/`, using the existing Python 3.12 environment:

```sh
.venv/bin/python -m pip install -r requirements-guardrails.txt
```

Add `GUARDRAILS_API_SECRET`, `GUARDRAILS_GEMINI_API_KEY`, and optionally
`GUARDRAILS_MODEL` to `backend/.env`; see `backend/guardrails/.env.example`.
Set the same secret as `GUARDRAILS_API_SECRET` in `frontend/.env.local`, alongside
`NEXT_PUBLIC_API_BASE_URL` and the existing n8n settings. Set
`ASSISTANT_GUARDRAILS_MODE=guarded` for protected requests. Restart both servers.
Never expose either secret through a `NEXT_PUBLIC_*` variable. The Gemini judge
is separate from n8n generation, although it can use the same model family.

Capture the pending baseline first using an isolated deployment with explicit
`ASSISTANT_GUARDRAILS_MODE=baseline`. Do not present baseline runs as guarded runs.
No real credentials are stored in this change.

## Verification

Local results on 2026-09-15:

- Backend: 34 tests passed, including both real-runtime compatibility tests.
- Frontend: 20 tests passed; lint and production build passed.
- Evaluation runner: 13 tests passed. The existing safety dataset is unchanged.
- After initial package download timeouts, the user installed the pinned
  dependencies in `backend/.venv`; the complete backend suite then passed.
- Live Gemini/n8n checks and baseline collection remain pending credentials.
  Fake-judge runtime checks establish local compatibility, not live safety quality.

```sh
# backend/
.venv/bin/python -m unittest discover -s tests -v
# Optional live Gemini checks: consumes four judge calls, requires a real key.
.venv/bin/python scripts/smoke_guardrails.py

# frontend/
npm test
npm run lint
npm run build
```

`test_guardrails.py` tests service authorization, malformed decisions, errors, and
an actual short timeout against a slow fake. `test_nemo_runtime.py` loads the real
NeMo configuration and executes input/output rails with a deterministic fake LLM;
it skips if optional dependencies are absent. It also constructs the pinned Gemini
client without a network request. When executed successfully, these checks prove
local compatibility and wiring, not the judge's ability to recognize attacks.

`assistant-guardrails.test.tsx` tests the actual Next.js handler with service stubs:
blocked input never reaches n8n; checked text is forwarded; safe proposals retain
their structure; blocked/rewritten output is withheld; errors stop processing.

Live Gemini/n8n verification and the 20-case baseline remain dependent on test
credentials and isolated cloud services. No live safety success is claimed.
Full response schema validation, catalogue grounding, PII masking, and internal
tool/retrieval enforcement belong to subsequent increments.

## Sources checked for this implementation

- [NeMo check-only API](https://docs.nvidia.com/nemo/guardrails/latest/run-guardrailed-inference/using-python-apis/check-messages)
- [Self-check prompts](https://docs.nvidia.com/nemo/guardrails/configure-guardrails/guardrail-catalog/self-check)
- [NeMo package metadata](https://pypi.org/project/nemoguardrails/0.24.0/)
- [Gemini integration package](https://pypi.org/project/langchain-google-genai/4.4.0/)

The runtime dependencies are explicitly pinned in `requirements-guardrails.txt`.
The existing backend requirements remain unchanged; guarded deployments must
install the additional file.
