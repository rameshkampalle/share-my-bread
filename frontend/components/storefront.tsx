"use client";

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Session } from "@supabase/supabase-js";
import { CartDrawer } from "@/components/cart-drawer";
import { OrdersDrawer } from "@/components/orders-drawer";
import { getSupabaseBrowserClient } from "@/lib/supabase";
import type { AssistantResponse, Cart, InventoryRow, Journey, OrderHistoryItem, Product } from "@/lib/types";

const money = new Intl.NumberFormat("en-IE", {
  style: "currency",
  currency: "EUR",
});

function inventoryFor(product: Product): InventoryRow | null {
  if (Array.isArray(product.inventory)) return product.inventory[0] ?? null;
  return product.inventory;
}

function stockDetails(product: Product) {
  const inventory = inventoryFor(product);
  const available = inventory?.available_quantity ?? 0;
  const reserved = inventory?.reserved_quantity ?? 0;
  const free = Math.max(available - reserved, 0);

  if (free === 0) return { label: "Out of stock", tone: "out" };
  if (free <= 5) return { label: `Only ${free} left`, tone: "low" };
  return { label: `${free} available`, tone: "good" };
}

export function Storefront() {
  const [session, setSession] = useState<Session | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const [email, setEmail] = useState("demo.member@sharemybread.test");
  const [password, setPassword] = useState("");
  const [authError, setAuthError] = useState("");
  const [products, setProducts] = useState<Product[]>([]);
  const [loadingProducts, setLoadingProducts] = useState(false);
  const [productError, setProductError] = useState("");
  const [cart, setCart] = useState<Cart | null>(null);
  const [cartError, setCartError] = useState("");
  const [cartOpen, setCartOpen] = useState(false);
  const [journey, setJourney] = useState<Journey | null>(null);
  const [journeyError, setJourneyError] = useState("");
  const [journeyNotice, setJourneyNotice] = useState("");
  const [mutating, setMutating] = useState(false);
  const [ordersOpen, setOrdersOpen] = useState(false);
  const [orders, setOrders] = useState<OrderHistoryItem[]>([]);
  const [ordersLoading, setOrdersLoading] = useState(false);
  const [ordersError, setOrdersError] = useState("");
  const rolloverStarted = useRef(false);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("All");
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [assistantQuery, setAssistantQuery] = useState("");
  const [assistantResult, setAssistantResult] = useState<AssistantResponse | null>(null);
  const [assistantError, setAssistantError] = useState("");
  const [asking, setAsking] = useState(false);
  const [decision, setDecision] = useState<"accepted" | "declined" | null>(null);
  const [selectedProposalIds, setSelectedProposalIds] = useState<string[]>([]);
  const [proposalQuantities, setProposalQuantities] = useState<Record<string, number>>({});

  const backend = useCallback(async (path: string, init?: RequestInit) => {
    const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
    if (!baseUrl) throw new Error("NEXT_PUBLIC_API_BASE_URL is not configured.");
    const { data } = await getSupabaseBrowserClient().auth.getSession();
    if (!data.session) throw new Error("Your session has expired.");
    const response = await fetch(`${baseUrl.replace(/\/$/, "")}${path}`, {
      ...init,
      signal: init?.signal ?? AbortSignal.timeout(20000),
      headers: { "content-type": "application/json", authorization: `Bearer ${data.session.access_token}`, ...(init?.headers ?? {}) },
    });
    const value = await response.json();
    if (!response.ok) throw new Error(value.detail ?? value.message ?? "Backend request failed.");
    return value;
  }, []);

  const refreshOrder = useCallback(async () => {
    setCartError("");
    setJourneyError("");
    const [cartResult, journeyResult] = await Promise.allSettled([
      backend("/api/cart/current"),
      backend("/api/journey/current"),
    ]);
    if (cartResult.status === "fulfilled") setCart(cartResult.value as Cart);
    else setCartError(cartResult.reason instanceof Error ? cartResult.reason.message : "Cart unavailable.");
    if (journeyResult.status === "fulfilled") setJourney(journeyResult.value as Journey);
    else setJourneyError(journeyResult.reason instanceof Error ? journeyResult.reason.message : "Order journey unavailable.");
  }, [backend]);

  const openOrderHistory = useCallback(async () => {
    setOrdersOpen(true);
    setOrdersLoading(true);
    setOrdersError("");
    try {
      const value = await backend("/api/journey/history");
      setOrders((value.orders ?? []) as OrderHistoryItem[]);
    } catch (error) {
      setOrdersError(error instanceof Error ? error.message : "Order history unavailable.");
    } finally {
      setOrdersLoading(false);
    }
  }, [backend]);

  useEffect(() => {
    let supabase;
    try {
      supabase = getSupabaseBrowserClient();
    } catch (error) {
      queueMicrotask(() => {
        setAuthError(error instanceof Error ? error.message : "Supabase configuration is missing.");
        setAuthReady(true);
      });
      return;
    }

    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setAuthReady(true);
    });

    const { data } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      setSession(nextSession);
    });

    return () => data.subscription.unsubscribe();
  }, []);

  useEffect(() => {
    if (!session) return;

    async function loadProducts() {
      setLoadingProducts(true);
      setProductError("");
      const { data, error } = await getSupabaseBrowserClient()
        .from("products")
        .select(
          "id,sku,name,description,category,brand,unit,price,currency,aliases,dietary_tags,image_url,inventory(available_quantity,reserved_quantity,updated_at)",
        )
        .eq("active", true)
        .order("category")
        .order("name");

      if (error) setProductError(error.message);
      else setProducts((data ?? []) as Product[]);
      setLoadingProducts(false);
    }

    void loadProducts();
    void refreshOrder();
  }, [session, refreshOrder]);

  useEffect(() => {
    if (journey?.order?.status !== "FULFILLED" || rolloverStarted.current) return;
    rolloverStarted.current = true;
    void backend("/api/journey/rollover", { method: "POST" })
      .then(async () => {
        await refreshOrder();
        await openOrderHistory();
      })
      .catch((error) => {
        rolloverStarted.current = false;
        setJourneyError(error instanceof Error ? error.message : "Could not open a new cart.");
      });
  }, [backend, journey?.order?.status, openOrderHistory, refreshOrder]);

  async function mutateCart(path: string, init: RequestInit, notice: string) {
    setMutating(true);
    setJourneyError("");
    setJourneyNotice("");
    try {
      const value = await backend(path, init);
      setCart(value as Cart);
      setJourneyNotice(notice);
      await refreshOrder();
    } catch (error) {
      setJourneyError(error instanceof Error ? error.message : "Cart update failed.");
    } finally {
      setMutating(false);
    }
  }

  function addProduct(product: Product) {
    setCartOpen(true);
    void mutateCart("/api/cart/items", { method: "POST", body: JSON.stringify({ productId: product.id, quantity: 1 }) }, `${product.name} added to the cart.`);
  }

  function updateQuantity(lineId: string, quantity: number) {
    void mutateCart(`/api/cart/items/${lineId}`, { method: "PATCH", body: JSON.stringify({ quantity }) }, "Cart quantity updated.");
  }

  function removeLine(lineId: string) {
    void mutateCart(`/api/cart/items/${lineId}`, { method: "DELETE" }, "Item removed from the cart.");
  }

  async function journeyAction(path: string, body?: object) {
    setMutating(true);
    setJourneyError("");
    setJourneyNotice("");
    try {
      const value = await backend(path, { method: "POST", body: body ? JSON.stringify(body) : undefined });
      setJourney(value as Journey);
      const messages: Record<string, string> = {
        "/api/journey/authorize": "Cart authorized and member cost calculated.",
        "/api/journey/commit-cash": "Cash commitment recorded.",
        "/api/journey/finalize": "Mock retailer order placed.",
        "/api/journey/collect-cash": "Cash collection recorded.",
        "/api/journey/fulfilment": "Order status updated.",
      };
      setJourneyNotice(messages[path] ?? "Order updated.");
      await refreshOrder();
      if (path === "/api/journey/fulfilment" && body && "status" in body && body.status === "FULFILLED") {
        setCartOpen(false);
        await openOrderHistory();
      }
    } catch (error) {
      setJourneyError(error instanceof Error ? error.message : "Order action failed.");
    } finally {
      setMutating(false);
    }
  }

  async function historyAction(path: string, body: object) {
    setMutating(true);
    setOrdersError("");
    try {
      await backend(path, { method: "POST", body: JSON.stringify(body) });
      await Promise.all([refreshOrder(), openOrderHistory()]);
    } catch (error) {
      setOrdersError(error instanceof Error ? error.message : "Order update failed.");
    } finally {
      setMutating(false);
    }
  }

  const categories = useMemo(
    () => ["All", ...Array.from(new Set(products.map((product) => product.category))).sort()],
    [products],
  );

  const filteredProducts = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return products.filter((product) => {
      const categoryMatches = category === "All" || product.category === category;
      const searchable = [
        product.name,
        product.description,
        product.category,
        product.sku,
        ...(product.aliases ?? []),
      ]
        .join(" ")
        .toLowerCase();
      return categoryMatches && (!needle || searchable.includes(needle));
    });
  }, [category, products, query]);

  async function signIn(event: FormEvent) {
    event.preventDefault();
    setAuthError("");
    const { error } = await getSupabaseBrowserClient().auth.signInWithPassword({ email, password });
    if (error) setAuthError(error.message);
  }

  async function askAssistant(event: FormEvent) {
    event.preventDefault();
    if (!assistantQuery.trim()) return;

    setAsking(true);
    setAssistantError("");
    setAssistantResult(null);
    setDecision(null);
    try {
      const response = await fetch("/api/assistant", {
        method: "POST",
        signal: AbortSignal.timeout(35000),
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          message: assistantQuery.trim(),
          userId: session?.user.id,
          channel: "WEB",
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error ?? "The assistant is unavailable.");
      setAssistantResult(data as AssistantResponse);
      const items = (data as AssistantResponse).proposal?.items ?? [];
      setSelectedProposalIds(items.length === 1 ? [items[0].productId] : []);
      setProposalQuantities(Object.fromEntries(items.map((item) => [item.productId, item.quantity])));
    } catch (error) {
      setAssistantError(error instanceof Error ? error.message : "The assistant is unavailable.");
    } finally {
      setAsking(false);
    }
  }

  async function confirmProposal() {
    if (!assistantResult?.proposal || !cart || !selectedProposalIds.length) return;
    setAsking(true);
    setAssistantError("");
    try {
      const value = await backend("/api/cart/confirm", {
        method: "POST",
        headers: { "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({
          cycleId: cart.cycle_id,
          correlationId: assistantResult.correlationId,
          sourceText: assistantQuery,
          proposal: { ...assistantResult.proposal, items: assistantResult.proposal.items.filter((item) => selectedProposalIds.includes(item.productId)).map((item) => ({ ...item, quantity: proposalQuantities[item.productId] ?? item.quantity })) },
        }),
      });
      setCart(value.cart);
      setDecision("accepted");
      setJourneyNotice("Assistant proposal confirmed and added to the cart.");
      await refreshOrder();
    } catch (error) {
      setAssistantError(error instanceof Error ? error.message : "Proposal confirmation failed.");
    } finally {
      setAsking(false);
    }
  }

  function maximumAddable(productId: string) {
    const product = products.find((item) => item.id === productId);
    if (!product) return 0;
    const inventory = inventoryFor(product);
    const free = Math.max((inventory?.available_quantity ?? 0) - (inventory?.reserved_quantity ?? 0), 0);
    const alreadyInCart = cart?.lines.find((line) => line.product_id === productId)?.quantity ?? 0;
    return Math.max(Math.min(free - alreadyInCart, 99), 0);
  }

  function chooseCandidate(productId: string, name: string, quantity = 1) {
    setAssistantResult((current) => current ? { ...current, responseType: "CART_PROPOSAL", message: `${name} is selected. Confirm before it is added to your cart.`, requiresConfirmation: true, proposal: { action: "ADD_ITEMS", items: [{ productId, name, quantity }] } } : current);
    setSelectedProposalIds([productId]);
    setProposalQuantities({ [productId]: quantity });
    setDecision(null);
  }

  if (!authReady) {
    return <main className="center-stage"><div className="loader" aria-label="Loading" /></main>;
  }

  if (!session) {
    return (
      <main className="login-page">
        <section className="login-story">
          <a className="brand brand-light" href="#">Share My Bread<span>.</span></a>
          <div>
            <p className="eyebrow">Community buying, made human</p>
            <h1>Better groceries.<br />Shared together.</h1>
            <p className="story-copy">Browse live stock, find regional names like curd or dahi, and let the assistant prepare your cart—without changing anything until you confirm.</p>
          </div>
          <p className="story-foot">Powered by Supabase · n8n · Gemini · Pinecone</p>
        </section>
        <section className="login-panel">
          <form className="login-card" onSubmit={signIn}>
            <p className="eyebrow ink">Member access</p>
            <h2>Welcome back</h2>
            <p>Sign in with the demo account created in Supabase.</p>
            <label>Email<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
            <label>Password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Enter your Supabase password" required /></label>
            {authError && <p className="error-banner" role="alert">{authError}</p>}
            <button className="primary-button" type="submit">Sign in to the pantry <span>→</span></button>
            <p className="privacy-note">Your session is securely managed by Supabase Auth.</p>
          </form>
        </section>
      </main>
    );
  }

  return (
    <main>
      <header className="topbar">
        <a className="brand" href="#top">Share My Bread<span>.</span></a>
        <nav aria-label="Primary navigation">
          <a className="active" href="#inventory">Inventory</a>
          <button onClick={() => void openOrderHistory()}>Orders</button>
          <button onClick={() => setAssistantOpen(true)}>AI assistant</button>
        </nav>
        <div className="member-menu">
          <span className="avatar">{session.user.email?.charAt(0).toUpperCase()}</span>
          <div><strong>{session.user.user_metadata.display_name ?? "Demo member"}</strong><small>{session.user.email}</small></div>
          <button className="cart-pill" onClick={() => setCartOpen(true)}>{cart?.lines.length ?? 0} cart items · {money.format(cart?.subtotal ?? 0)}</button>
          <button onClick={() => getSupabaseBrowserClient().auth.signOut()}>Sign out</button>
        </div>
      </header>

      <section className="intro" id="top">
        <div>
          <p className="eyebrow ink">Live community catalogue</p>
          <h1>What shall we share today?</h1>
          <p>Thirty pantry essentials, one transparent inventory, and a smarter way to shop together.</p>
        </div>
        <button className="assistant-button" onClick={() => setAssistantOpen(true)}><span>✦</span> Ask the shopping assistant</button>
      </section>

      <button className="cart-strip" id="cart" onClick={() => setCartOpen(true)}>
        <div><p className="eyebrow ink">Current shared order</p><h2>{cart?.group_name ?? "Your cart"}</h2></div>
        {cartError ? <p className="cart-error">{cartError}</p> : cart?.lines.length ? (
          <div className="cart-lines">{cart.lines.map((line) => <span key={line.id}><strong>{line.quantity}×</strong> {line.name}</span>)}</div>
        ) : <p className="empty-cart">Your cart is empty. Ask the assistant to prepare something.</p>}
        <strong className="cart-total">{money.format(cart?.subtotal ?? 0)} <span>Review →</span></strong>
      </button>

      <section className="catalogue" id="inventory">
        <div className="catalogue-tools">
          <label className="search-field"><span>⌕</span><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search yogurt, curd, dahi, bread…" /></label>
          <div className="category-tabs" aria-label="Product categories">
            {categories.map((item) => <button key={item} className={category === item ? "selected" : ""} onClick={() => setCategory(item)}>{item}</button>)}
          </div>
          <p className="result-count">{filteredProducts.length} of {products.length} products</p>
        </div>

        {loadingProducts && <div className="state-card"><div className="loader" /><p>Opening the pantry…</p></div>}
        {productError && <div className="state-card error-state"><h2>Inventory could not load</h2><p>{productError}</p></div>}
        {!loadingProducts && !productError && filteredProducts.length === 0 && <div className="state-card"><h2>No products found</h2><p>Try another name, alias, or category.</p></div>}

        <div className="product-grid">
          {filteredProducts.map((product) => {
            const stock = stockDetails(product);
            return (
              <article className="product-card" key={product.id}>
                <div className={`product-mark mark-${product.category.toLowerCase()}`} aria-hidden="true"><span>{product.name.charAt(0)}</span><small>{product.category}</small></div>
                <div className="product-content">
                  <div className="product-heading"><p>{product.brand}</p><span className={`stock stock-${stock.tone}`}>{stock.label}</span></div>
                  <h2>{product.name}</h2>
                  <p className="description">{product.description}</p>
                  <p className="aliases">Also known as: {(product.aliases ?? []).slice(0, 3).join(", ")}</p>
                  <div className="product-foot"><div><strong>{money.format(Number(product.price))}</strong><span>{product.unit}</span></div><span className="sku">{product.sku}</span></div>
                  <button className="add-button" disabled={stock.tone === "out" || mutating || journey?.cycle.status !== "OPEN"} onClick={() => addProduct(product)}>{stock.tone === "out" ? "Unavailable" : journey?.cycle.status !== "OPEN" ? "Checkout started" : "+ Add to cart"}</button>
                </div>
              </article>
            );
          })}
        </div>
      </section>

      <button className="assistant-fab" onClick={() => setAssistantOpen(true)} aria-label="Open AI shopping assistant">✦</button>

      {cartOpen && <CartDrawer cart={cart} journey={journey} busy={mutating} error={journeyError || cartError} notice={journeyNotice} onClose={() => setCartOpen(false)} onQuantity={updateQuantity} onRemove={removeLine} onAction={journeyAction} />}
      {ordersOpen && <OrdersDrawer orders={orders} loading={ordersLoading} busy={mutating} error={ordersError} onClose={() => setOrdersOpen(false)} onAction={historyAction} />}

      {assistantOpen && (
        <div className="drawer-backdrop" onMouseDown={() => setAssistantOpen(false)}>
          <aside className="assistant-drawer" aria-label="AI shopping assistant" onMouseDown={(e) => e.stopPropagation()}>
            <div className="drawer-head"><div><p className="eyebrow">Gemini + Pinecone</p><h2>Shopping assistant</h2></div><button onClick={() => setAssistantOpen(false)} aria-label="Close">×</button></div>
            <p className="assistant-intro">Ask naturally. I can understand regional product names and prepare a proposal for you to approve.</p>
            <div className="suggestions">
              {["Add two tubs of curd for raita", "Find a vegan milk for coffee", "What can I use for rajma?"].map((item) => <button key={item} onClick={() => setAssistantQuery(item)}>{item}</button>)}
            </div>
            <form className="assistant-form" onSubmit={askAssistant}>
              <textarea value={assistantQuery} onChange={(e) => setAssistantQuery(e.target.value)} placeholder="What would you like to find?" rows={4} />
              <button className="primary-button" disabled={asking}>{asking ? "Thinking…" : "Ask assistant"}<span>→</span></button>
            </form>
            {assistantError && <p className="error-banner" role="alert">{assistantError}</p>}
            {assistantResult && (
              <div className="assistant-response">
                <span className="response-type">{(assistantResult.responseType ?? "ASSISTANT_RESPONSE").replaceAll("_", " ")}</span>
                <p>{assistantResult.message}</p>
                {!!assistantResult.candidates?.length && !assistantResult.proposal && <div className="candidate-options"><p>Choose a product:</p>{assistantResult.candidates.map((candidate) => <button key={candidate.productId} onClick={() => chooseCandidate(candidate.productId, candidate.name, candidate.quantity ?? 1)}>{candidate.quantity ?? 1}× {candidate.name}<span>Choose →</span></button>)}</div>}
                {assistantResult.proposal?.items && <div className="proposal-items"><p>{assistantResult.proposal.items.length > 1 ? "Select one or more items:" : "Proposed item:"}</p>{assistantResult.proposal.items.map((item) => {
                  const quantity = proposalQuantities[item.productId] ?? item.quantity;
                  const maximum = maximumAddable(item.productId);
                  const invalid = quantity > maximum;
                  return <div className="proposal-choice" key={item.productId}><label><input type="checkbox" checked={selectedProposalIds.includes(item.productId)} onChange={(event) => setSelectedProposalIds((current) => event.target.checked ? [...current, item.productId] : current.filter((id) => id !== item.productId))} /><span><strong>{quantity}×</strong> {item.name}</span></label>{invalid && <p className="stock-warning">Only {maximum} can be added to this cart. {maximum > 0 && <button onClick={() => setProposalQuantities((current) => ({ ...current, [item.productId]: maximum }))}>Use {maximum}</button>}</p>}</div>;
                })}</div>}
                {assistantResult.requiresConfirmation && assistantResult.proposal && !decision && (
                  <div className="proposal-actions">
                    <button className="primary-button" disabled={asking || !cart || !selectedProposalIds.length || assistantResult.proposal.items.some((item) => selectedProposalIds.includes(item.productId) && (proposalQuantities[item.productId] ?? item.quantity) > maximumAddable(item.productId))} onClick={confirmProposal}>{asking ? "Saving…" : "Confirm selected"}</button>
                    <button className="secondary-button" disabled={asking} onClick={() => setDecision("declined")}>Not now</button>
                  </div>
                )}
                {decision === "accepted" && <p className="decision-note">Confirmed and saved to your cart.</p>}
                {decision === "declined" && <p className="decision-note">No changes made.</p>}
                <small>Correlation: {assistantResult.correlationId}</small>
              </div>
            )}
            <p className="safety-note">The assistant proposes. You confirm. No inventory or cart mutation happens directly from AI.</p>
          </aside>
        </div>
      )}
    </main>
  );
}
