# Share My Bread backend

The FastAPI service verifies Supabase access tokens and owns deterministic cart mutations.

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item ..\.env.example .env
uvicorn app.main:app --reload --port 8000
```

Required `.env` values: `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, and
`CORS_ALLOWED_ORIGINS=http://localhost:3000`. Keep `SUPABASE_SERVICE_ROLE_KEY` private;
the current cart implementation connects with `DATABASE_URL` and does not need it.

Optional consent-controlled personalization uses `MEM0_ENABLED=true` and a server-only
`MEM0_API_KEY`. Never add the key to frontend or `NEXT_PUBLIC_*` variables.
