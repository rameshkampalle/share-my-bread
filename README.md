# Share My Bread

Cloud-native shared grocery application using a deterministic FastAPI/PostgreSQL core with n8n, Gemini, and Pinecone for agent-assisted search, proposals, reminders, and notifications.

## Architecture

| Capability | Cloud component |
|---|---|
| Web application | Next.js on Vercel |
| API and domain services | FastAPI on Render |
| Transactional data and authentication | Supabase PostgreSQL and Supabase Auth |
| Workflow and agent orchestration | n8n Cloud |
| Chat model and embeddings | Google Gemini |
| Semantic product search | Pinecone |
| Source and handover | GitHub |

AI may search, recommend, explain, and create proposals. It must not directly change prices, stock, authorization, orders, allocations, cash records, or fulfilment state. Every proposed cart mutation requires explicit confirmation through the backend.

## Repository

- `frontend/` — member and admin experience
- `backend/` — FastAPI and deterministic domain services
- `database/` — ordered migrations and repeatable sample data
- `automation/` — n8n workflow exports, prompts, and contracts
- `evals/` — evaluation datasets, runner, results, and report
- `tests/` — API and end-to-end tests
- `docs/` — architecture, setup, security, handover, and demo material

## Safe setup order

1. Run `database/migrations/001_extensions.sql` through `006_multi_user_roles.sql` in order.
2. Run `database/seed/001_products.sql`, `002_inventory.sql`, `003_demo_workspace.sql`, then `004_multi_user_demo.sql`.
3. Configure cloud variables using `.env.example`; never commit their real values.
4. Deploy the backend and verify `/health`.
5. Index products with `SMB-VEC-001-Index-Products` in n8n.
6. Run retrieval evaluations before enabling the agent workflow.

Confirmed semantic-search configuration: Gemini `gemini-embedding-001` at 3072 dimensions, Pinecone index `enterprise-architecture-rag`, isolated namespace `share-my-bread-demo`, cosine similarity.

Submission target: 12 September 2026.
