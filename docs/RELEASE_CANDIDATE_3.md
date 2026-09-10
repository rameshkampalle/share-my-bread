# Release candidate 3: personalized voice assistant

## Scope

- Browser speech recognition writes an editable transcript; raw audio is not retained.
- Mem0 preference memory is disabled until each user opts in.
- Supabase user UUIDs are namespaced and used as the Mem0 user boundary.
- Only explicit grocery preferences may be saved. Cart, order, stock, payment and audio data remain outside Mem0.
- Users can inspect and delete individual memories, or disable memory and erase all of their memories.
- Individual deletion cascades through Mem0's linked V3 history so an older superseded preference cannot resurface.
- Preference creation waits for Mem0's asynchronous event to succeed before the UI reports that it is ready.
- Forget waits until the deleted preference is absent from Mem0's list API before reporting success.
- A failed or disabled memory service never blocks the normal assistant.

## Deployment

1. On Render set `MEM0_ENABLED=true` and `MEM0_API_KEY=<server-side key>`.
2. Redeploy the backend and verify `/health` reports `preferenceMemory: true`.
3. Redeploy Vercel.
4. Regenerate/import `SMB-AGT-001-Assistant.json`, reconnect its existing Gemini and Pinecone credentials, test, then activate it.

## Smoke test

1. Retail User 1 enables memory and saves `I prefer vegan milk`.
2. Verify the preference is listed before the UI reports `Preference saved and ready to use`.
3. Ask by voice for milk; verify the transcript is editable before submission and the proposal still requires confirmation.
4. Retail User 2 opens memory and must not see User 1's preference.
5. User 1 deletes the preference, then disables memory; verify the list is empty.
