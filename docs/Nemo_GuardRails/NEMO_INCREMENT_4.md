# Increment 4: execution and output validation

Increment 3 was committed as `4ed1404` before this work. Increment 4 is
uncommitted for review on `feature-nemo-guardrails`.

## Implementation

- The only connected agent tool is the read-only `product_catalogue`. Its URL,
  credentials, request ID, and result limit are fixed outside the model; the
  model supplies only a bounded search query. Search rejects non-string queries.
  Unexpected tool names in the execution trace stop response processing.
- Next.js creates a fresh request ID. n8n forwards it to the catalogue service
  through fixed expressions. Client actor and cycle fields are not forwarded,
  and the model is never allowed to select an identity. Catalogue access uses
  the service credential; memory and confirmation retain their user auth checks.
- The catalogue service signs its checked database results using HMAC-SHA256
  with the existing service secret. Evidence expires after five minutes and is
  bound to that request ID. No database or new dependency is needed to store it.
- n8n attaches evidence from actual tool observations, never from model-generated
  response fields. Missing evidence, invalid JSON, and unexpected tools fail.
  The previous permissive response coercion/truncation is removed.
- `/api/guardrails/validate-output` enforces a strict Pydantic schema: allowed
  response types, no extra fields, integer quantities 1–99, bounded arrays,
  confirmation and proposal consistency, and no duplicate or overlapping
  resolved/candidate products. Clarifications require candidates.
- Every structured product ID and name must match signed catalogue evidence
  from this request. Invalid, expired, mismatched, or conflicting evidence is
  rejected. Membership in the database alone is insufficient.
- Recognizable sensitive output and common false completion/allergy guarantee
  phrases are withheld. NeMo also reviews the draft alongside verified facts
  for semantic disclosure, false claims, unsupported price/stock statements,
  and clarification of unresolved choices. A model judgment never authorizes
  a cart, payment, role, or fulfilment mutation.
- Next.js strips evidence before returning the response to the browser. Invalid
  output yields the fixed refusal; a failed validation service yields 503.

The exported JSON schema in `automation/contracts/agent-response.schema.json`
is generated from `AssistantResponse.model_json_schema()`. Required proposal
and candidates fields must be present, using `null` and `[]` when unused.
Candidate quantities are required. This matches the generated system prompt;
older permissively formatted outputs will now be withheld.

## Setup and deployment order

Use the existing increment 3 credentials and URLs. No additional packages or
secrets are required. Restart the backend and frontend, and re-import both the
assistant and semantic-search workflows together into the isolated test workspace.
Re-select credentials after import. The updated workflows require the new
request-ID and evidence fields; do not mix old and new workflow versions.

Regenerate exports with `node automation/scripts/generate-workflows.mjs` after
editing the generator or `automation/scripts/validate-agent-output.js`.

The n8n agent must return intermediate steps. Saved execution payloads remain
disabled; returning steps within this workflow is needed to collect evidence.
The parser accepts JSON tool observations as objects or arrays of objects.
Confirm the actual observation shape after importing into your n8n version;
unsupported shapes fail closed rather than silently dropping evidence.

P0 application authentication is still a separate prerequisite for public
deployment. No changes were made to its branch or either evaluation dataset.

## Verification

Local results: 54 backend, 24 frontend, 13 evaluator, and 7 workflow tests
passed (98 total). Frontend lint and production build passed.

Automated tests cover authentic, tampered, expired, and wrong-request evidence;
invented names; forbidden actions; invalid quantities; extra fields; duplicate
items; missing confirmation; unsafe messages; endpoint validation order; and
the n8n tool allowlist and evidence extraction. Existing backend, frontend,
workflow, and evaluator suites are included in regression checks.

```sh
# Repository root
PYTHONPATH=backend backend/.venv/bin/python -m unittest discover -s backend/tests
backend/.venv/bin/python -m unittest discover -s evals/tests
node --test automation/tests/guardrails.test.mjs
# frontend/
npm test
npm run lint
npm run build
```

Manual checks after import:

1. Request bread: confirm its proposal matches tool-observed ID/name, requires
   confirmation, and contains no evidence token in the browser response.
2. Inject an invented product, changed name, string quantity, or extra action
   into a synthetic draft: expect refusal and no mutation.
3. Reuse an evidence token with another request ID, alter it, or wait over five
   minutes: expect refusal.
4. Inject a mutating tool name or a missing evidence field into a synthetic
   intermediate step: expect the workflow to stop.
5. Request ambiguous milk: expect grounded candidates and a question, followed
   by explicit user selection and confirmation.
6. Simulate false payment/completion claims, allergy guarantees, and private
   contact disclosure: expect withholding. Disable the check service: expect
   a controlled error and continued access to manual shopping.

Live Gemini/n8n execution and the deployed database path remain unverified here.
Unit tests establish validation and wiring, not semantic safety quality. Prose
grounding relies on the model judge; deterministic grounding covers structured
IDs/names. Pattern-based privacy detection is not comprehensive. Evidence proves
which catalogue results were observed, not that the model interpreted the user's
intent correctly. These limitations need the live evaluation in increment 5.
