import React, { useEffect, useRef, useState } from "react";
import { API_BASE } from "../../../lib/api";
import { ModelSelector } from "./ModelSelector";

interface ChatComposerProps {
  selectedModel?: string;
  isBusy?: boolean;
  onSubmit?: (message: string) => void;
  onTranscribeAudio?: (file: File) => Promise<string>;
  onAttach?: () => void;
  onVoice?: () => void;
  onModelChange?: (model: string) => void;
}

const LIVE_TRANSCRIPTION_SAMPLE_RATE = 24000;

function buildLiveTranscriptionUrl(): string {
  const baseUrl = API_BASE || window.location.origin;
  const url = new URL(baseUrl, window.location.origin);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.pathname = "/v1/audio/live-transcription";
  url.search = "";
  url.hash = "";
  return url.toString();
}

function downsampleBuffer(buffer: Float32Array, inputRate: number, outputRate: number): Float32Array {
  if (outputRate === inputRate) return buffer;

  const sampleRateRatio = inputRate / outputRate;
  const newLength = Math.round(buffer.length / sampleRateRatio);
  const result = new Float32Array(newLength);
  let offsetResult = 0;
  let offsetBuffer = 0;

  while (offsetResult < result.length) {
    const nextOffsetBuffer = Math.round((offsetResult + 1) * sampleRateRatio);
    let accum = 0;
    let count = 0;

    for (let i = offsetBuffer; i < nextOffsetBuffer && i < buffer.length; i += 1) {
      accum += buffer[i];
      count += 1;
    }

    result[offsetResult] = count > 0 ? accum / count : 0;
    offsetResult += 1;
    offsetBuffer = nextOffsetBuffer;
  }

  return result;
}

function floatTo16BitPcm(input: Float32Array): Uint8Array {
  const output = new Uint8Array(input.length * 2);
  const view = new DataView(output.buffer);

  for (let i = 0; i < input.length; i += 1) {
    const sample = Math.max(-1, Math.min(1, input[i]));
    view.setInt16(i * 2, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
  }

  return output;
}

function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";

  for (let i = 0; i < bytes.length; i += 1) {
    binary += String.fromCharCode(bytes[i]);
  }

  return btoa(binary);
}

function formatDuration(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60).toString().padStart(2, "0");
  const seconds = Math.floor(totalSeconds % 60).toString().padStart(2, "0");
  return `${minutes}:${seconds}`;
}

