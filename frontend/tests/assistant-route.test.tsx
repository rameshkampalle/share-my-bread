// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { POST } from "@/app/api/assistant/route";

const fetchMock = vi.fn();
const workspace = {
  profile: { id: "member-1", can_shop: true, app_role: "MEMBER" },
  groups: [{ id: "group-1", cycle: { id: "cycle-1" } }],
};
const json = (value: unknown, status = 200) => Response.json(value, { status });
const request = (authorization: string | null = "Bearer valid-token", body: unknown = { message: "Find bread" }) =>
  new Request("http://localhost/api/assistant", {
    method: "POST",
    headers: { "content-type": "application/json", ...(authorization === null ? {} : { authorization }) },
    body: JSON.stringify(body),
  });

beforeEach(() => {
  vi.stubEnv("N8N_AGENT_WEBHOOK_URL", "https://n8n.example/assistant");
  vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "https://api.example");
  vi.stubGlobal("fetch", fetchMock);
  fetchMock.mockReset();
  fetchMock.mockImplementation(async (url: string) => {
    if (url.endsWith("/workspace/me")) return json(workspace);
    if (url.includes("/memory/context")) return json({ memories: ["Prefers rye"] });
    return json({ responseType: "ANSWER", message: "Found bread" });
  });
});
afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); });

describe("assistant authentication boundary", () => {
  it.each([null, "Basic token", "Bearer "])("rejects missing/malformed credentials: %s", async (header) => {
    expect((await POST(request(header))).status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each([401, 403, 500])("fails closed on backend status %s", async (status) => {
    fetchMock.mockResolvedValueOnce(json({ detail: "private diagnostic" }, status));
    const response = await POST(request());
    expect(response.status).toBe(status === 500 ? 503 : status);
    expect(await response.text()).not.toContain("private diagnostic");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("fails closed when verification times out", async () => {
    fetchMock.mockRejectedValueOnce(new Error("private diagnostic"));
    expect((await POST(request())).status).toBe(503);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it.each([
    { ...workspace, profile: { ...workspace.profile, can_shop: false } },
    { ...workspace, groups: [] },
    { ...workspace, groups: [...workspace.groups, { id: "group-2" }] },
  ])("denies unauthorized or ambiguous workspaces", async (value) => {
    fetchMock.mockResolvedValueOnce(json(value));
    expect((await POST(request())).status).toBe(403);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it.each([null, {}, { profile: {}, groups: [{}] }])("rejects malformed verification responses", async (value) => {
    fetchMock.mockResolvedValueOnce(json(value));
    expect((await POST(request())).status).toBe(503);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("requires backend configuration", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "");
    expect((await POST(request())).status).toBe(503);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each([null, [], {}, { message: 123 }])("rejects requests without a text message", async (body) => {
    expect((await POST(request("Bearer valid-token", body))).status).toBe(400);
    expect(fetchMock.mock.calls.every(([url]) => url.endsWith("/workspace/me"))).toBe(true);
  });

  it("replaces all client identity/context with verified workspace values", async () => {
    const response = await POST(request("Bearer valid-token", {
      message: "Find bread", userId: "victim", groupId: "other-group", cycleId: "other-cycle",
      actor: { userId: "victim", role: "ADMIN" }, data: { cycleId: "other-cycle" },
      memoryContext: ["malicious memory"], role: "ADMIN",
    }));
    expect(response.status).toBe(200);
    expect(fetchMock.mock.calls[0][0]).toBe("https://api.example/api/workspace/me");
    expect(fetchMock.mock.calls[0][1].headers.authorization).toBe("Bearer valid-token");
    const [url, options] = fetchMock.mock.calls.at(-1)!;
    expect(url).toBe("https://n8n.example/assistant");
    expect(JSON.parse(options.body)).toEqual({
      message: "Find bread", channel: "WEB", userId: "member-1", groupId: "group-1", cycleId: "cycle-1",
      actor: { userId: "member-1", groupId: "group-1", role: "MEMBER" }, memoryContext: ["Prefers rye"],
    });
    expect(options.headers).not.toHaveProperty("authorization");
  });

  it("preserves optional memory fallback after authorization", async () => {
    fetchMock.mockResolvedValueOnce(json(workspace)).mockRejectedValueOnce(new Error("Memory unavailable"));
    expect((await POST(request())).status).toBe(200);
    expect(JSON.parse(fetchMock.mock.calls.at(-1)![1].body).memoryContext).toEqual([]);
  });
});
