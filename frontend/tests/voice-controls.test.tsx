import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ReadAloud, VoiceInput } from "@/components/voice-controls";

const session = vi.hoisted(() => ({ userId: "member-1" }));
vi.mock("@/lib/supabase", () => ({ getSupabaseBrowserClient: () => ({ auth: { getSession: async () => ({ data: { session: { user: { id: session.userId }, access_token: "test-token" } } }) } }) }));

const stopTrack = vi.fn();
const getUserMedia = vi.fn();
const fetchMock = vi.fn();
class Recorder {
  static latest: Recorder;
  static isTypeSupported() { return true; }
  state = "inactive";
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor() { Recorder.latest = this; }
  start() { this.state = "recording"; }
  stop() {
    this.state = "inactive";
    this.ondataavailable?.({ data: new Blob(["voice"], { type: "audio/webm" }) });
    this.onstop?.();
  }
}
class Player {
  static latest: Player;
  onended: (() => void) | null = null;
  onerror: (() => void) | null = null;
  pause = vi.fn();
  play = vi.fn().mockResolvedValue(undefined);
  constructor() { Player.latest = this; }
}
const response = (value: unknown) => ({ ok: true, json: async () => value });

beforeEach(() => {
  session.userId = "member-1";
  stopTrack.mockClear(); getUserMedia.mockReset(); fetchMock.mockReset();
  getUserMedia.mockResolvedValue({ getTracks: () => [{ stop: stopTrack }] });
  Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia } });
  vi.stubGlobal("MediaRecorder", Recorder);
  vi.stubGlobal("Audio", Player);
  vi.stubGlobal("fetch", fetchMock);
  Object.defineProperty(URL, "createObjectURL", { configurable: true, value: vi.fn(() => "blob:test") });
  Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
  process.env.NEXT_PUBLIC_API_BASE_URL = "https://backend.test";
  fetchMock.mockImplementation(async (url: string) => response(url.endsWith("status") ? { transcription: true } : { transcript: "Add two yogurts" }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

async function record() {
  const button = await screen.findByRole("button", { name: "🎙 Record request" });
  await waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(button);
  await screen.findByRole("button", { name: "■ Stop and transcribe" });
}

describe("Voice recording", () => {
  it("returns editable text without calling assistant or cart APIs", async () => {
    const transcript = vi.fn(); const busy = vi.fn();
    render(<VoiceInput userId="member-1" disabled={false} onTranscript={transcript} onBusy={busy} />);
    await record(); fireEvent.click(screen.getByRole("button", { name: "■ Stop and transcribe" }));
    await waitFor(() => expect(transcript).toHaveBeenCalledWith("Add two yogurts"));
    expect(fetchMock.mock.calls.map(call => call[0])).toEqual(["https://backend.test/api/voice/status", "https://backend.test/api/voice/transcribe"]);
    expect(stopTrack).toHaveBeenCalled(); expect(busy).toHaveBeenLastCalledWith(false);
    expect(screen.getByRole("status").textContent).toContain("cart has not changed");
  });

  it("cancels recording without uploading it", async () => {
    const transcript = vi.fn();
    render(<VoiceInput userId="member-1" disabled={false} onTranscript={transcript} onBusy={vi.fn()} />);
    await record(); fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(stopTrack).toHaveBeenCalled(); expect(transcript).not.toHaveBeenCalled();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("releases a microphone granted after the drawer closed", async () => {
    let grant!: (value: unknown) => void;
    getUserMedia.mockReturnValue(new Promise(resolve => { grant = resolve; }));
    const view = render(<VoiceInput userId="member-1" disabled={false} onTranscript={vi.fn()} onBusy={vi.fn()} />);
    await waitFor(() => expect((screen.getByRole("button", { name: "🎙 Record request" }) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByRole("button", { name: "🎙 Record request" }));
    view.unmount();
    await act(async () => { grant({ getTracks: () => [{ stop: stopTrack }] }); });
    expect(stopTrack).toHaveBeenCalled(); expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("drops a late transcript after unmount / account change", async () => {
    let finish!: (value: unknown) => void;
    fetchMock.mockImplementation(async (url: string) => url.endsWith("status") ? response({ transcription: true }) : new Promise(resolve => { finish = resolve; }));
    const transcript = vi.fn();
    const view = render(<VoiceInput userId="member-1" disabled={false} onTranscript={transcript} onBusy={vi.fn()} />);
    await record(); fireEvent.click(screen.getByRole("button", { name: "■ Stop and transcribe" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    view.unmount(); session.userId = "member-2";
    await act(async () => { finish(response({ transcript: "old private request" })); });
    expect(transcript).not.toHaveBeenCalled();
    expect(fetchMock.mock.calls[1][1].signal.aborted).toBe(true);
  });

  it("keeps the text fallback when microphone permission is denied", async () => {
    getUserMedia.mockRejectedValue(new DOMException("Denied", "NotAllowedError"));
    const busy = vi.fn();
    render(<VoiceInput userId="member-1" disabled={false} onTranscript={vi.fn()} onBusy={busy} />);
    await waitFor(() => expect((screen.getByRole("button", { name: "🎙 Record request" }) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByRole("button", { name: "🎙 Record request" }));
    await waitFor(() => expect(screen.getByRole("status").textContent).toContain("still type"));
    expect(busy).toHaveBeenLastCalledWith(false);
  });
});

describe("Spoken playback", () => {
  it("is user-triggered and releases playback on unmount", async () => {
    fetchMock.mockResolvedValue({ ok: true, blob: async () => new Blob(["audio"]) });
    const view = render(<ReadAloud userId="member-1" text="Your groceries are ready." />);
    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Listen with ElevenLabs" }));
    await screen.findByRole("button", { name: "■ Stop playback" });
    expect(JSON.parse(fetchMock.mock.calls[0][1].body).text).toBe("Your groceries are ready.");
    view.unmount(); expect(Player.latest.pause).toHaveBeenCalled();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:test");
  });

  it("does not play a response that arrives after cancellation", async () => {
    let finish!: (value: unknown) => void;
    fetchMock.mockReturnValue(new Promise(resolve => { finish = resolve; }));
    render(<ReadAloud userId="member-1" text="Review this proposal." />);
    fireEvent.click(screen.getByRole("button", { name: "Listen with ElevenLabs" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("button", { name: "Cancel voice loading" }));
    await act(async () => { finish({ ok: true, blob: async () => new Blob(["late audio"]) }); });
    expect(URL.createObjectURL).not.toHaveBeenCalled();
  });
});