export const ChatComposer: React.FC<ChatComposerProps> = ({
  selectedModel = "gpt-5.6-luna",
  isBusy = false,
  onSubmit,
  onTranscribeAudio,
  onAttach,
  onVoice,
  onModelChange,
}) => {
  const [value, setValue] = useState("");
  const [isRecording, setIsRecording] = useState(false);
  const [isLiveConnected, setIsLiveConnected] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [audioStatus, setAudioStatus] = useState("");
  const [liveTranscript, setLiveTranscript] = useState("");
  const [finalTranscript, setFinalTranscript] = useState("");
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const websocketRef = useRef<WebSocket | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const liveTranscriptRef = useRef("");
  const liveCommittedTranscriptRef = useRef("");
  const liveDeltaByItemRef = useRef<Map<string, string>>(new Map());
  const timerRef = useRef<number | null>(null);
  const startedAtRef = useRef<number | null>(null);
  const isLocked = isBusy || isTranscribing;

  const autoGrow = () => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(160, textareaRef.current.scrollHeight)}px`;
    }
  };

  const cleanupLiveAudio = () => {
    processorRef.current?.disconnect();
    sourceRef.current?.disconnect();
    void audioContextRef.current?.close();
    processorRef.current = null;
    sourceRef.current = null;
    audioContextRef.current = null;
  };

  const stopMediaStream = () => {
    mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
    mediaStreamRef.current = null;
  };

  const cleanupTimer = () => {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
  };

  const closeLiveSocket = () => {
    const ws = websocketRef.current;

    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "commit" }));
      ws.send(JSON.stringify({ type: "close" }));
    }

    websocketRef.current = null;
    setIsLiveConnected(false);
  };

  useEffect(() => {
    return () => {
      cleanupTimer();
      cleanupLiveAudio();
      closeLiveSocket();
      stopMediaStream();
    };
  }, []);

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setValue(e.target.value);
    autoGrow();
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleSubmit = (e?: React.FormEvent) => {
    e?.preventDefault();
    const content = value.trim();
    if (!content || isLocked || isRecording) return;
    setValue("");
    setAudioStatus("");
    setFinalTranscript("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
    onSubmit?.(content);
  };

  const appendTranscription = (text: string) => {
    const cleanText = text.trim();
    if (!cleanText) return;

    setValue((prev) => {
      const separator = prev.trim() ? "\n\n" : "";
      return `${prev}${separator}${cleanText}`;
    });
    requestAnimationFrame(autoGrow);
  };

  const handleAudioFile = async (file: File | null) => {
    if (!file || isLocked || !onTranscribeAudio) return;

    setIsTranscribing(true);
    setAudioStatus("Trascrizione diarizzata in corso...");

    try {
      const text = await onTranscribeAudio(file);
      setFinalTranscript(text);
      appendTranscription(text);
      setAudioStatus(text ? "Transcript finale pronto." : "Nessun parlato rilevato.");
    } catch (err) {
      console.error(err);
      setAudioStatus("Trascrizione finale non riuscita.");
    } finally {
      setIsTranscribing(false);
    }
  };

  const startElapsedTimer = () => {
    startedAtRef.current = Date.now();
    setElapsedSeconds(0);
    cleanupTimer();
    timerRef.current = window.setInterval(() => {
      if (startedAtRef.current) {
        setElapsedSeconds(Math.floor((Date.now() - startedAtRef.current) / 1000));
      }
    }, 500);
  };

  const startLivePcmStreaming = (stream: MediaStream, ws: WebSocket) => {
    const win = window as unknown as { webkitAudioContext?: typeof AudioContext };
    const AudioContextCtor = window.AudioContext || win.webkitAudioContext;
    const audioContext = new AudioContextCtor();
    const source = audioContext.createMediaStreamSource(stream);
    const processor = audioContext.createScriptProcessor(4096, 1, 1);

    processor.onaudioprocess = (event) => {
      if (ws.readyState !== WebSocket.OPEN) return;

      const input = event.inputBuffer.getChannelData(0);
      const downsampled = downsampleBuffer(input, audioContext.sampleRate, LIVE_TRANSCRIPTION_SAMPLE_RATE);
      const pcm16 = floatTo16BitPcm(downsampled);

      ws.send(
        JSON.stringify({
          type: "audio",
          audio: bytesToBase64(pcm16),
        })
      );
    };

    source.connect(processor);
    processor.connect(audioContext.destination);
    audioContextRef.current = audioContext;
    sourceRef.current = source;
    processorRef.current = processor;
  };

  const finalizeRecording = () => {
    cleanupLiveAudio();
    cleanupTimer();
    stopMediaStream();
    closeLiveSocket();
    setIsRecording(false);
    setAudioStatus("Genero transcript finale con speaker attribution...");
  };

  const stopRecording = () => {
    const recorder = mediaRecorderRef.current;
    if (!recorder || recorder.state === "inactive") return;

    finalizeRecording();
    recorder.stop();
  };

  const startRecording = async () => {
    if (!onTranscribeAudio) {
      onVoice?.();
      return;
    }

    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setAudioStatus("Registrazione non supportata da questo browser.");
      return;
    }

    try {
      setAudioStatus("Connessione live transcription...");
      setLiveTranscript("");
      setFinalTranscript("");
      liveTranscriptRef.current = "";
      liveCommittedTranscriptRef.current = "";
      liveDeltaByItemRef.current = new Map();

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      const ws = new WebSocket(buildLiveTranscriptionUrl());

      mediaStreamRef.current = stream;
      websocketRef.current = ws;

      ws.onopen = () => {
        setIsLiveConnected(true);
        setIsRecording(true);
        setAudioStatus("Live transcript attivo.");
        startElapsedTimer();
        startLivePcmStreaming(stream, ws);
      };

      ws.onmessage = (event) => {
        const message = JSON.parse(event.data);

        if (message.type === "ready") {
          setIsLiveConnected(true);
        }

        if (message.type === "delta") {
          const itemId = message.item_id || "current";
          const currentDelta = liveDeltaByItemRef.current.get(itemId) || "";
          liveDeltaByItemRef.current.set(itemId, `${currentDelta}${message.delta || ""}`);
          const liveDraft = [
            liveCommittedTranscriptRef.current,
            ...Array.from(liveDeltaByItemRef.current.values()),
          ]
            .filter(Boolean)
            .join("\n")
            .trim();
          liveTranscriptRef.current = liveDraft;
          setLiveTranscript(liveDraft);
        }

        if (message.type === "completed" && message.transcript) {
          const itemId = message.item_id || "current";
          const transcript = String(message.transcript || "").trim();
          liveDeltaByItemRef.current.delete(itemId);
          liveCommittedTranscriptRef.current = `${liveCommittedTranscriptRef.current.trim()}\n${transcript}`.trim();
          const liveDraft = [
            liveCommittedTranscriptRef.current,
            ...Array.from(liveDeltaByItemRef.current.values()),
          ]
            .filter(Boolean)
            .join("\n")
            .trim();
          liveTranscriptRef.current = liveDraft;
          setLiveTranscript(liveDraft);
        }

        if (message.type === "error") {
          setAudioStatus(message.detail || "Errore live transcription.");
        }
      };

      ws.onerror = () => {
        setAudioStatus("Connessione live non riuscita.");
      };

      ws.onclose = () => {
        setIsLiveConnected(false);
      };

      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : MediaRecorder.isTypeSupported("audio/webm")
          ? "audio/webm"
          : "";
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);

      mediaRecorderRef.current = recorder;
      audioChunksRef.current = [];

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      recorder.onstop = () => {
        const type = mimeType || "audio/webm";
        const blob = new Blob(audioChunksRef.current, { type });
        const file = new File([blob], `intervista-${Date.now()}.webm`, { type });
        void handleAudioFile(file);
      };

      recorder.start(1000);
    } catch (err) {
      console.error(err);
      cleanupLiveAudio();
      cleanupTimer();
      closeLiveSocket();
      stopMediaStream();
      setIsRecording(false);
      setAudioStatus("Permesso microfono negato o dispositivo non disponibile.");
    }
  };

  const handleVoiceClick = () => {
    if (isTranscribing || isBusy) return;

    if (isRecording) {
      stopRecording();
      return;
    }

    void startRecording();
  };

  const hasInterviewPanel = isRecording || isTranscribing || liveTranscript || finalTranscript;

  return (
    <div className="composer-wrap">
      {hasInterviewPanel && (
        <section className="interview-panel" aria-label="Trascrizione intervista">
          <div className="interview-toolbar">
            <div>
              <div className="interview-title">Intervista live</div>
              <div className="interview-meta">
                <span className={`status-chip ${isLiveConnected ? "online" : ""}`}>
                  {isLiveConnected ? "Live WebSocket" : "Connessione"}
                </span>
                <span>{formatDuration(elapsedSeconds)}</span>
                <span>{isTranscribing ? "Diarizzazione finale" : "Draft realtime"}</span>
              </div>
            </div>
            <button
              className="btn-pill-light"
              type="button"
              onClick={() => {
                const text = finalTranscript || liveTranscript;
                appendTranscription(text);
              }}
              disabled={!finalTranscript && !liveTranscript}
              title="Inserisci transcript nel messaggio"
            >
              <svg viewBox="0 0 24 24">
                <polyline points="20 6 9 17 4 12" />
              </svg>
              <span>Usa transcript</span>
            </button>
          </div>

          <div className="interview-transcript">
            <div className="transcript-column">
              <div className="transcript-label">Live draft</div>
              <div className="transcript-body">
                {liveTranscript || "Il testo live apparira qui durante l'intervista."}
              </div>
            </div>
            <div className="transcript-column final">
              <div className="transcript-label">Finale diarizzato</div>
              <div className="transcript-body">
                {finalTranscript || "Dopo Stop, qui arriva il transcript definitivo con speaker attribution."}
              </div>
            </div>
          </div>
        </section>
      )}

      <form className="composer-box" onSubmit={handleSubmit}>
        <input
          ref={fileInputRef}
          type="file"
          accept="audio/*,.flac,.mp3,.mp4,.mpeg,.mpga,.m4a,.ogg,.wav,.webm"
          hidden
          onChange={(event) => {
            const file = event.target.files?.[0] || null;
            void handleAudioFile(file);
            event.target.value = "";
          }}
        />
        <textarea
          ref={textareaRef}
          rows={1}
          value={value}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder="Scrivi un messaggio..."
          disabled={isLocked}
          autoComplete="off"
        />
        {audioStatus && <div className="composer-status">{audioStatus}</div>}
        <div className="composer-bottom-bar">
          <ModelSelector selectedModel={selectedModel} onChange={onModelChange} />

          <div className="composer-actions">
            <button
              className="btn-pill-light"
              type="button"
              onClick={() => {
                if (onTranscribeAudio) {
                  fileInputRef.current?.click();
                } else {
                  onAttach?.();
                }
              }}
              disabled={isLocked || isRecording}
              title="Carica audio da trascrivere"
            >
              <svg viewBox="0 0 24 24">
                <path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
              </svg>
              <span>Audio</span>
            </button>
            <button
              className={`btn-pill-light ${isRecording ? "recording" : ""}`}
              type="button"
              onClick={handleVoiceClick}
              disabled={isBusy || isTranscribing}
              title={isRecording ? "Ferma intervista" : "Avvia intervista live"}
            >
              <svg viewBox="0 0 24 24">
                <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
                <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                <line x1="12" y1="19" x2="12" y2="23" />
                <line x1="8" y1="23" x2="16" y2="23" />
              </svg>
              <span>{isRecording ? "Stop" : "Intervista"}</span>
            </button>
            <button
              className="btn-send"
              type="submit"
              disabled={isLocked || isRecording || !value.trim()}
              title="Invia messaggio"
            >
              <span>Invia</span>
              <svg viewBox="0 0 24 24">
                <line x1="12" y1="19" x2="12" y2="5" />
                <polyline points="5 12 12 5 19 12" />
              </svg>
            </button>
          </div>
        </div>
      </form>
      <div className="footnote">Il modello puo commettere errori. Verifica sempre le risposte importanti.</div>
    </div>
  );
};
