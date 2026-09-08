-- Reset mutable demo transaction data while preserving users and catalogue.
-- Use only in the shared demo environment.

begin;

delete from public.idempotency_records;
delete from public.outbox_events;
delete from public.audit_events;
delete from public.fulfilment_events;
delete from public.collection_records;
delete from public.cash_obligations;
delete from public.allocations;
delete from public.order_lines;
delete from public.orders;
delete from public.agent_proposals;
delete from public.authorizations;
delete from public.line_claims;
delete from public.cart_lines;
delete from public.order_cycles;
delete from public.pickup_points;

update public.inventory set reserved_quantity = 0, updated_at = timezone('utc', now());

commit;
