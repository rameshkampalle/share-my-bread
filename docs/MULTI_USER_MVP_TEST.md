# Multi-user MVP setup and acceptance test

## Apply once

1. In Supabase SQL Editor run `database/migrations/006_multi_user_roles.sql`.
2. Confirm these Auth users exist and are email-confirmed:
   - `demo.member@sharemybread.test`
   - `retail.user1@sharemybread.test`
   - `retail.user2@sharemybread.test`
   - `retail.user3@sharemybread.test`
   - `delivery.user1@sharemybread.test`
   - `delivery.user2@sharemybread.test`
   - `admin.support@sharemybread.test`
3. Run `database/seed/004_multi_user_demo.sql`.
4. Verify that retail accounts are `MEMBER`, delivery/support accounts are `ADMIN`, and all appear in the demo group.
5. Deploy the backend and frontend from the same commit.

Do not rerun `003_demo_workspace.sql` after applying migration 006. It is the legacy single-user reset.

## Three-session acceptance test

Use three independent browser profiles or one normal window plus two incognito/alternate-browser sessions.

### Session A — Retail User 1

1. Sign in and add Plain Yogurt.
2. Open the cart and verify every line shows its contributor.
3. Authorize this member's items.
4. Verify the cart remains open.

### Session B — Retail User 2

1. Sign in and verify Retail User 1's yogurt is visible but its edit controls are disabled.
2. Add Whole Wheat Bread.
3. Authorize this member's items.

### Session C — Admin or delivery account

1. Sign in and verify both members' items and authorization states are visible.
2. Select **Close shared cart & calculate**. This is the explicit developer-mode override before the scheduled cutoff.
3. Verify one cash obligation exists for each authorized member.

### Member commitments

1. In Session A select **Commit cash payment**.
2. In Session B select **Commit cash payment**.
3. In Session C verify pending commitments is zero and select **Freeze and place order**.

### Fulfilment and collection

In Session C:

1. Move the order to Preparing.
2. Mark it Ready for pickup.
3. Record cash once for each included member.
4. Record item collection once for each included member.
5. Verify Fulfil is disabled until both pending counters reach zero.
6. Mark the order fulfilled.
7. Verify the previous order appears in history and a new open cycle is created.

## Negative checks

- A retail member cannot see fulfilment buttons.
- A retail member cannot edit another member's line.
- A member cart change removes that member's earlier authorization.
- An add/update request after cutoff is rejected.
- Direct ORDER_PLACED to FULFILLED is rejected.
- An order cannot be fulfilled with pending cash or item collections.
