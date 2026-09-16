"use client";

import { useEffect, useRef, useState } from "react";
import { voiceRequest } from "./voice-controls";

export function LiveVoice({ userId, disabled, onBusy, onRequest }: {
  userId: string; disabled: boolean; onBusy: (busy: boolean) => void;
  onRequest: (text: string, signal: AbortSignal) => Promise<string | undefined>;
}) {
  const [active, setActive] = useState(false);
  const [status, setStatus] = useState("");
  const generation = useRef(0);
  const cleanup = useRef<() => void>(() => {});
  const busy = useRef(onBusy); busy.current = onBusy;
  const ask = useRef(onRequest); ask.current = onRequest;

  function stop() {
    generation.current++;
    cleanup.current(); cleanup.current = () => {};
    setActive(false); busy.current(false);
  }
  useEffect(() => () => { generation.current++; cleanup.current(); busy.current(false); }, [userId]);

  async function start() {
    const run = ++generation.current;
    setActive(true); busy.current(true); setStatus("Opening microphone…");
    let media: MediaStream | undefined;
    let context: AudioContext | undefined;
    let capture: MediaRecorder | undefined;
    let interval: ReturnType<typeof setInterval> | undefined;
    let deadline: ReturnType<typeof setTimeout> | undefined;
    let player: HTMLAudioElement | undefined;
    let objectUrl: string | undefined;
    let rejectPlayback: ((reason: Error) => void) | undefined;
    const control = new AbortController();
    const alive = () => run === generation.current && !control.signal.aborted;
    cleanup.current = () => {
      control.abort(); clearInterval(interval); clearTimeout(deadline);
      if (capture) { capture.onstop = null; capture.ondataavailable = null; if (capture.state !== "inactive") capture.stop(); }
      media?.getTracks().forEach(track => track.stop());
      if (context) void context.close();
      if (player) { player.onended = null; player.onerror = null; player.pause(); }
      rejectPlayback?.(new Error("Conversation ended."));
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
    try {
      if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") throw new Error("Live voice is unavailable in this browser. Use Record request or type instead.");
      media = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
      if (!alive()) { media.getTracks().forEach(track => track.stop()); return; }
      context = new AudioContext(); await context.resume();
      const analyser = context.createAnalyser(); analyser.fftSize = 2048;
      context.createMediaStreamSource(media).connect(analyser);
      const samples = new Float32Array(analyser.fftSize);
      const mimeType = ["audio/webm;codecs=opus", "audio/mp4", "audio/ogg;codecs=opus"].find(type => MediaRecorder.isTypeSupported(type));
      if (!mimeType) throw new Error("This browser cannot record a supported format.");
      deadline = setTimeout(() => { if (alive()) { stop(); setStatus("Five-minute session ended. Start live voice again to continue."); } }, 300000);
      const listen = () => {
        if (!alive() || !media) return;
        media.getAudioTracks().forEach(track => { track.enabled = true; });
        setStatus("Listening… Speak, then pause. Your request will be sent automatically.");
        const chunks: Blob[] = []; let size = 0; let speechFrames = 0;
        let heardSpeech = false; let lastSpeech = performance.now(); const started = lastSpeech;
        capture = new MediaRecorder(media, { mimeType });
        capture.ondataavailable = event => {
          size += event.data.size;
          if (size > 5 * 1024 * 1024) { stop(); setStatus("Recording too large. Start again with a shorter request."); return; }
          if (event.data.size) chunks.push(event.data);
        };
        capture.onerror = () => { stop(); setStatus("Recording failed. Please try again."); };
        capture.onstop = async () => {
          clearInterval(interval);
          media?.getAudioTracks().forEach(track => { track.enabled = false; });
          if (!alive()) return;
          try {
            setStatus("Transcribing…");
            const response = await voiceRequest(userId, "transcribe", { method: "POST", body: new Blob(chunks, { type: mimeType }), headers: { "content-type": mimeType }, signal: AbortSignal.any([control.signal, AbortSignal.timeout(40000)]) });
            chunks.length = 0;
            const { transcript } = await response.json();
            if (!alive()) return;
            setStatus("Thinking…");
            const reply = await ask.current(transcript, control.signal);
            if (!alive()) return;
            if (!reply) throw new Error("The assistant could not reply. Review the message below and try again.");
            if (reply.length > 1200) throw new Error("The reply is too long for voice. Please read it below.");
            setStatus("Preparing spoken reply…");
            const audio = await voiceRequest(userId, "speak", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ text: reply }), signal: AbortSignal.any([control.signal, AbortSignal.timeout(40000)]) });
            const blob = await audio.blob();
            if (!alive()) return;
            objectUrl = URL.createObjectURL(blob); player = new Audio(objectUrl);
            setStatus("Speaking… Your microphone is paused.");
            await new Promise<void>((resolve, reject) => {
              rejectPlayback = reject;
              player!.onended = () => resolve();
              player!.onerror = () => reject(new Error("Playback failed. Use Listen with ElevenLabs below."));
              void player!.play().catch(() => reject(new Error("Your browser blocked automatic audio. Use Listen with ElevenLabs below.")));
            });
            rejectPlayback = undefined;
            if (objectUrl) URL.revokeObjectURL(objectUrl); objectUrl = undefined; player = undefined;
            listen();
          } catch (error) {
            if (alive()) { stop(); setStatus(error instanceof Error ? error.message : "Voice failed. Please try again."); }
          }
        };
        capture.start(250);
        interval = setInterval(() => {
          if (!alive()) return;
          analyser.getFloatTimeDomainData(samples);
          const rms = Math.sqrt(samples.reduce((sum, value) => sum + value * value, 0) / samples.length);
          const now = performance.now();
          if (rms > 0.018) { speechFrames++; if (speechFrames >= 3) heardSpeech = true; lastSpeech = now; } else { speechFrames = 0; }
          if (heardSpeech && (now - lastSpeech > 1400 || now - started > 55000)) {
            clearInterval(interval); if (capture?.state === "recording") capture.stop();
          } else if (!heardSpeech && now - started > 20000) { stop(); setStatus("No speech detected. Start live voice when ready."); }
        }, 100);
      };
      listen();
    } catch (error) {
      if (alive()) { stop(); setStatus(error instanceof Error ? error.message : "Microphone unavailable."); }
    }
  }

  return <section className="live-voice" aria-label="Live voice conversation">
    <button type="button" className="voice-button" disabled={!active && disabled} onClick={() => active ? (stop(), setStatus("Live voice ended.")) : void start()}>{active ? "End live voice" : "Start live voice"}</button>
    <p role="status">{status || "Speak and hear replies automatically. Pause after each request."}</p>
    <small>Starting enables automatic sending of spoken requests. ElevenLabs may retain audio and transcripts. Cart changes still require Confirm selected. End live voice to stop the microphone.</small>
  </section>;
}
