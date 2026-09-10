"use client";

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Session } from "@supabase/supabase-js";
import { CartDrawer } from "@/components/cart-drawer";
import { OrdersDrawer } from "@/components/orders-drawer";
import { getSupabaseBrowserClient } from "@/lib/supabase";
import type { AssistantResponse, Cart, InventoryRow, Journey, MemoryStatus, NotificationFeed, OrderHistoryItem, Product, Workspace } from "@/lib/types";

const money = new Intl.NumberFormat("en-IE", {
  style: "currency",
  currency: "EUR",
});

type BrowserSpeechRecognition = {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: (event: { results: ArrayLike<{ 0: { transcript: string }; isFinal?: boolean }> }) => void;
  onerror: () => void;
  onend: () => void;
  start: () => void;
  stop: () => void;
};

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
  const [authMode, setAuthMode] = useState<"signin" | "signup">("signin");
  const [displayName, setDisplayName] = useState("");
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [workspaceError, setWorkspaceError] = useState("");
  const [groupName, setGroupName] = useState("");
  const [joinCode, setJoinCode] = useState("");
  const [pickupLabel, setPickupLabel] = useState("Community pickup");
  const [pickupAddress, setPickupAddress] = useState("Utrecht, Netherlands");
  const [cutoffAt, setCutoffAt] = useState("");
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
  const [notifications, setNotifications] = useState<NotificationFeed>({ unread: 0, items: [] });
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const rolloverStarted = useRef(false);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("All");
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [assistantQuery, setAssistantQuery] = useState("");
  const [assistantResult, setAssistantResult] = useState<AssistantResponse | null>(null);
  const [assistantError, setAssistantError] = useState("");
  const [asking, setAsking] = useState(false);
  const [listening, setListening] = useState(false);
  const voiceRecognition = useRef<BrowserSpeechRecognition | null>(null);
  const [memory, setMemory] = useState<MemoryStatus | null>(null);
  const [preference, setPreference] = useState("");
  const [memoryBusy, setMemoryBusy] = useState(false);
  const [memoryNotice, setMemoryNotice] = useState("");
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
    const responseText = await response.text();
    const value = responseText ? JSON.parse(responseText) : null;
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

  const refreshJourney = useCallback(async () => {
    setJourneyError("");
    try {
      setJourney(await backend("/api/journey/current") as Journey);
    } catch (error) {
      setJourneyError(error instanceof Error ? error.message : "Order journey unavailable.");
    }
  }, [backend]);

  const refreshWorkspace = useCallback(async () => {
    setWorkspaceError("");
    try {
      setWorkspace(await backend("/api/workspace/me") as Workspace);
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Workspace unavailable.");
    }
  }, [backend]);

  const refreshNotifications = useCallback(async () => {
    try {
      setNotifications(await backend("/api/notifications") as NotificationFeed);
    } catch {
      // Notifications are supplementary; the cart remains usable if this read fails.
    }
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
    void refreshWorkspace();
    void refreshNotifications();
  }, [session, refreshNotifications, refreshWorkspace]);

  async function readAllNotifications() {
    await backend("/api/notifications/read-all", { method: "POST" });
    await refreshNotifications();
  }

  async function resetDemoWorkspace() {
    if (!window.confirm("Reset the unfinished demo journey and open a clean cart? Completed order history will remain.")) return;
    setMutating(true);
    setJourneyError("");
    try {
      await backend("/api/operations/demo-reset", { method: "POST", body: JSON.stringify({ confirmation: "RESET DEMO WORKSPACE" }) });
      rolloverStarted.current = false;
      await Promise.all([refreshWorkspace(), refreshOrder(), openOrderHistory()]);
      setJourneyNotice("Demo workspace reset. A clean seven-day order cycle is open.");
    } catch (error) {
      setJourneyError(error instanceof Error ? error.message : "Demo reset failed.");
    } finally {
      setMutating(false);
    }
  }

  useEffect(() => {
    if (!session || !workspace?.groups.length) return;
    void refreshOrder();
  }, [session,workspace?.groups.length,refreshOrder]);

  useEffect(() => {
    if (!session || !workspace?.groups.length) return;
    const refreshSharedState = window.setInterval(() => {
      void Promise.all([refreshOrder(), refreshWorkspace(), refreshNotifications()]);
    }, 30000);
    return () => window.clearInterval(refreshSharedState);
  }, [session, workspace?.groups.length, refreshNotifications, refreshOrder, refreshWorkspace]);

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
      await Promise.all([refreshJourney(), refreshWorkspace()]);
    } catch (error) {
      setJourneyError(error instanceof Error ? error.message : "Cart update failed.");
    } finally {
      setMutating(false);
    }
  }

  function addProduct(product: Product) {
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
        "/api/journey/authorize": "Your items are authorized. The shared cart remains open until cutoff.",
        "/api/journey/decline": "You declined this cycle. Your items will not enter this order.",
        "/api/journey/close-cart": "Cutoff applied and member cash obligations calculated.",
        "/api/journey/commit-cash": "Cash commitment recorded.",
        "/api/journey/finalize": "Mock retailer order placed.",
        "/api/journey/collect-cash": "Cash collection recorded.",
        "/api/journey/collect-items": "Item collection recorded.",
        "/api/journey/fulfilment": "Order status updated.",
      };
      setJourneyNotice(messages[path] ?? "Order updated.");
      await Promise.all([refreshOrder(), refreshWorkspace(), refreshNotifications()]);
      if (path === "/api/journey/fulfilment" && body && "status" in body && ["FULFILLED", "CANCELLED"].includes(String(body.status))) {
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

  async function signUp(event: FormEvent) {
    event.preventDefault();
    setAuthError("");
    const { error } = await getSupabaseBrowserClient().auth.signUp({
      email,password,options:{ data:{ display_name: displayName || email.split("@")[0] } },
    });
    if (error) setAuthError(error.message);
    else setAuthError("Account created. If email confirmation is enabled, confirm it before signing in.");
  }

  async function groupAction(path: string, body: object) {
    setWorkspaceError("");
    try {
      setWorkspace(await backend(path,{ method:"POST",body:JSON.stringify(body) }) as Workspace);
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Group action failed.");
    }
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
        headers: { "content-type": "application/json", authorization: `Bearer ${session?.access_token ?? ""}` },
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

  async function refreshMemory() {
    try { setMemory(await backend("/api/memory") as MemoryStatus); } catch { setMemory(null); }
  }

  async function toggleMemory(enabled: boolean) {
    setMemoryBusy(true); setMemoryNotice("");
    try {
      await backend("/api/memory/consent", { method: "POST", body: JSON.stringify({ enabled }) });
      await refreshMemory();
      setMemoryNotice(enabled ? "Preference memory enabled." : "Preference memory disabled and erased.");
    } catch (error) { setMemoryNotice(error instanceof Error ? error.message : "Memory update failed."); }
    finally { setMemoryBusy(false); }
  }

  async function savePreference() {
    if (!preference.trim()) return;
    setMemoryBusy(true); setMemoryNotice("");
    try {
      await backend("/api/memory/preferences", { method: "POST", body: JSON.stringify({ preference: preference.trim() }) });
      setPreference(""); setMemoryNotice("Preference accepted. It may take a few seconds to appear.");
      window.setTimeout(() => void refreshMemory(), 2500);
    } catch (error) { setMemoryNotice(error instanceof Error ? error.message : "Preference could not be saved."); }
    finally { setMemoryBusy(false); }
  }

  async function deletePreference(id: string) {
    setMemoryBusy(true);
    try { await backend(`/api/memory/preferences/${id}`, { method: "DELETE" }); await refreshMemory(); }
    catch (error) { setMemoryNotice(error instanceof Error ? error.message : "Preference could not be deleted."); }
    finally { setMemoryBusy(false); }
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
      await refreshJourney();
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
    setAssistantResult((current) => {
      if (!current) return current;
      const existingItems = current.proposal?.items ?? [];
      const items = existingItems.some((item) => item.productId === productId)
        ? existingItems
        : [...existingItems, { productId, name, quantity }];
      const candidates = (current.candidates ?? []).filter((candidate) => candidate.productId !== productId);
      return {
        ...current,
        responseType: "CART_PROPOSAL",
        message: candidates.length
          ? `${name} is selected. Choose any other requested products, then confirm the selected items.`
          : `${name} is selected. Confirm before the selected items are added to your cart.`,
        requiresConfirmation: true,
        proposal: { action: "ADD_ITEMS", items },
        candidates,
      };
    });
    setSelectedProposalIds((current) => current.includes(productId) ? current : [...current, productId]);
    setProposalQuantities((current) => ({ ...current, [productId]: quantity }));
    setDecision(null);
  }

  function startVoiceInput() {
    if (listening && voiceRecognition.current) {
      voiceRecognition.current.stop();
      return;
    }
    const browserWindow = window as unknown as {
      SpeechRecognition?: new () => BrowserSpeechRecognition;
      webkitSpeechRecognition?: new () => BrowserSpeechRecognition;
    };
    const Recognition = browserWindow.SpeechRecognition ?? browserWindow.webkitSpeechRecognition;
    if (!Recognition) {
      setAssistantError("Voice input is not supported by this browser. You can still type the request.");
      return;
    }
    setAssistantError("");
    setListening(true);
    const recognition = new Recognition();
    voiceRecognition.current = recognition;
    recognition.lang = navigator.language || "en-GB";
    recognition.interimResults = true;
    recognition.continuous = true;
    recognition.onresult = (event) => {
      const transcript = Array.from(event.results).map((result) => result[0]?.transcript ?? "").join(" ").trim();
      if (transcript) setAssistantQuery(transcript);
    };
    recognition.onerror = () => setAssistantError("Voice input could not be captured. Please try again or type the request.");
    recognition.onend = () => { voiceRecognition.current = null; setListening(false); };
    recognition.start();
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
          <form className="login-card" onSubmit={authMode === "signin" ? signIn : signUp}>
            <p className="eyebrow ink">Member access</p>
            <h2>{authMode === "signin" ? "Welcome back" : "Create an account"}</h2>
            <p>{authMode === "signin" ? "Sign in with your Supabase account." : "Create a retail-member account, then create or join a group."}</p>
            {authMode === "signup" && <label>Display name<input value={displayName} onChange={(e) => setDisplayName(e.target.value)} required /></label>}
            <label>Email<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
            <label>Password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Enter your Supabase password" required /></label>
            {authError && <p className="error-banner" role="alert">{authError}</p>}
            <button className="primary-button" type="submit">{authMode === "signin" ? "Sign in to the pantry" : "Create account"} <span>→</span></button>
            <button className="secondary-button" type="button" onClick={() => { setAuthMode(authMode === "signin" ? "signup" : "signin"); setAuthError(""); }}>{authMode === "signin" ? "Need an account? Sign up" : "Already registered? Sign in"}</button>
            <p className="privacy-note">Your session is securely managed by Supabase Auth.</p>
          </form>
        </section>
      </main>
    );
  }

  if (!workspace) return <main className="center-stage"><div className="loader" aria-label="Loading workspace" />{workspaceError && <p className="error-banner">{workspaceError}</p>}</main>;

  if (!workspace.groups.length) {
    return <main className="login-page"><section className="login-story"><a className="brand brand-light" href="#">Share My Bread<span>.</span></a><div><p className="eyebrow">Shared ordering starts here</p><h1>Create or join<br />a buying group.</h1><p className="story-copy">A coordinator creates the group, cutoff and pickup point. Other members join using its code.</p></div></section><section className="login-panel"><div className="login-card"><p className="eyebrow ink">Group setup</p><h2>Hello, {workspace.profile.display_name}</h2><label>New group name<input value={groupName} onChange={(e) => setGroupName(e.target.value)} placeholder="Neighbourhood pantry" /></label><label>Join code<input value={joinCode} onChange={(e) => setJoinCode(e.target.value.toUpperCase())} placeholder="BREAD2026" /></label><label>Order cutoff<input type="datetime-local" value={cutoffAt} onChange={(e) => setCutoffAt(e.target.value)} /></label><label>Pickup point<input value={pickupLabel} onChange={(e) => setPickupLabel(e.target.value)} /></label><label>Pickup address<input value={pickupAddress} onChange={(e) => setPickupAddress(e.target.value)} /></label>{workspaceError && <p className="error-banner">{workspaceError}</p>}<button className="primary-button" disabled={groupName.length < 2 || joinCode.length < 6 || !cutoffAt} onClick={() => void groupAction("/api/groups",{ name:groupName,joinCode,pickupLabel,pickupAddress,cutoffAt:new Date(cutoffAt).toISOString() })}>Create group<span>→</span></button><button className="secondary-button" disabled={joinCode.length < 6} onClick={() => void groupAction("/api/groups/join",{ joinCode })}>Join existing group</button><button className="secondary-button" onClick={() => getSupabaseBrowserClient().auth.signOut()}>Sign out</button></div></section></main>;
  }

  const activeGroup = workspace.groups[0];
  const pendingMembers = activeGroup.members.filter((member) => member.decision === "PENDING").length;

  return (
    <main>
      <header className="topbar">
        <a className="brand" href="#top">Share My Bread<span>.</span></a>
        <nav aria-label="Primary navigation">
          <a className="active" href="#inventory">Inventory</a>
          <button onClick={() => void openOrderHistory()}>{workspace.profile.app_role === "ADMIN" ? "Orders & delivery" : "Orders"}</button>
          <button onClick={() => { setAssistantOpen(true); void refreshMemory(); }}>AI assistant</button>
        </nav>
        <div className="member-menu">
          <span className="avatar">{session.user.email?.charAt(0).toUpperCase()}</span>
          <div><strong>{workspace.profile.display_name}</strong><small>{workspace.profile.app_role} · {session.user.email}</small></div>
          <button className="notification-button" onClick={() => setNotificationsOpen((open) => !open)} aria-label={`${notifications.unread} unread notifications`}>●<span>{notifications.unread}</span></button>
          <button className="cart-pill" onClick={() => setCartOpen(true)}>{cart?.lines.length ?? 0} cart items · {money.format(cart?.subtotal ?? 0)}</button>
          <button onClick={() => getSupabaseBrowserClient().auth.signOut()}>Sign out</button>
        </div>
      </header>

      {notificationsOpen && <aside className="notification-panel" aria-label="Notifications">
        <div><h2>Notifications</h2><button disabled={!notifications.unread} onClick={() => void readAllNotifications()}>Mark all read</button></div>
        {!notifications.items.length && <p>No notifications yet.</p>}
        {notifications.items.map((item) => <article key={item.id} className={item.read_at ? "read" : "unread"}><strong>{item.title}</strong><p>{item.message}</p><small>{new Date(item.created_at).toLocaleString()}</small></article>)}
      </aside>}

      <section className="intro" id="top">
        <div>
          <p className="eyebrow ink">Live community catalogue</p>
          <h1>What shall we share today?</h1>
          <p>Thirty pantry essentials, one transparent inventory, and a smarter way to shop together.</p>
        </div>
        <button className="assistant-button" onClick={() => { setAssistantOpen(true); void refreshMemory(); }}><span>✦</span> Ask the shopping assistant</button>
      </section>

      <section className="group-dashboard" aria-label="Current group and order cycle">
        <div className="group-dashboard-title">
          <div><p className="eyebrow ink">Active buying group</p><h2>{activeGroup.name}</h2></div>
          <span className={`cycle-status cycle-${(activeGroup.cycle?.status ?? "none").toLowerCase()}`}>{activeGroup.cycle?.status.replaceAll("_", " ") ?? "NO CYCLE"}</span>
        </div>
        <dl className="group-facts">
          <div><dt>Your group role</dt><dd>{activeGroup.member_role}</dd></div>
          <div><dt>Join code</dt><dd>{activeGroup.join_code}</dd></div>
          <div><dt>Cutoff</dt><dd>{activeGroup.cycle ? new Date(activeGroup.cycle.cutoff_at).toLocaleString() : "Not scheduled"}</dd></div>
          <div><dt>Pickup</dt><dd>{activeGroup.pickup_label ?? "Not configured"}<small>{activeGroup.pickup_address}</small></dd></div>
        </dl>
        <div className="group-member-summary">
          <strong>{activeGroup.members.length} members</strong>
          <span>{pendingMembers} pending decision{pendingMembers === 1 ? "" : "s"}</span>
          <div className="member-chips">{activeGroup.members.map((member) => <span key={member.id} title={`${member.member_role} · ${member.app_role}`} className={`decision-${member.decision.toLowerCase()}`}>{member.display_name}<small>{member.decision}</small></span>)}</div>
          {workspace.profile.app_role === "ADMIN" && <button className="reset-demo-button" disabled={mutating} onClick={() => void resetDemoWorkspace()}>Reset unfinished demo</button>}
        </div>
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

      <button className="assistant-fab" onClick={() => { setAssistantOpen(true); void refreshMemory(); }} aria-label="Open AI shopping assistant">✦</button>

      {cartOpen && <CartDrawer cart={cart} journey={journey} busy={mutating} error={journeyError || cartError} notice={journeyNotice} onClose={() => setCartOpen(false)} onQuantity={updateQuantity} onRemove={removeLine} onAction={journeyAction} />}
      {ordersOpen && <OrdersDrawer orders={orders} loading={ordersLoading} busy={mutating} error={ordersError} isAdmin={workspace.profile.app_role === "ADMIN"} onClose={() => setOrdersOpen(false)} onAction={historyAction} />}

      {assistantOpen && (
        <div className="drawer-backdrop" onMouseDown={() => setAssistantOpen(false)}>
          <aside className="assistant-drawer" aria-label="AI shopping assistant" onMouseDown={(e) => e.stopPropagation()}>
            <div className="drawer-head"><div><p className="eyebrow">Gemini + Pinecone</p><h2>Shopping assistant</h2></div><button onClick={() => setAssistantOpen(false)} aria-label="Close">×</button></div>
            <p className="assistant-intro">Ask naturally. I can understand regional product names and prepare a proposal for you to approve.</p>
            <section className="memory-panel">
              <div><strong>Personal preferences (Mem0)</strong><label><input type="checkbox" checked={memory?.consent ?? false} disabled={memoryBusy || !memory?.configured} onChange={(event) => void toggleMemory(event.target.checked)} /> Remember mine</label></div>
              {!memory?.configured && <p>Memory is not enabled on the server yet.</p>}
              {memory?.consent && <>
                <div className="memory-add"><input value={preference} maxLength={240} onChange={(event) => setPreference(event.target.value)} placeholder="e.g. I prefer vegan milk" /><button type="button" disabled={memoryBusy || preference.trim().length < 3} onClick={() => void savePreference()}>Remember</button></div>
                {!!memory.memories.length && <ul>{memory.memories.map((item) => <li key={item.id}><span>{item.memory}</span><button type="button" disabled={memoryBusy} onClick={() => void deletePreference(item.id)}>Forget</button></li>)}</ul>}
              </>}
              {memoryNotice && <p role="status">{memoryNotice}</p>}
              <small>Only explicit grocery preferences are stored. Cart, payment, stock and audio are never sent to memory.</small>
            </section>
            <div className="suggestions">
              {["Add two tubs of curd for raita", "Find a vegan milk for coffee", "What can I use for rajma?"].map((item) => <button key={item} onClick={() => setAssistantQuery(item)}>{item}</button>)}
            </div>
            <form className="assistant-form" onSubmit={askAssistant}>
              <textarea value={assistantQuery} onChange={(e) => setAssistantQuery(e.target.value)} placeholder="What would you like to find?" rows={4} />
              <button className="voice-button" type="button" disabled={asking} onClick={startVoiceInput}>{listening ? "■ Stop listening" : "🎙 Speak request"}</button>
              <button className="primary-button" disabled={asking}>{asking ? "Thinking…" : "Ask assistant"}<span>→</span></button>
            </form>
            {assistantError && <p className="error-banner" role="alert">{assistantError}</p>}
            {assistantResult && (
              <div className="assistant-response">
                <span className="response-type">{(assistantResult.responseType ?? "ASSISTANT_RESPONSE").replaceAll("_", " ")}</span>
                <p>{assistantResult.message}</p>
                {!!assistantResult.candidates?.length && <div className="candidate-options"><p>{assistantResult.proposal ? "Choose another requested product:" : "Choose one or more requested products:"}</p>{assistantResult.candidates.map((candidate) => <button key={candidate.productId} onClick={() => chooseCandidate(candidate.productId, candidate.name, candidate.quantity ?? 1)}>{candidate.quantity ?? 1}× {candidate.name}<span>Add to proposal →</span></button>)}</div>}
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
