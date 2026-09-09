import { NextResponse } from "next/server";

export const runtime = "nodejs";

export async function POST(request: Request) {
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

  const headers: HeadersInit = { "content-type": "application/json" };
  if (process.env.N8N_WEBHOOK_SECRET) {
    headers["x-smb-webhook-secret"] = process.env.N8N_WEBHOOK_SECRET;
  }

  try {
    const response = await fetch(webhookUrl, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
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
