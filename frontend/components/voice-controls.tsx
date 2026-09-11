"use client";

import { useEffect, useRef, useState } from "react";
import { getSupabaseBrowserClient } from "@/lib/supabase";

const MAX_BYTES = 5 * 1024 * 1024;

async function voiceRequest(userId: string, path: string, init: RequestInit) {
  const base = process.env.NEXT_PUBLIC_API_BASE_URL;
  const { data } = await getSupabaseBrowserClient().auth.getSession();
  if (!base || data.session?.user.id !== userId) throw new Error("Your session has changed. Please sign in again.");
  const response = await fetch(`${base.replace(/\/$/, "")}/api/voice/${path}`, {
    ...init, headers: { ...init.headers, authorization: `Bearer ${data.session.access_token}` },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || "Voice is unavailable. Please use text.");
  }
  return response;
}

export function VoiceInput({ userId, disabled, onTranscript, onBusy }: {
  userId: string; disabled: boolean; onTranscript: (text: string) => void; onBusy: (busy: boolean) => void;
}) {
  const [phase, setPhase] = useState<"idle" | "requesting" | "recording" | "transcribing">("idle");
  const [available, setAvailable] = useState(false);
  const [message, setMessage] = useState("Checking voice availability…");
  const recorder = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const request = useRef<AbortController | null>(null);
  const generation = useRef(0);

  useEffect(() => {
    const control = new AbortController();
    void voiceRequest(userId, "status", { signal: control.signal }).then(r => r.json()).then(status => {
      if (control.signal.aborted) return;
      const supported = !!navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== "undefined";
      setAvailable(status.transcription && supported);
      setMessage(status.transcription && supported ? "Record up to 60 seconds, then review your transcript." : "Voice is unavailable. You can type your request.");
    }).catch(() => { if (!control.signal.aborted) setMessage("Voice is unavailable. You can type your request."); });
    return () => {
      control.abort(); generation.current += 1; request.current?.abort();
      if (timer.current) clearTimeout(timer.current);
      if (recorder.current) { recorder.current.onstop = null; recorder.current.ondataavailable = null; recorder.current.onerror = null; if (recorder.current.state !== "inactive") recorder.current.stop(); }
      stream.current?.getTracks().forEach(track => track.stop());
    };
  }, [userId]);

  function cancel() {
    generation.current += 1; request.current?.abort();
    if (timer.current) clearTimeout(timer.current);
    if (recorder.current) { recorder.current.onstop = null; recorder.current.ondataavailable = null; recorder.current.onerror = null; if (recorder.current.state !== "inactive") recorder.current.stop(); }
    stream.current?.getTracks().forEach(track => track.stop());
    recorder.current = null; stream.current = null;
    setPhase("idle"); onBusy(false);
  }

  async function start() {
    const current = ++generation.current;
    setPhase("requesting"); onBusy(true); setMessage("Allow microphone access to record your request.");
    try {
      const media = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (current !== generation.current) { media.getTracks().forEach(track => track.stop()); return; }
      stream.current = media;
      const mimeType = ["audio/webm;codecs=opus", "audio/mp4", "audio/ogg;codecs=opus"].find(type => MediaRecorder.isTypeSupported(type));
      if (!mimeType) throw new Error("This browser cannot record a supported format. Please type your request.");
      const capture = new MediaRecorder(media, { mimeType });
      recorder.current = capture;
      const chunks: Blob[] = [];
      let size = 0;
      capture.ondataavailable = event => {
        size += event.data.size;
        if (size > MAX_BYTES) { cancel(); setMessage("Recording is too large. Please record a shorter request."); return; }
        if (event.data.size) chunks.push(event.data);
      };
      capture.onerror = () => { cancel(); setMessage("Recording failed. Please try again or type your request."); };
      capture.onstop = async () => {
        media.getTracks().forEach(track => track.stop());
        if (timer.current) clearTimeout(timer.current);
        if (current !== generation.current) return;
        recorder.current = null; stream.current = null;
        setPhase("transcribing"); setMessage("Turning your recording into editable text…");
        const control = new AbortController(); request.current = control;
        const timeout = setTimeout(() => control.abort(), 40000);
        try {
          const audio = new Blob(chunks, { type: mimeType }); chunks.length = 0;
          if (!audio.size) throw new Error("No audio was captured. Please try again.");
          const response = await voiceRequest(userId, "transcribe", { method: "POST", body: audio, headers: { "content-type": mimeType }, signal: control.signal });
          const data = await response.json();
          if (current !== generation.current) return;
          onTranscript(data.transcript);
          setMessage("Review or edit the transcript, then choose Ask assistant. Your cart has not changed.");
        } catch (error) {
          if (current === generation.current) setMessage(error instanceof Error && error.name !== "AbortError" ? error.message : "Transcription timed out. Please try again or type your request.");
        } finally {
          clearTimeout(timeout);
          if (current === generation.current) { setPhase("idle"); onBusy(false); }
        }
      };
      capture.start(250);
      setPhase("recording"); setMessage("Recording… Stop when you are finished.");
      timer.current = setTimeout(() => { if (capture.state === "recording") capture.stop(); }, 60000);
    } catch (error) {
      if (current !== generation.current) return;
      cancel(); setMessage(error instanceof Error && error.name !== "NotAllowedError" ? error.message : "Microphone access was not granted. You can still type your request.");
    }
  }

  return <div className="voice-controls">
    <div className="voice-actions">
      <button className="voice-button" type="button" disabled={disabled || !available || phase === "requesting" || phase === "transcribing"} onClick={() => phase === "recording" ? recorder.current?.stop() : void start()}>
        {phase === "recording" ? "■ Stop and transcribe" : phase === "transcribing" ? "Transcribing…" : phase === "requesting" ? "Opening microphone…" : "🎙 Record request"}
      </button>
      {phase !== "idle" && <button className="secondary-button" type="button" onClick={() => { cancel(); setMessage("Recording cancelled. No request was sent to the assistant."); }}>Cancel</button>}
    </div>
    <p role="status">{message}</p>
    <small>Recording sends audio to ElevenLabs for transcription. Share My Bread does not save the recording.</small>
  </div>;
}

