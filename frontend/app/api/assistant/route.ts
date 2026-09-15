import { NextResponse } from "next/server";

export const runtime = "nodejs";

export async function POST(request: Request) {
  const authorization = request.headers.get("authorization");
  if (!authorization || !/^Bearer \S+$/i.test(authorization)) {
    return NextResponse.json({ error: "Sign in to use the assistant." }, { status: 401 });
  }
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
  const webhookUrl = process.env.N8N_AGENT_WEBHOOK_URL;

  if (!webhookUrl || !apiBaseUrl) {
    return NextResponse.json(
      { error: "The assistant is not configured." },
      { status: 503 },
    );
  }

  // FastAPI verifies the token with Supabase and reads active membership from the database.
  // Never authorize from client-supplied IDs or decoded, unverified JWT claims.
  let actor: { userId: string; groupId: string; role: string };
  let cycleId: string | null;
  try {
    const response = await fetch(`${apiBaseUrl.replace(/\/$/, "")}/api/workspace/me`, {
      headers: { authorization }, cache: "no-store", signal: AbortSignal.timeout(10000),
      redirect: "error",
    });
    if (response.status === 401 || response.status === 403) {
      return NextResponse.json(
        { error: response.status === 401 ? "Sign in to use the assistant." : "Assistant access is not allowed." },
        { status: response.status },
      );
    }
    if (!response.ok) throw new Error("Workspace verification failed");
    const workspace = await response.json();
    if (!workspace || typeof workspace.profile?.id !== "string" || !workspace.profile.id ||
        typeof workspace.profile.can_shop !== "boolean" || !Array.isArray(workspace.groups)) {
      throw new Error("Invalid workspace response");
    }
    if (!workspace.profile.can_shop || workspace.groups.length !== 1) {
      return NextResponse.json({ error: "An active shopping workspace is required." }, { status: 403 });
    }
    const group = workspace.groups[0];
    if (!group || typeof group.id !== "string" || !group.id ||
        !["MEMBER", "ADMIN"].includes(workspace.profile.app_role) ||
        (group.cycle != null && (typeof group.cycle.id !== "string" || !group.cycle.id))) {
      throw new Error("Invalid workspace context");
    }
    actor = { userId: workspace.profile.id, groupId: group.id, role: workspace.profile.app_role };
    cycleId = group.cycle?.id ?? null;
  } catch {
    return NextResponse.json({ error: "Assistant access could not be verified. Please try again." }, { status: 503 });
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON request." }, { status: 400 });
  }

  if (!body || typeof body !== "object" || Array.isArray(body) ||
      !("message" in body) || typeof body.message !== "string") {
    return NextResponse.json({ error: "A text message is required." }, { status: 400 });
  }
  let memoryContext: string[] = [];
  try {
    const query = body.message.slice(0, 500);
    const memoryResponse = await fetch(`${apiBaseUrl.replace(/\/$/, "")}/api/memory/context?query=${encodeURIComponent(query)}`, {
      headers: { authorization }, cache: "no-store", signal: AbortSignal.timeout(5000),
    });
    if (memoryResponse.ok) memoryContext = (await memoryResponse.json()).memories ?? [];
  } catch {
    // Optional memory must never make the shopping assistant unavailable.
  }

  const headers: HeadersInit = { "content-type": "application/json" };
  if (process.env.N8N_WEBHOOK_SECRET) {
    headers["x-smb-webhook-secret"] = process.env.N8N_WEBHOOK_SECRET;
  }

  try {
    const response = await fetch(webhookUrl, {
      method: "POST",
      headers,
      body: JSON.stringify({
        message: body.message, channel: "WEB", userId: actor.userId, groupId: actor.groupId,
        actor, cycleId, memoryContext,
      }),
      cache: "no-store",
      signal: AbortSignal.timeout(30000),
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

    return NextResponse.json(normalized, { status: response.status });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Assistant request failed.";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
