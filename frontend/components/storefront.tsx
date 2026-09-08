"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import type { Session } from "@supabase/supabase-js";
import { getSupabaseBrowserClient } from "@/lib/supabase";
import type { AssistantResponse, InventoryRow, Product } from "@/lib/types";

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
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("All");
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [assistantQuery, setAssistantQuery] = useState("");
  const [assistantResult, setAssistantResult] = useState<AssistantResponse | null>(null);
  const [assistantError, setAssistantError] = useState("");
  const [asking, setAsking] = useState(false);
  const [decision, setDecision] = useState<"accepted" | "declined" | null>(null);

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
  }, [session]);

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
    } catch (error) {
      setAssistantError(error instanceof Error ? error.message : "The assistant is unavailable.");
    } finally {
      setAsking(false);
    }
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
          <button onClick={() => setAssistantOpen(true)}>AI assistant</button>
        </nav>
        <div className="member-menu">
          <span className="avatar">{session.user.email?.charAt(0).toUpperCase()}</span>
          <div><strong>{session.user.user_metadata.display_name ?? "Demo member"}</strong><small>{session.user.email}</small></div>
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
                </div>
              </article>
            );
          })}
        </div>
      </section>

      <button className="assistant-fab" onClick={() => setAssistantOpen(true)} aria-label="Open AI shopping assistant">✦</button>

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
                <span className="response-type">{assistantResult.responseType.replaceAll("_", " ")}</span>
                <p>{assistantResult.message}</p>
                {assistantResult.requiresConfirmation && assistantResult.proposal && !decision && (
                  <div className="proposal-actions">
                    <button className="primary-button" onClick={() => setDecision("accepted")}>Confirm proposal</button>
                    <button className="secondary-button" onClick={() => setDecision("declined")}>Not now</button>
                  </div>
                )}
                {decision === "accepted" && <p className="decision-note">Proposal approved in the UI. Cart mutation will be connected through the deterministic backend in the next stage.</p>}
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
