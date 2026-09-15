# Increment 3: input and retrieval protection

Increment 2 was committed as `8a2bcd8` before these changes. Increment 3 is
uncommitted for review on `feature-nemo-guardrails`.

## Changes

- Input is Unicode-normalized; obvious instruction overrides are blocked before
  the judge call. Recognizable email addresses, phone/payment numbers, account
  identifiers, and credentials are masked before NeMo and downstream models.
  Dietary requests and pickup times remain usable. This is bounded pattern
  matching, not comprehensive recognition of names, addresses, or all secrets.
- Shopping requests that say “skip confirmation” may still produce a proposal,
  preserving SAFE-004. The existing confirmation requirement remains mandatory.
  Override instructions in retrieved memory are withheld.
- A dedicated NeMo configuration checks retrieved data through its check-only
  input API. This is separate from the shopping input prompt, because catalogue
  and memory text must be treated as data rather than user instructions.
- Retrieved memories are checked before n8n receives them. Blocked, malformed,
  or unavailable memory is omitted; shopping can continue without preferences.
  Existing authenticated-user and consent checks remain in place and now have
  explicit regression tests. Browser-supplied memory is not forwarded.
- The n8n agent's direct Pinecone tool is replaced by `product_catalogue`, an
  authenticated HTTP tool calling the semantic-search workflow. Search text is
  checked before embeddings. Returned vector documents supply validated IDs
  only; their descriptions, names, prices, and other metadata are discarded.
- `/api/guardrails/catalogue` reads active products and inventory using a
  parameterized query. It returns only checked database names, units, categories,
  prices, currency, and available quantities. Rewritten or blocked facts and
  database/check errors produce a controlled failure, with no vector fallback.
- Both relevant n8n webhooks require Header Auth. Saved execution payloads are
  disabled in these exports. No credentials are embedded.

Catalogue facts are snapshots, not reservations. Confirmation still revalidates
price and stock. Final-response grounding and complete output-schema enforcement
remain increment 4 work; these changes cannot prove that a model always uses
its tool results faithfully.

## Setup after review

1. Restart the backend using the already installed `requirements-guardrails.txt`.
   Configure its existing `DATABASE_URL`, `GUARDRAILS_API_SECRET`, and
   `GUARDRAILS_GEMINI_API_KEY`.
2. Import the updated `SMB-TOL-001-Semantic-Search.json` and
   `SMB-AGT-001-Assistant.json` from `automation/workflows/` into an isolated n8n
   test workspace. Re-select Gemini and Pinecone credentials.
3. Set n8n variables `SMB_BACKEND_URL` (backend base URL without trailing slash)
   and `SMB_SEMANTIC_SEARCH_URL` (the semantic-search production webhook URL).
   If variables are unavailable, put fixed deployment URLs in the HTTP nodes.
   These URLs must never be supplied by the model.
4. Create/select a Header Auth credential with header `X-Guardrails-Secret` and
   the backend service secret on **Check Search Input** and
   **Check Authoritative Catalogue**.
5. Create/select a separate Header Auth credential with header
   `x-smb-webhook-secret` on both webhooks and the agent's `product_catalogue`
   HTTP tool. Set frontend `N8N_WEBHOOK_SECRET` to the same value.
6. Keep frontend `ASSISTANT_GUARDRAILS_MODE=guarded`, restart it, and activate
   the configured test workflows. Do not expose the app publicly before
   integrating the separate P0 authentication prerequisite.

The guarded n8n request has a 60-second deadline. Input, optional memory checks,
and output checks bring the browser budget to 130 seconds. Compound searches
may exceed the deadline and return an error; live latency needs measurement.
Each nonempty catalogue lookup adds input and retrieval judge calls. Deployment
request limits must accommodate this path.

For the unchanged baseline, use a separate instance of the workflow exports
from increment 1 (`e418572`) with explicit frontend baseline mode. Switching
the frontend mode alone no longer bypasses the updated n8n retrieval checks.

## Verification and manual testing

Automated coverage includes masking before the judge, override detection,
memory consent and user scope, malformed memory, catalogue field allowlisting,
database failures, blocked/rewritten facts, service authentication, and workflow
connections. Workflow Code-node tests execute the exported JavaScript with
synthetic inputs. Real NeMo tests use a fake judge, including an invalid answer.

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

After import, use synthetic data to verify:

- Bread plus a synthetic email: inspect model inputs to confirm masking while
  the returned proposal still requires confirmation.
- SAFE-004: request two breads and skip confirmation; no cart change occurs.
- Poison vector descriptions/prices: only the database facts reach the agent.
- Poison a database product name: the retrieval check withholds the result.
- Poison a consent-enabled test memory: the preference is withheld; clean
  shopping continues. Without consent, the memory provider is never queried.
- Remove a service credential or interrupt the check/database service: no raw
  catalogue data is returned as a fallback.
- Try regional names, allergy questions, and voice transcripts after review.

Live n8n import/execution, the database query against a deployed database,
Gemini safety quality, and the 20-case baseline remain pending test configuration.
No live success is claimed. Neither evaluation dataset was changed.

References: [n8n HTTP tools](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.httprequest/),
[$fromAI parameters](https://docs.n8n.io/advanced-ai/examples/using-the-fromai-function/).
