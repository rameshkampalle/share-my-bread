import type { Cart, Journey } from "@/lib/types";

const money = new Intl.NumberFormat("en-IE", { style: "currency", currency: "EUR" });

type Props = {
  cart: Cart | null;
  journey: Journey | null;
  busy: boolean;
  error: string;
  notice: string;
  onClose: () => void;
  onQuantity: (lineId: string, quantity: number) => void;
  onRemove: (lineId: string) => void;
  onAction: (path: string, body?: object) => void;
};

const stageLabels = ["Cart", "Authorized", "Cash committed", "Order placed", "Ready", "Fulfilled"];

function stageIndex(journey: Journey | null) {
  if (!journey?.authorization) return 0;
  if (!journey.obligation || journey.obligation.status === "DUE") return 1;
  if (!journey.order || journey.order.status === "AWAITING_COMMITMENT") return 2;
  if (["ORDER_PLACED", "PREPARING"].includes(journey.order.status)) return 3;
  if (journey.order.status === "READY_FOR_PICKUP") return 4;
  if (journey.order.status === "FULFILLED") return 5;
  return 3;
}

export function CartDrawer({ cart, journey, busy, error, notice, onClose, onQuantity, onRemove, onAction }: Props) {
  const stage = stageIndex(journey);
  const editable = journey?.cycle.status === "OPEN";
  const orderStatus = journey?.order?.status;
  const obligationStatus = journey?.obligation?.status;

  return (
    <div className="drawer-backdrop" onMouseDown={onClose}>
      <aside className="cart-drawer" aria-label="Cart and order journey" onMouseDown={(event) => event.stopPropagation()}>
        <div className="cart-drawer-head">
          <div><p className="eyebrow ink">Shared order journey</p><h2>{cart?.group_name ?? "Your cart"}</h2></div>
          <button onClick={onClose} aria-label="Close cart">×</button>
        </div>

        {journey?.dev_fulfilment_mode && <p className="demo-banner">Demo mode · retailer placement and fulfilment are simulated</p>}

        <ol className="journey-steps">
          {stageLabels.map((label, index) => <li key={label} className={index <= stage ? "done" : ""}><span>{index < stage ? "✓" : index + 1}</span>{label}</li>)}
        </ol>

        <section className="drawer-section">
          <div className="section-title"><h3>Review cart</h3><strong>{money.format(cart?.subtotal ?? 0)}</strong></div>
          {!cart?.lines.length && <p className="drawer-empty">Your cart is empty. Add an item from the catalogue.</p>}
          <div className="review-lines">
            {cart?.lines.map((line) => (
              <article key={line.id}>
                <div><strong>{line.name}</strong><small>{line.contributor_name} · {line.sku} · {line.unit} · {money.format(Number(line.unit_price))} each</small></div>
                <div className="quantity-control">
                  <button disabled={busy || !editable || !line.editable || line.quantity <= 1} onClick={() => onQuantity(line.id, line.quantity - 1)}>−</button>
                  <span>{line.quantity}</span>
                  <button disabled={busy || !editable || !line.editable} onClick={() => onQuantity(line.id, line.quantity + 1)}>+</button>
                </div>
                <strong>{money.format(Number(line.line_total))}</strong>
                <button className="remove-line" disabled={busy || !editable || !line.editable} onClick={() => onRemove(line.id)}>Remove</button>
              </article>
            ))}
          </div>
        </section>

        {journey?.order && (
          <section className="drawer-section cost-card">
            <div className="section-title"><h3>Deterministic allocation</h3><span className="status-chip">{obligationStatus?.replaceAll("_", " ")}</span></div>
            <p>Only authorized members are included. Each member pays for their own frozen lines at the stored unit price.</p>
            {journey.order_lines.map((line) => <div className="allocation-row" key={line.id}><span>{line.quantity}× {line.product_snapshot.name}</span><strong>{money.format(Number(line.total))}</strong></div>)}
            <div className="allocation-total"><span>Your cash obligation</span><strong>{money.format(Number(journey.obligation?.amount_due ?? 0))}</strong></div>
          </section>
        )}

        {error && <p className="error-banner" role="alert">{error}</p>}
        {notice && <p className="success-banner">{notice}</p>}

        <div className="journey-actions">
          {journey?.cycle.status === "OPEN" && !journey?.authorization && <><button className="primary-button" disabled={busy || Number(cart?.member_subtotal ?? 0) <= 0} onClick={() => onAction("/api/journey/authorize")}>{busy ? "Working…" : "Authorize my items"}<span>→</span></button><button className="secondary-button" disabled={busy} onClick={() => onAction("/api/journey/decline")}>Decline this cycle</button></>}
          {journey?.cycle.status === "OPEN" && journey?.authorization?.decision === "AUTHORIZED" && <p className="success-banner">Your items are authorized. Other members can still add items and decide until cutoff.</p>}
          {journey?.cycle.status === "OPEN" && journey?.authorization?.decision === "DECLINED" && <button className="primary-button" disabled={busy || Number(cart?.member_subtotal ?? 0) <= 0} onClick={() => onAction("/api/journey/authorize")}>Change decision: authorize my items<span>→</span></button>}
          {journey?.cycle.status === "OPEN" && (journey.is_admin || journey.is_coordinator) && <button className="primary-button" disabled={busy || !journey.member_decisions.some((member) => member.decision === "AUTHORIZED")} onClick={() => onAction("/api/journey/close-cart", { forceBeforeCutoff: true })}>Close shared cart & calculate<span>→</span></button>}
          {journey?.authorization && obligationStatus === "DUE" && <button className="primary-button" disabled={busy} onClick={() => onAction("/api/journey/commit-cash")}>{busy ? "Working…" : "Commit cash payment"}<span>→</span></button>}
          {(journey?.is_admin || journey?.is_coordinator) && orderStatus === "AWAITING_COMMITMENT" && <button className="primary-button" disabled={busy || journey.pending_commitments > 0} onClick={() => onAction("/api/journey/finalize")}>{journey.pending_commitments ? `Waiting for ${journey.pending_commitments} cash commitment(s)` : "Freeze and place order (mock retailer)"}<span>→</span></button>}
          {journey?.is_admin && orderStatus === "ORDER_PLACED" && <button className="primary-button" disabled={busy} onClick={() => onAction("/api/journey/fulfilment", { status: "PREPARING" })}>Move to preparing<span>→</span></button>}
          {journey?.is_admin && orderStatus === "PREPARING" && <button className="primary-button" disabled={busy} onClick={() => onAction("/api/journey/fulfilment", { status: "READY_FOR_PICKUP" })}>Mark ready for pickup<span>→</span></button>}
          {journey?.is_admin && ["ORDER_PLACED", "PREPARING", "READY_FOR_PICKUP"].includes(orderStatus ?? "") && <button className="secondary-button danger-button" disabled={busy} onClick={() => onAction("/api/journey/fulfilment", { status: "CANCELLED", reason: "Cancelled by administrator in developer mode" })}>Cancel order</button>}
          {journey?.is_admin && orderStatus === "READY_FOR_PICKUP" && journey.pending_collections > 0 && <button className="primary-button" disabled={busy} onClick={() => onAction("/api/journey/collect-cash")}>Record next cash collection ({journey.pending_collections} left)<span>→</span></button>}
          {journey?.is_admin && orderStatus === "READY_FOR_PICKUP" && journey.pending_item_collections > 0 && <button className="primary-button" disabled={busy} onClick={() => onAction("/api/journey/collect-items")}>Record next item collection ({journey.pending_item_collections} left)<span>→</span></button>}
          {journey?.is_admin && orderStatus === "READY_FOR_PICKUP" && journey.pending_collections === 0 && journey.pending_item_collections === 0 && <button className="primary-button" disabled={busy} onClick={() => onAction("/api/journey/fulfilment", { status: "FULFILLED" })}>Mark order fulfilled<span>→</span></button>}
          {orderStatus === "FULFILLED" && <p className="complete-message">✓ Order fulfilled and cash collected. The complete demo journey is recorded.</p>}
        </div>

        {!!journey?.member_decisions.length && <section className="drawer-section"><h3>Member decisions</h3>{journey.member_decisions.map((member) => <div className="allocation-row" key={member.id}><span>{member.display_name}</span><strong>{member.decision}</strong></div>)}</section>}
        {journey?.is_admin && !!journey.group_obligations.length && <section className="drawer-section"><h3>Member obligations</h3>{journey.group_obligations.map((item) => <div className="allocation-row" key={item.id}><span>{item.display_name}</span><strong>{money.format(Number(item.amount_due))} · {item.status.replaceAll("_", " ")} · items {item.items_collected ? "collected" : "pending"}</strong></div>)}</section>}

        {!!journey?.fulfilment_events.length && <section className="drawer-section"><h3>Order status timeline</h3><ol className="event-list">{journey.fulfilment_events.map((event) => <li key={event.id}><span>●</span><div><strong>{event.new_status.replaceAll("_", " ")}</strong><small>{event.source.replaceAll("_", " ")} · {new Date(event.created_at).toLocaleString()}</small></div></li>)}</ol></section>}
        {!!journey?.audit_events.length && <details className="audit-panel"><summary>Audit history ({journey.audit_events.length})</summary>{journey.audit_events.map((event) => <div key={event.id}><strong>{event.action.replaceAll("_", " ")}</strong><small>{new Date(event.created_at).toLocaleString()}</small></div>)}</details>}
      </aside>
    </div>
  );
}
