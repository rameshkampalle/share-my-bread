# Share My Bread frontend

Cloud-ready Next.js inventory website using Supabase Auth/data and the n8n assistant webhook.

## Local setup (Windows PowerShell)

```powershell
cd C:\Users\SiriRamesh\Desktop\AgenticAI\MasteringAgenticAIPRogram\share-my-bread\frontend
Copy-Item .env.example .env.local
notepad .env.local
npm install
npm run dev
```

Set these values in `.env.local`:

- `NEXT_PUBLIC_SUPABASE_URL`: Supabase project URL.
- `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`: Supabase publishable key. Do not use the secret/service-role key.
- `NEXT_PUBLIC_API_BASE_URL`: FastAPI URL (`http://localhost:8000` for local development).
- `N8N_AGENT_WEBHOOK_URL`: production URL from the published `SMB-AGT-001-Assistant` workflow.
- `N8N_WEBHOOK_SECRET`: optional shared secret if the n8n workflow validates it.

Open `http://localhost:3000` and sign in with `demo.member@sharemybread.test` plus the password created in Supabase Auth.

## Verification

```powershell
npm run lint
npm run build
```

Run the FastAPI backend separately before testing cart confirmation. Expected after sign-in:
30 products, inventory stock indicators, alias search, category filters, and the current cart.

## Vercel deployment

1. In Vercel, choose **Add New → Project** and import `rameshkampalle/share-my-bread`.
2. Set **Root Directory** to `frontend`.
3. Add the same four environment variables from `.env.local`.
4. Deploy. No server or database runs locally.

## Current safety boundary

The assistant searches and proposes. Only the authenticated FastAPI endpoint validates stock and writes confirmed items to the cart in one database transaction.
