# Security baseline

- The browser never receives the Supabase service-role key, database password, Gemini key, Pinecone key, or n8n webhook secret.
- Browser clients do not directly mutate business tables.
- FastAPI validates Supabase user tokens and derives actor/group scope server-side.
- n8n uses narrow API tools and has no arbitrary SQL or unrestricted mutation tool.
- Cart changes are proposals until confirmed through FastAPI.
- Webhook events carry correlation and idempotency identifiers and are authenticated.
- Prompts and product text are untrusted input.
- Logs exclude secrets, raw authentication tokens, private addresses, and raw audio.
