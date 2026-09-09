import type { OrderHistoryItem } from "@/lib/types";

const money = new Intl.NumberFormat("en-IE", { style: "currency", currency: "EUR" });

type Props = {
  orders: OrderHistoryItem[];
  loading: boolean;
  busy: boolean;
  error: string;
  onClose: () => void;
  onAction: (path: string, body: object) => void;
};

export function OrdersDrawer({ orders, loading, busy, error, onClose, onAction }: Props) {
  return (
    <div className="drawer-backdrop" onMouseDown={onClose}>
      <aside className="cart-drawer" aria-label="Order history" onMouseDown={(event) => event.stopPropagation()}>
        <div className="cart-drawer-head"><div><p className="eyebrow ink">Saved permanently</p><h2>Order history</h2></div><button onClick={onClose} aria-label="Close order history">×</button></div>
        {loading && <p className="drawer-empty">Loading orders…</p>}
        {error && <p className="error-banner">{error}</p>}
        {!loading && !error && !orders.length && <p className="drawer-empty">No completed orders yet.</p>}
        <div className="order-history-list">
          {orders.map((order) => <article key={order.id} className="history-order">
            <div className="section-title"><div><span className="status-chip">{order.status.replaceAll("_", " ")}</span><h3>{order.order_number}</h3></div><strong>{money.format(Number(order.subtotal))}</strong></div>
            <p>{order.group_name} · {new Date(order.created_at).toLocaleString()}</p>
            {order.lines.map((line) => <div className="allocation-row" key={line.id}><span>{line.quantity}× {line.name}</span><strong>{money.format(Number(line.total))}</strong></div>)}
            <div className="history-payment"><span>Cash</span><strong>{order.cash_status?.replaceAll("_", " ") ?? "—"} · {money.format(Number(order.amount_collected ?? 0))} collected</strong></div>
            <div className="history-actions">
              {order.status === "ORDER_PLACED" && <button disabled={busy} onClick={() => onAction("/api/journey/fulfilment", { orderId: order.id, status: "PREPARING" })}>Move to preparing</button>}
              {order.status === "PREPARING" && <button disabled={busy} onClick={() => onAction("/api/journey/fulfilment", { orderId: order.id, status: "READY_FOR_PICKUP" })}>Mark ready for pickup</button>}
              {order.status === "READY_FOR_PICKUP" && order.cash_status !== "COLLECTED" && <button disabled={busy} onClick={() => onAction("/api/journey/collect-cash", { orderId: order.id })}>Record cash collected</button>}
              {order.status === "READY_FOR_PICKUP" && order.cash_status === "COLLECTED" && <button disabled={busy} onClick={() => onAction("/api/journey/fulfilment", { orderId: order.id, status: "FULFILLED" })}>Mark fulfilled</button>}
            </div>
          </article>)}
        </div>
      </aside>
    </div>
  );
}
