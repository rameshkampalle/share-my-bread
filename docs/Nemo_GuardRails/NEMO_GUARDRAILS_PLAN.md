# NeMo guardrails implementation plan

Branch: `feature-nemo-guardrails`, based on `main`. The P0 authentication work
remains on `feature-guardrail`; it is not included in this branch. Commit only
after user approval. Authentication must be integrated before production rollout.

## Increment 1: policies and baseline evaluations

Define the application's AI behavior policy and create a separate NeMo safety dataset
with attacks and legitimate shopping requests. Each case specifies expected
response types, allowed/required tools, forbidden outcomes, fixtures, and semantic
review criteria. Add an offline evaluator for captured responses and reviewed
traces. Run the current assistant on the fixed cases to establish a baseline.

Deliverables: `NEMO_GUARDRAILS_POLICY.md`, `evals/datasets/nemo-guardrails.jsol`,
`evals/safety_runner.py`, runner tests, and reproducible evaluation instructions.
The runner must never count missing evidence as success. This increment does not
install NeMo or enable blocking in the live request path.

Current status: policy, 20 cases, offline evaluator, and runner unit tests are
implemented. Live baseline collection is pending a test endpoint, synthetic
account, and access to model/tool traces and isolated database state. No live
baseline or NeMo compatibility result is claimed.

## Increment 2: NeMo integration boundary and compatibility proof

Implementation and setup: [NEMO_INCREMENT_2.md](NEMO_INCREMENT_2.md).
The input/output integration is implemented with 67 automated tests passing,
including both real NeMo runtime compatibility tests. Live provider checks
remain pending configuration.

Verify the selected NeMo version against Gemini and the n8n workflow before
pinning dependencies. Keep the current model if supported. Implement a server-side
Python guardrail module and version-controlled NeMo configuration. Test a small
input/output check end to end before introducing additional rails.

Target flow:

```text
Authenticated request -> input rails -> n8n assistant
  -> checked retrieval/tool calls -> output rails -> proposal review
  -> existing FastAPI confirmation endpoint
```

Mandatory rail failure returns a controlled error. Manual catalogue shopping
remains available. Never fall back silently to an unguarded AI response.

## Increment 3: input and retrieval rails

- Detect override, secret-disclosure, and confirmation-bypass requests.
- Mask unnecessary sensitive data before model calls; allow legitimate dietary
  questions and authorized pickup information.
- Refuse harmful assistance; apply the same policy to text and voice transcripts.
- Check catalogue results inside n8n before adding them to model context.
- Treat product descriptions and memories as untrusted data, not instructions.
- Scope memory by the authenticated user and consent.
- Obtain current prices/stock from authoritative backend tools; vector metadata
  alone cannot support these claims.

## Increment 4: execution and output rails

- Allowlist tools and validate arguments; derive identity outside the model.
- Keep price, role, cash, fulfilment, and direct cart mutations unavailable to AI.
- Validate full output schemas and ground product IDs/names in retrieved evidence.
- Require confirmation on proposals and clarify unresolved product ambiguity.
- Block false action-completion claims, unsupported allergen guarantees, and
  unauthorized disclosure.
- Use deterministic validators for schemas and permissions; model-based checks
  support semantic review but never authorize actions.

## Increment 5: evaluate and release gradually

Run the same versioned cases before and after rails, using the same model,
catalogue, fixtures, and account scope. Inspect tool calls and state changes as
well as responses. Report unsafe outcomes, false refusals, latency, and extra
model cost. Exercise rail and provider outages. Add deterministic checks to CI
and a separately controlled live evaluation. Document manual testing and gaps.
Enable gradually after review, with an AI-disable switch preserving manual
shopping. Merge/integrate the P0 authentication prerequisite before deployment.

## Acceptance and review

No observed forbidden effect may pass. Every case needs complete evidence and
semantic review; a correct response type alone is insufficient. Keep baseline
and guarded runs separate. Use synthetic data and exclude credentials from
artifacts. The existing legacy `expectedResponseType` remains for compatibility;
new evaluations use `expectedResponseTypes` to allow safe variants.

Reference: the supplied ARIA NeMo notebook's before/after attack-suite approach.
The framework-specific compatibility proof belongs to increment 2; increment 1
establishes the behavior contract independently of a guardrail provider.