export function ReadAloud({ userId, text }: { userId: string; text: string }) {
  const [phase, setPhase] = useState<"idle" | "loading" | "playing">("idle");
  const [error, setError] = useState("");
  const audio = useRef<HTMLAudioElement | null>(null);
  const url = useRef<string | null>(null);
  const request = useRef<AbortController | null>(null);
  const timeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => {
    request.current?.abort(); request.current = null;
    if (audio.current) { audio.current.onended = null; audio.current.onerror = null; audio.current.pause(); }
    if (timeout.current) clearTimeout(timeout.current);
    if (url.current) URL.revokeObjectURL(url.current);
  }, [userId, text]);

  function stop() {
    request.current?.abort(); request.current = null;
    if (audio.current) { audio.current.onended = null; audio.current.onerror = null; audio.current.pause(); }
    if (timeout.current) clearTimeout(timeout.current);
    if (url.current) URL.revokeObjectURL(url.current);
    url.current = null; audio.current = null; setPhase("idle");
  }

  async function play() {
    if (phase !== "idle") { stop(); return; }
    setError(""); setPhase("loading");
    const control = new AbortController(); request.current = control;
    const requestTimeout = setTimeout(() => control.abort(), 40000);
    timeout.current = requestTimeout;
    try {
      const response = await voiceRequest(userId, "speak", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ text }), signal: control.signal });
      const blob = await response.blob();
      if (control.signal.aborted) return;
      url.current = URL.createObjectURL(blob);
      const player = new Audio(url.current); audio.current = player;
      player.onended = stop;
      player.onerror = () => { stop(); setError("Audio could not be played. Please read the text."); };
      await player.play();
      if (!control.signal.aborted) setPhase("playing");
    } catch (failure) {
      if (!control.signal.aborted) { stop(); setError(failure instanceof Error ? failure.message : "Spoken playback is unavailable. Please read the text."); }
      else if (request.current === control) { setPhase("idle"); setError("Spoken playback timed out. Please read the text."); }
    } finally { clearTimeout(requestTimeout); }
  }

  return <div className="read-aloud">
    <button className="voice-button" type="button" disabled={!text.trim() || text.length > 1200} onClick={() => void play()} title="Send this text to ElevenLabs and play it aloud">
      {phase === "loading" ? "Cancel voice loading" : phase === "playing" ? "■ Stop playback" : "Listen with ElevenLabs"}
    </button>
    {error && <p role="status">{error}</p>}
  </div>;
}
