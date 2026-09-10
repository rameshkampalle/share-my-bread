# Release candidate 2 — group visibility and unattended cutoff

This release builds on the tested multi-user MVP. It does not replace or reset
the existing Supabase project automatically.

## Included

- Visible group, role, join code, pickup, cutoff and member-decision dashboard.
- In-app notification feed with unread count and mark-all-read.
- Browser voice capture that writes an editable transcript before the AI request.
- Retry-safe cutoff reminders for members who have not decided.
- Automatic cutoff processing through a secured n8n schedule.
- Group notifications for placed, preparing, ready, fulfilled and cancelled orders.
- Audited cancellation with stock restoration and collection safety checks.
- Admin-only, explicitly confirmed demo reset that preserves completed history and
  reconciles stock before opening a clean seven-day cycle.

## Deploy in this order

1. Pause team testing for the short deployment window.
2. In Supabase SQL Editor run `database/migrations/007_notifications_and_automation.sql`.
3. In Render set `N8N_WEBHOOK_SECRET` to a new long random value. Do not commit it.
4. Deploy the backend and verify `/health` returns HTTP 200.
5. In n8n create a **Header Auth** credential named `SMB - Backend Scheduler`.
   Set Header Name to `X-Webhook-Secret` and Header Value to the identical secret.
6. Import `automation/workflows/SMB-SCH-001-Cutoff-Orchestrator.json`, then select
   `SMB - Backend Scheduler` on its HTTP Request node.
7. Run the workflow once manually. Its output must contain `remindersCreated`,
   `cyclesClosed`, and `failures`. Keep it inactive if `failures` is non-empty.
8. Activate the scheduler workflow.
9. Deploy the frontend from the same Git commit.
10. Sign in as one member and one admin, then run the smoke test below.

## Smoke test

1. Confirm the dashboard shows the same group, cutoff and members in both sessions.
2. Add an item as the member and confirm the shared cart updates.
3. Authorize as the member; confirm their dashboard badge changes to `AUTHORIZED`.
4. Run the scheduler manually before cutoff; it must not close the cycle.
5. Confirm a pending member receives at most one cutoff reminder even after two runs.
6. Use the existing admin developer override to close the cart and complete one order.
7. Mark it ready and confirm both sessions receive an in-app notification.
8. For cancellation testing, place a different order, cancel before collection, and
   verify inventory is restored and a new clean cycle opens.

## Safe demo reset

The group dashboard exposes **Reset unfinished demo** only to an `ADMIN`. The API
also requires the exact confirmation phrase `RESET DEMO WORKSPACE` and developer
fulfilment mode. It removes only non-terminal journeys in the administrator's own
group, preserves fulfilled/cancelled order history, reconciles affected inventory,
and writes an audit event.

Do not use legacy `database/seed/003_demo_workspace.sql` after migration 006.
