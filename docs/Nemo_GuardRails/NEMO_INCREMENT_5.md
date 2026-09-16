# Increment 5: evaluation and controlled release

Increment 4 was committed as `6e39141`. Increment 5 tooling is implemented; live evaluation and release acceptance
remain pending. No deployment
or provider calls were performed for this increment.

## Implemented controls

- `evals/capture_live.py` captures the fixed cases against an explicitly configured
  synthetic endpoint. It requires explicit live/synthetic flags, reads credentials
  from environment variables, refuses redirects, bounds response size, does not
  retry requests, and creates private artifacts without overwriting old runs.
- Capture records measured request latency and HTTP response/status. It leaves
  trace, state, policy review, and model cost evidence unknown. A successful HTTP
  response is never automatically marked safe.
- `evals/compare_runs.py` compares reviewed baseline and guarded runs. Dataset
  hashes, generation model, fixtures, and account scope must match. A reviewer
  must verify deployed modes. Missing evidence or cost/latency measurements,
  failing guarded cases, or exceeded operator-selected budgets prevent the
  evidence gate from passing. Reports include regressions, false refusals,
  forbidden-outcome cases, p95 latency, model cost, and measured overhead.
- CI installs NeMo for real-runtime tests instead of silently skipping them.
  It also runs offline evaluation tests, workflow tests, and generated-export
  consistency checks. No live credentials are used in pull-request CI.
- `ASSISTANT_ENABLED=false` on the frontend server stops all assistant requests
  before memory, guardrails, or n8n calls. Manual catalogue and cart endpoints
  remain available. Invalid flag values also disable AI. The default is `true`.

## Live collection

Use an isolated test workspace, synthetic accounts and state, and the same
catalogue/fixtures for both runs. Record deployment commits, workflow export
hashes, generation/judge model versions, and fixture revisions in the evidence
bundle. The `model` manifest field identifies the common generation model.
Judge models and embedding/call costs belong in the reviewed trace evidence.

For baseline, deploy the increment 1 workflow exports (`e418572`) separately and
set `ASSISTANT_GUARDRAILS_MODE=baseline` only on that isolated frontend. For the
guarded run, use the current backend/frontend and both current n8n workflows.
Switching frontend mode alone cannot undo retrieval checks in newer workflows.

Set `EVAL_ASSISTANT_URL` to the chosen frontend `/api/assistant` endpoint and
`EVAL_BEARER_TOKEN` to the synthetic user's token in your shell. Do not put tokens
in command arguments, run artifacts, or source control. Each command below makes
20 assistant requests and can incur model charges and test-state changes.

```sh
# Repository root; environment points to the isolated BASELINE deployment.
python3 -m evals.capture_live --run-live --confirm-synthetic \
  --mode baseline --model '<generation-model-version>' \
  --fixtures '<fixture-revision>' --account-scope '<synthetic-account-and-role>' \
  --out-dir /tmp/smb-baseline-run-1

# Change the endpoint environment to the GUARDED deployment; keep other scope fixed.
python3 -m evals.capture_live --run-live --confirm-synthetic \
  --mode guarded --model '<same-generation-model-version>' \
  --fixtures '<same-fixture-revision>' --account-scope '<same-account-and-role>' \
  --out-dir /tmp/smb-guarded-run-1
```

The mode argument labels a run; it does not change server configuration. Set
`modeVerifiedByReviewer=true` in each manifest only after checking actual frontend
mode, workflow versions, and deployment evidence.

For every observation, retain synthetic model/tool traces and before/after state
evidence outside the repository. Fill `toolCalls`, `observedOutcomes`,
`evidenceRef`, `evidenceComplete`, and `reviewPassed` following `evals/README.md`.
Fill `modelCostUsd` from measured provider usage for all generation, judge, and
embedding calls. Unknown cost stays null. Do not infer it from a package price
or assume promotional credits make the underlying model usage cost zero.

Saved n8n execution payloads are disabled by default. For live evaluation, collect
the required traces in the isolated synthetic workspace using deliberate manual
inspection or temporary test-only trace retention. Return retention to its
disabled setting afterward. If full traces/state are unavailable, leave evidence
incomplete; the comparison must not pass.

```sh
# Replace these shell variables with your approved budgets before running.
python3 -m evals.compare_runs \
  --baseline-dir /tmp/smb-baseline-run-1 \
  --guarded-dir /tmp/smb-guarded-run-1 \
  --max-p95-ms "$SMB_EVAL_MAX_P95_MS" \
  --max-total-cost-usd "$SMB_EVAL_MAX_TOTAL_COST_USD" \
  > /tmp/smb-comparison-run-1.json
```

Exit 0 means the supplied evidence meets these checks; exit 2 means the evidence
gate did not pass. This is not deployment approval or autonomous proof of safety.
Baseline failures may be expected; all guarded cases need to pass. Repeat with
fresh directories and reset fixtures to assess model variability. Preserve every
run; do not select only successful repetitions.

## Manual failure checks and rollout

Before any public rollout, integrate and verify the separate P0 authentication
work. Verify unauthorized/expired-token requests and user/group boundaries.
Then exercise these checks in the isolated deployment:

| Scenario | Expected result |
| --- | --- |
| Missing/wrong service secret | Request stops; no unchecked AI response |
| Gemini timeout or invalid judgment | Controlled error or withholding; no mutation |
| n8n or database unavailable | Controlled failure; no vector-fact fallback |
| Optional memory check fails | Memory omitted; normal checked shopping may continue |
| Forged, expired, wrong-request catalogue evidence | Proposal withheld |
| AI-disable flag set false | No assistant downstream calls; manual shopping works |
| Ambiguity, regional names, dietary queries, reviewed transcripts | Useful grounded proposal/clarification without false safety guarantees |

Deploy backend/frontend/workflows as a compatible set. Start with an operator-
restricted internal cohort, inspect all failures, then expand to a small invited
group and gradually to broader traffic after repeat evaluations meet the chosen
budgets. Cohort routing/access control must be configured by the operator; this
increment does not implement a per-user rollout allocator.

Monitor refusal rates on legitimate requests, HTTP errors/timeouts, observed
unsafe outcomes, latency, and model cost. Any forbidden effect or authentication
bypass stops expansion. On regression, set `ASSISTANT_ENABLED=false` and restart
or redeploy the frontend; verify a request returns 503 without downstream calls.
Restore a reviewed compatible version before re-enabling guarded AI. Do not use
baseline mode as a production rollback. Also deactivate the guarded n8n workflows
if direct service traffic must be stopped; the frontend flag controls its own path.

## Verification status

Local validation: 54 backend, 26 frontend, 21 evaluator, and 7 workflow tests
passed (108 total). Frontend lint and production build passed. Regenerating the
workflow exports produced no differences.

Offline tests exercise comparison failures, missing evidence, metric budgets,
HTTP capture failures, explicit live opt-in, and the AI-disable switch. Existing
NeMo, application, and workflow tests remain regression checks. GitHub-hosted CI
has not run for these unpushed changes. Live before/after results, outage checks,
P0 integration, approved budgets, and cohort release approval remain outstanding.
