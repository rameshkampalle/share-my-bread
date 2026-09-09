# Share My Bread — 12-step demo journey

## One-time setup after applying this patch

1. In Supabase SQL Editor, rerun `database/seed/003_demo_workspace.sql`. This promotes the demo account to `ADMIN` so the simulated fulfilment controls are visible.
2. Restart the FastAPI backend so the new journey router is loaded.
3. Restart the Next.js frontend, then sign in as `demo.member@sharemybread.test`.

No new cloud account, migration, n8n import, or credential is required for this patch.

## End-to-end test

- [ ] 1. Click **+ Add to cart** on any product.
- [ ] 2. Click the dark cart strip or the cart pill in the header; the cart drawer opens.
- [ ] 3. Use **+**, **−**, and **Remove** to edit the cart.
- [ ] 4. Review every line and the subtotal in the drawer.
- [ ] 5. Click **Authorize cart & calculate**.
- [ ] 6. Verify the deterministic allocation equals the stored cart subtotal.
- [ ] 7. Click **Commit cash payment**.
- [ ] 8. Click **Finalize mock order** and verify the order is placed.
- [ ] 9. Verify the order-status timeline shows `FINALIZED` and `ORDER PLACED`.
- [ ] 10. As the demo admin, click **Move to preparing**, then **Mark ready for pickup**.
- [ ] 11. Click **Record cash collected**, then **Mark order fulfilled**.
- [ ] 12. Expand **Audit history** and verify the recorded business events.
- [ ] 13. Verify fulfilment opens **Order history**, the completed order is listed, the active cart becomes empty, and catalogue Add buttons are enabled again.

The AI assistant remains available throughout the catalogue phase. It can propose products through n8n/Gemini/Pinecone, but only explicit user confirmation changes the cart. Checkout totals and state transitions are calculated and enforced by FastAPI/PostgreSQL.

## Expected final state

- Order: `FULFILLED`
- Cash obligation: `COLLECTED`
- Order cycle: `FINALIZED`
- Timeline: finalization, mock retailer placement, preparation, ready for pickup, and fulfilment
- Audit history: cart authorization, cash commitment, order placement, collection, and fulfilment actions

## Reset for another demonstration

Rerun `database/seed/003_demo_workspace.sql` to reopen the demo cycle, restore the demo account's admin role, and clear only the previous checkout/order records. Existing cart lines remain available for another run.
