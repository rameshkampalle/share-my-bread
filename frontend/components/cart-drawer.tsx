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
                <div><strong>{line.name}</strong><small>{line.sku} · {line.unit} · {money.format(Number(line.unit_price))} each</small></div>
                <div className="quantity-control">
                  <button disabled={busy || !editable || line.quantity <= 1} onClick={() => onQuantity(line.id, line.quantity - 1)}>−</button>
                  <span>{line.quantity}</span>
                  <button disabled={busy || !editable} onClick={() => onQuantity(line.id, line.quantity + 1)}>+</button>
                </div>
                <strong>{money.format(Number(line.line_total))}</strong>
                <button className="remove-line" disabled={busy || !editable} onClick={() => onRemove(line.id)}>Remove</button>
              </article>
            ))}
          </div>
        </section>

        {journey?.authorization && (
          <section className="drawer-section cost-card">
            <div className="section-title"><h3>Deterministic allocation</h3><span className="status-chip">{obligationStatus?.replaceAll("_", " ")}</span></div>
            <p>The demo has one member, so every confirmed line is allocated to you at its stored unit price.</p>
            {journey.order_lines.map((line) => <div className="allocation-row" key={line.id}><span>{line.quantity}× {line.product_snapshot.name}</span><strong>{money.format(Number(line.total))}</strong></div>)}
            <div className="allocation-total"><span>Your cash obligation</span><strong>{money.format(Number(journey.obligation?.amount_due ?? 0))}</strong></div>
          </section>
        )}

        {error && <p className="error-banner" role="alert">{error}</p>}
        {notice && <p className="success-banner">{notice}</p>}

        <div className="journey-actions">
          {!journey?.authorization && <button className="primary-button" disabled={busy || !cart?.lines.length} onClick={() => onAction("/api/journey/authorize")}>{busy ? "Working…" : "Authorize cart & calculate"}<span>→</span></button>}
          {journey?.authorization && obligationStatus === "DUE" && <button className="primary-button" disabled={busy} onClick={() => onAction("/api/journey/commit-cash")}>{busy ? "Working…" : "Commit cash payment"}<span>→</span></button>}
          {obligationStatus === "COMMITTED" && orderStatus === "AWAITING_COMMITMENT" && <button className="primary-button" disabled={busy} onClick={() => onAction("/api/journey/finalize")}>{busy ? "Working…" : "Place order (mock retailer)"}<span>→</span></button>}
          {journey?.is_admin && orderStatus === "ORDER_PLACED" && <button className="primary-button" disabled={busy} onClick={() => onAction("/api/journey/fulfilment", { status: "PREPARING" })}>Move to preparing<span>→</span></button>}
          {journey?.is_admin && orderStatus === "PREPARING" && <button className="primary-button" disabled={busy} onClick={() => onAction("/api/journey/fulfilment", { status: "READY_FOR_PICKUP" })}>Mark ready for pickup<span>→</span></button>}
          {journey?.is_admin && orderStatus === "READY_FOR_PICKUP" && obligationStatus !== "COLLECTED" && <button className="primary-button" disabled={busy} onClick={() => onAction("/api/journey/collect-cash")}>Record cash collected<span>→</span></button>}
          {journey?.is_admin && orderStatus === "READY_FOR_PICKUP" && obligationStatus === "COLLECTED" && <button className="primary-button" disabled={busy} onClick={() => onAction("/api/journey/fulfilment", { status: "FULFILLED" })}>Mark order fulfilled<span>→</span></button>}
          {orderStatus === "FULFILLED" && <p className="complete-message">✓ Order fulfilled and cash collected. The complete demo journey is recorded.</p>}
        </div>

        {!!journey?.fulfilment_events.length && <section className="drawer-section"><h3>Order status timeline</h3><ol className="event-list">{journey.fulfilment_events.map((event) => <li key={event.id}><span>●</span><div><strong>{event.new_status.replaceAll("_", " ")}</strong><small>{event.source.replaceAll("_", " ")} · {new Date(event.created_at).toLocaleString()}</small></div></li>)}</ol></section>}
        {!!journey?.audit_events.length && <details className="audit-panel"><summary>Audit history ({journey.audit_events.length})</summary>{journey.audit_events.map((event) => <div key={event.id}><strong>{event.action.replaceAll("_", " ")}</strong><small>{new Date(event.created_at).toLocaleString()}</small></div>)}</details>}
      </aside>
    </div>
  );
}
