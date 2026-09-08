# Evaluation plan

1. Index the fixed product catalogue into the isolated Pinecone `demo` namespace.
2. Run `product-retrieval.jsonl` directly against the semantic-search workflow.
3. Fix data/alias/indexing problems before evaluating the agent.
4. Run `agent-tools.jsonl` and score intent, selected tools, arguments, schema, and confirmation.
5. Run `safety.jsonl`; any prohibited mutation or disclosure is a release blocker.
6. Test Gemini/Pinecone/n8n failure paths and the deterministic website fallback.
7. Freeze prompt and workflow versions, then run the final regression without changing fixtures mid-run.
