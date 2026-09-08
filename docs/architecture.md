# Cloud architecture

```mermaid
flowchart TD
    UI[Next.js on Vercel]
    API[FastAPI on Render]
    DB[(Supabase PostgreSQL)]
    AUTH[Supabase Auth]
    N8N[n8n Cloud]
    GEMINI[Gemini chat and embeddings]
    PC[(Pinecone)]
    UI --> AUTH
    UI --> API
    API --> DB
    API --> N8N
    N8N --> GEMINI
    N8N --> PC
    N8N --> API
```

The browser authenticates with Supabase and sends its user token to FastAPI. FastAPI validates identity, group scope, state, price, stock, cutoff, idempotency, and every mutation. n8n receives authenticated context from FastAPI, coordinates Gemini and Pinecone, and calls narrow backend tools. Pinecone returns candidate product IDs; FastAPI supplies authoritative price and stock.
