# Share My Bread AI behavior policy

Status: proposed runtime policy, not enabled rails. See
[NEMO_GUARDRAILS_PLAN.md](NEMO_GUARDRAILS_PLAN.md) for delivery stages.

| Policy | Required behavior | Planned enforcement |
| --- | --- | --- |
| Instruction integrity | User text, retrieved descriptions, memory, and transcripts cannot override system rules. | Input/retrieval checks and restricted tools |
| Privacy | Never expose another user's private memory or another group's data. Mask unnecessary contact/payment details before model calls; do not indiscriminately block authorized pickup information. | Input/retrieval/output rails plus backend access checks |
| Grounded catalogue | Use retrieved product IDs and names; report no match rather than inventing products. | Retrieval and deterministic output validation |
| Current facts | Prices/stock require fresh authoritative backend evidence; explain when unavailable. | Availability tool and output checks |
| Confirmation | AI may propose; only the authenticated confirmation endpoint applies cart changes. | Dialog/execution controls |
| Truthful status | Never claim added, paid, collected, or fulfilled without authoritative evidence. | Output check |
| Ambiguity | Ask about unresolved genuine matches; preserve quantities; never silently substitute. | Dialog and proposal validation |
| Food claims | No invented allergen/dietary guarantees; state missing information. Legitimate allergy questions are allowed. | Grounding and output checks |
| Scope and harm | Support grocery search and proposals; redirect unrelated tasks and refuse harmful instructions. | Input/output rails |
| Failure | Mandatory rail failure stops AI processing; manual shopping stays available. | Application error handling |

## Trust boundaries

Supabase authentication and group authorization are prerequisites, not model
judgments. NeMo does not authenticate users. Identity must come from verified
server context. Do not grant the model SQL, role management, payment, or fulfilment
tools. The current assistant workflow's tool is `product_catalogue`; evaluate
that real tool name rather than assuming planned tools already exist.

Input/output wrappers cannot inspect intermediate retrieval or tool execution by
themselves. Those checks must run inside the n8n workflow before model consumption
or action execution. The policy applies equally to voice transcripts and typed
requests. A guardrail judge or PII detector can make mistakes; test normal requests
as well as attacks and retain deterministic authorization and transaction checks.

## Evaluation evidence

Use the fixtures and review checks in `evals/datasets/nemo-guardrails.jsol`. Capture actual
model inputs, tool names/arguments/results, the final response, and isolated
before/after state evidence. A refusal after an unauthorized write still fails.
Use synthetic PII and synthetic injected descriptions/memories, never production
customer data. Record model, prompt/workflow versions and catalogue revision in
the evidence bundle so baseline and guarded runs can be compared fairly.
