import { NextResponse } from "next/server";
import { checkRail, GuardrailUnavailable } from "@/lib/guardrails";

function refusal() {
  return NextResponse.json({ responseType: "REFUSAL", message: "I cannot help with that request. You can browse the catalogue manually.", requiresConfirmation: false, correlationId: crypto.randomUUID(), proposal: null, candidates: [] });
}

function safetyUnavailable() {
  return NextResponse.json({ error: "Safety checks are unavailable. Please try again or browse the catalogue manually." }, { status: 503 });
}

export const runtime = "nodejs";

export async function POST(request: Request) {
  const mode = process.env.ASSISTANT_GUARDRAILS_MODE ?? "guarded";
  if (!["baseline", "guarded"].includes(mode)) return safetyUnavailable();
  const guarded = mode === "guarded";
  const webhookUrl = process.env.N8N_AGENT_WEBHOOK_URL;

  if (!webhookUrl) {
    return NextResponse.json(
      { error: "The assistant webhook has not been configured yet." },
      { status: 503 },
    );
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON request." }, { status: 400 });
  }

  if (guarded) {
    if (!body || typeof body !== "object" || Array.isArray(body) ||
        !("message" in body) || typeof body.message !== "string" ||
        body.message.trim().length < 2 || body.message.length > 500) {
      return NextResponse.json({ error: "Enter a shopping request of 2-500 characters." }, { status: 400 });
    }
    try {
      const checked = await checkRail("input", body.message);
      if (checked.status === "blocked") return refusal();
      if (checked.text.length < 2 || checked.text.length > 500) return safetyUnavailable();
      // No unchecked nested message, system instructions, actor, or memory from the caller.
      body = { message: checked.text, channel: "WEB" };
    } catch {
      return safetyUnavailable();
    }
  }

  const authorization = request.headers.get("authorization");
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
  let memoryContext: string[] = [];
  if (authorization && apiBaseUrl && body && typeof body === "object" && "message" in body) {
    try {
      const query = String((body as { message?: unknown }).message ?? "").slice(0, 500);
      const memoryResponse = await fetch(`${apiBaseUrl.replace(/\/$/, "")}/api/memory/context?query=${encodeURIComponent(query)}`, {
        headers: { authorization }, cache: "no-store", signal: AbortSignal.timeout(5000),
      });
      if (memoryResponse.ok) memoryContext = (await memoryResponse.json()).memories ?? [];
    } catch {
      // Optional memory must never make the shopping assistant unavailable.
    }
  }

  if (guarded) {
    try {
      if (!Array.isArray(memoryContext) || memoryContext.length > 5 ||
          !memoryContext.every(value => typeof value === 'string' && value.length <= 240)) {
        throw new GuardrailUnavailable();
      }
      const checked = memoryContext.length
        ? await checkRail('retrieval', JSON.stringify(memoryContext))
        : { status: 'passed', text: '[]' };
      const values: unknown = checked.status === 'blocked' ? [] : JSON.parse(checked.text);
      if (!Array.isArray(values) || values.length > 5 ||
          !values.every(value => typeof value === 'string' && value.length <= 240)) {
        throw new GuardrailUnavailable();
      }
      memoryContext = values;
    } catch {
      // Memory is optional. Withhold it completely when its mandatory check fails.
      memoryContext = [];
    }
  }

  const headers: HeadersInit = { "content-type": "application/json" };
  if (process.env.N8N_WEBHOOK_SECRET) {
    headers["x-smb-webhook-secret"] = process.env.N8N_WEBHOOK_SECRET;
  }

  try {
    const response = await fetch(webhookUrl, {
      method: "POST",
      headers,
      body: JSON.stringify({ ...(body as object), memoryContext }),
      cache: "no-store",
      signal: AbortSignal.timeout(guarded ? 60000 : 30000),
    });

    const text = await response.text();
    let result: unknown;
    try {
      result = JSON.parse(text);
    } catch {
      result = { error: text || "n8n returned an empty response." };
    }

    const normalized = Array.isArray(result) ? result[0] : result;
    if (
      response.ok &&
      (!normalized ||
        typeof normalized !== "object" ||
        !("responseType" in normalized) ||
        typeof normalized.responseType !== "string")
    ) {
      return NextResponse.json(
        { error: "n8n returned an incomplete assistant response." },
        { status: 502 },
      );
    }

    if (guarded) {
      if (!response.ok) return NextResponse.json({ error: "The assistant is unavailable." }, { status: 502 });
      // Check the entire JSON envelope, including product names and candidates.
      const draft = JSON.stringify(normalized);
      if (draft.length > 16000) return safetyUnavailable();
      const checked = await checkRail("output", draft);
      // Never apply free-text rewrites to a structured cart proposal.
      if (checked.status === "blocked" || checked.status === "modified") return refusal();
      const value = normalized as { responseType: string; requiresConfirmation?: boolean; proposal?: unknown };
      if (value.responseType === "CART_PROPOSAL" && (value.requiresConfirmation !== true || !value.proposal)) {
        return refusal();
      }
    }
    return NextResponse.json(normalized, { status: response.status });
  } catch (error) {
    if (error instanceof GuardrailUnavailable) return safetyUnavailable();
    if (guarded) return NextResponse.json({ error: "The assistant is unavailable." }, { status: 502 });
    const message = error instanceof Error ? error.message : "Assistant request failed.";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
