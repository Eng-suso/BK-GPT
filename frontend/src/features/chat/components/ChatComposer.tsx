import React, { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowUp, Check, FileText, GitBranch, Mic, Paperclip, Plus, Square, Workflow, X } from "lucide-react";

import { Badge } from "@/ui/badge";
import { Button } from "@/ui/button";
import { Dialog, DialogContent, DialogTitle, DialogTrigger } from "@/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import { API_BASE } from "../../../lib/api";
import { appendAuthQueryParams } from "../../../lib/security";
import {
  MAX_CHAT_ATTACHMENTS,
  chatAttachmentKey,
  type ChatAttachment,
  type ChatAttachmentKind,
  type ChatMode,
  type ReasoningEffort,
} from "../../../contracts/chat";
import type { ChatScope } from "../chatScope";
import { AttachmentPicker } from "./AttachmentPicker";
import { ChatModeSelector } from "./ChatModeSelector";
import { ModelSelector } from "./ModelSelector";

interface ChatComposerProps {
  scope: ChatScope;
  selectedModel?: string;
  chatMode: ChatMode;
  onChatModeChange: (mode: ChatMode) => void;
  reasoningEffort: ReasoningEffort;
  onReasoningEffortChange: (effort: ReasoningEffort) => void;
  isBusy?: boolean;
  onSubmit?: (message: string, attachments: ChatAttachment[]) => void;
  onTranscribeAudio?: (file: File) => Promise<string>;
  onAttach?: () => void;
  onVoice?: () => void;
  onModelChange?: (model: string) => void;
}

const LIVE_TRANSCRIPTION_SAMPLE_RATE = 24000;

/**
 * Capture runs on the audio thread, not the main one.
 *
 * `ScriptProcessorNode` --- what this replaced --- fires on the main thread, so
 * a busy render drops whole blocks and the interview comes back with words
 * chewed in half. The worklet keeps capturing regardless and hands finished
 * chunks over the port.
 *
 * It is inlined as a Blob rather than a separate asset because it has to load
 * from the same origin as the page, and a bundled worklet URL is one more build
 * step to keep correct for the sake of twenty lines.
 */
const LIVE_CAPTURE_WORKLET = `
class LiveCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.chunk = new Float32Array(2048);
    this.offset = 0;
  }

  process(inputs) {
    const input = inputs[0] && inputs[0][0];
    if (!input) return true;

    for (let i = 0; i < input.length; i += 1) {
      this.chunk[this.offset] = input[i];
      this.offset += 1;

      if (this.offset === this.chunk.length) {
        this.port.postMessage(this.chunk.slice(0));
        this.offset = 0;
      }
    }

    return true;
  }
}

registerProcessor("live-capture", LiveCaptureProcessor);
`;

function buildLiveTranscriptionUrl(): string {
  const baseUrl = API_BASE || window.location.origin;
  const url = new URL(baseUrl, window.location.origin);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.pathname = "/v1/audio/live-transcription";
  url.search = "";
  url.hash = "";
  return appendAuthQueryParams(url).toString();
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

const ATTACHMENT_ICONS: Record<ChatAttachmentKind, React.ReactNode> = {
  source: <FileText aria-hidden="true" />,
  process: <Workflow aria-hidden="true" />,
  simulation_run: <GitBranch aria-hidden="true" />,
  note: <Paperclip aria-hidden="true" />,
};

const ATTACHMENT_MENU: ChatAttachmentKind[] = [
  "source",
  "process",
  "simulation_run",
  "note",
];

export const ChatComposer: React.FC<ChatComposerProps> = ({
  scope,
  selectedModel = "gpt-5.6-luna",
  chatMode,
  onChatModeChange,
  reasoningEffort,
  onReasoningEffortChange,
  isBusy = false,
  onSubmit,
  onTranscribeAudio,
  onAttach,
  onVoice,
  onModelChange,
}) => {
  const { t } = useTranslation("chat");
  const [value, setValue] = useState("");
  const [isRecording, setIsRecording] = useState(false);
  const [isLiveConnected, setIsLiveConnected] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [audioStatus, setAudioStatus] = useState("");
  const [liveTranscript, setLiveTranscript] = useState("");
  const [finalTranscript, setFinalTranscript] = useState("");
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [attachments, setAttachments] = useState<ChatAttachment[]>([]);
  const [pickerKind, setPickerKind] = useState<ChatAttachmentKind | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<AudioWorkletNode | ScriptProcessorNode | null>(null);
  const workletUrlRef = useRef<string | null>(null);
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
    if (workletUrlRef.current) {
      URL.revokeObjectURL(workletUrlRef.current);
      workletUrlRef.current = null;
    }
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
      // No explicit commit: server VAD owns the buffer now and the API rejects
      // a manual one. The trailing utterance closes on its own silence.
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
    const sent = attachments;
    setAttachments([]);
    onSubmit?.(content, sent);
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
      // The diarized pass is the transcript of record, but losing an interview
      // because it failed is worse than keeping the live draft without speaker
      // labels. The consultant is told which one they are holding.
      const draft = liveTranscriptRef.current.trim();

      if (draft) {
        setFinalTranscript(draft);
        appendTranscription(draft);
        setAudioStatus("Diarizzazione non riuscita: recuperato il draft live, senza speaker.");
      } else {
        setAudioStatus("Trascrizione finale non riuscita.");
      }
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

  const startLivePcmStreaming = async (stream: MediaStream, ws: WebSocket) => {
    const win = window as unknown as { webkitAudioContext?: typeof AudioContext };
    const AudioContextCtor = window.AudioContext || win.webkitAudioContext;
    // Asking for the target rate lets the browser resample natively; where the
    // hint is ignored, `downsampleBuffer` below still corrects the difference.
    const audioContext = new AudioContextCtor({ sampleRate: LIVE_TRANSCRIPTION_SAMPLE_RATE });
    const source = audioContext.createMediaStreamSource(stream);

    audioContextRef.current = audioContext;
    sourceRef.current = source;

    const sendFrames = (input: Float32Array) => {
      if (ws.readyState !== WebSocket.OPEN) return;

      const downsampled = downsampleBuffer(input, audioContext.sampleRate, LIVE_TRANSCRIPTION_SAMPLE_RATE);
      const pcm16 = floatTo16BitPcm(downsampled);

      ws.send(JSON.stringify({ type: "audio", audio: bytesToBase64(pcm16) }));
    };

    if (audioContext.audioWorklet) {
      const workletUrl = URL.createObjectURL(
        new Blob([LIVE_CAPTURE_WORKLET], { type: "application/javascript" }),
      );
      workletUrlRef.current = workletUrl;

      await audioContext.audioWorklet.addModule(workletUrl);

      const node = new AudioWorkletNode(audioContext, "live-capture");
      node.port.onmessage = (event: MessageEvent<Float32Array>) => sendFrames(event.data);

      // The graph only renders what reaches the destination, so the node has to
      // be connected --- through a silent gain, because routing a microphone to
      // the speakers is how you get feedback howl on a laptop with no headset.
      const silence = audioContext.createGain();
      silence.gain.value = 0;

      source.connect(node);
      node.connect(silence);
      silence.connect(audioContext.destination);

      processorRef.current = node;
      return;
    }

    // Safari without AudioWorklet. Same capture, on the main thread, with the
    // block drops that come with it.
    const processor = audioContext.createScriptProcessor(4096, 1, 1);
    processor.onaudioprocess = (event) => sendFrames(event.inputBuffer.getChannelData(0));
    source.connect(processor);
    processor.connect(audioContext.destination);
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
        startLivePcmStreaming(stream, ws).catch((err) => {
          // Capture failed to start. The recording itself keeps going, so the
          // interview still gets its diarized pass on stop --- only the live
          // draft is missing.
          console.error(err);
          setAudioStatus("Draft live non disponibile; la registrazione continua.");
        });
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

        if (message.type === "completed") {
          // A completed item with an empty transcript was dropped by the backend
          // language guard. Its provisional deltas must still go, or they stay
          // on screen forever as text nobody said.
          const itemId = message.item_id || "current";
          const transcript = String(message.transcript || "").trim();
          liveDeltaByItemRef.current.delete(itemId);
          if (transcript) {
            liveCommittedTranscriptRef.current = `${liveCommittedTranscriptRef.current.trim()}\n${transcript}`.trim();
          }
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
        <Dialog>
          <div className="mx-auto mb-2 flex w-full max-w-[var(--chat-measure)] flex-wrap items-center justify-between gap-2">
            <span className="text-xs text-muted-foreground" role="status">
              {isRecording ? `${t("composer.recording")} · ${formatDuration(elapsedSeconds)}` : isTranscribing ? t("composer.transcribing") : t("composer.transcriptReady")}
            </span>
            <DialogTrigger asChild>
              <Button type="button" size="sm" variant="outline">{t("composer.viewTranscript")}</Button>
            </DialogTrigger>
          </div>
          <DialogContent aria-describedby={undefined} className="max-h-[85dvh] overflow-y-auto border-border sm:max-w-2xl">
            <DialogTitle>{t("composer.transcriptTitle")}</DialogTitle>
          <div className="mb-3 flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className="text-sm font-semibold text-foreground">
                {isRecording ? t("composer.recording") : t("composer.transcriptReady")}
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <Badge
                  variant="outline"
                  className={cn(
                    "border-warning-border bg-warning-surface text-[var(--amber-700)]",
                    isLiveConnected &&
                      "border-success-border bg-success-surface text-[var(--color-status-success)]",
                  )}
                >
                  {isRecording ? (isLiveConnected ? t("composer.recording") : t("composer.connecting")) : t("composer.transcriptReady")}
                </Badge>
                <span>{formatDuration(elapsedSeconds)}</span>
                <span>
                  {isTranscribing ? t("composer.transcribing") : ""}
                </span>
              </div>
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => {
                const text = finalTranscript || liveTranscript;
                appendTranscription(text);
              }}
              disabled={!finalTranscript && !liveTranscript}
              title="Inserisci transcript nel messaggio"
            >
              <Check />
              Usa transcript
            </Button>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="min-w-0 overflow-hidden rounded-lg border border-border bg-muted/40">
              <div className="flex h-8 items-center border-b border-border px-3 text-[10.5px] font-semibold uppercase tracking-[0.055em] text-muted-foreground">
                Live draft
              </div>
              <div className="h-[112px] overflow-y-auto whitespace-pre-wrap p-3 text-[13px] leading-normal text-foreground @max-[540px]/composer-wrap:h-[92px]">
                {liveTranscript ||
                  "Il testo live apparira qui durante l'intervista."}
              </div>
            </div>
            <div className="min-w-0 overflow-hidden rounded-lg border border-[var(--green-200)] bg-[var(--green-50)]">
              <div className="flex h-8 items-center border-b border-border px-3 text-[10.5px] font-semibold uppercase tracking-[0.055em] text-muted-foreground">
                Finale diarizzato
              </div>
              <div className="h-[112px] overflow-y-auto whitespace-pre-wrap p-3 text-[13px] leading-normal text-foreground @max-[540px]/composer-wrap:h-[92px]">
                {finalTranscript ||
                  "Dopo Stop, qui arriva il transcript definitivo con speaker attribution."}
              </div>
            </div>
          </div>
          </DialogContent>
        </Dialog>
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
        {/* Sopra il testo, non dentro un menu: quello che stai per mandare deve
            restare a vista finche' non parte, e si deve poter togliere. */}
        {attachments.length > 0 && (
          <ul className="composer-chips" aria-label={t("attach.listLabel")}>
            {attachments.map((attachment) => (
              <li key={chatAttachmentKey(attachment)} className="composer-chip">
                <span className="composer-chip-icon">
                  {ATTACHMENT_ICONS[attachment.kind]}
                </span>
                <span className="composer-chip-label" title={attachment.label}>
                  {attachment.label}
                </span>
                <button
                  type="button"
                  className="composer-chip-remove"
                  aria-label={t("attach.remove", { label: attachment.label })}
                  onClick={() =>
                    setAttachments((prev) =>
                      prev.filter(
                        (item) =>
                          chatAttachmentKey(item) !== chatAttachmentKey(attachment),
                      ),
                    )
                  }
                >
                  <X aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
        )}

        <textarea
          ref={textareaRef}
          rows={1}
          value={value}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder={t("composer.placeholder")}
          aria-label={t("composer.placeholder")}
          disabled={isLocked}
          autoComplete="off"
          className="max-h-[180px] min-h-[42px] w-full resize-none border-none bg-transparent px-0.5 py-1 text-sm leading-normal text-foreground outline-none placeholder:text-muted-foreground/90 disabled:opacity-60"
        />
        {audioStatus && (
          <div className="min-h-[18px] px-0.5 text-xs leading-normal text-muted-foreground">
            {audioStatus}
          </div>
        )}
        <div className="composer-bottom-bar">
          <div className="composer-bottom-left">
            {/* "+" apre cosa alleghi; la modalita' dice come lavora l'agente.
                Il microfono sta a destra, accanto a Invia: e' un modo di
                mandare il messaggio, non un'impostazione della riga. */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  className="composer-add"
                  type="button"
                  variant="outline"
                  size="icon-sm"
                  disabled={isLocked || isRecording}
                  aria-label={t("composer.addLabel")}
                  title={t("composer.addLabel")}
                >
                  <Plus />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" side="top">
                {ATTACHMENT_MENU.map((attachmentKind) => (
                  <DropdownMenuItem
                    key={attachmentKind}
                    disabled={attachments.length >= MAX_CHAT_ATTACHMENTS}
                    onSelect={() => setPickerKind(attachmentKind)}
                  >
                    {ATTACHMENT_ICONS[attachmentKind]}
                    {t(`attach.${attachmentKind}.menu`)}
                  </DropdownMenuItem>
                ))}
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  onSelect={() => {
                    if (onTranscribeAudio) {
                      fileInputRef.current?.click();
                    } else {
                      onAttach?.();
                    }
                  }}
                >
                  <Paperclip />
                  {t("composer.audioUpload")}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>

            <ChatModeSelector
              value={chatMode}
              onChange={onChatModeChange}
              effort={reasoningEffort}
              onEffortChange={onReasoningEffortChange}
              disabled={isBusy}
            />
            <ModelSelector selectedModel={selectedModel} onChange={onModelChange} />
          </div>

          <div className="composer-actions">
            {/* In registrazione il microfono diventa Stop con il tempo a vista:
                uno stato attivo deve essere fermabile in un click. */}
            {isRecording ? (
              <Button
                className="composer-stop"
                type="button"
                variant="outline"
                size="sm"
                onClick={handleVoiceClick}
                disabled={isTranscribing}
                title={t("composer.stopHint")}
              >
                <Square />
                <span>{t("composer.stop")}</span>
                <span className="composer-stop-time">{formatDuration(elapsedSeconds)}</span>
              </Button>
            ) : (
              <Button
                className="composer-mic"
                type="button"
                variant="ghost"
                size="icon-sm"
                onClick={handleVoiceClick}
                disabled={isBusy || isTranscribing}
                aria-label={t("composer.interviewStart")}
                title={t("composer.interviewStart")}
              >
                <Mic />
              </Button>
            )}
            <Button
              className="btn-send"
              type="submit"
              size="sm"
              disabled={isLocked || isRecording || !value.trim()}
              aria-label={t("composer.send")}
              title={t("composer.sendHint")}
            >
              <span>{t("composer.send")}</span>
              <ArrowUp />
            </Button>
          </div>
        </div>
      </form>
      <AttachmentPicker
        kind={pickerKind}
        scope={scope}
        onClose={() => setPickerKind(null)}
        onPick={(attachment) => {
          setPickerKind(null);
          setAttachments((prev) =>
            prev.some((item) => chatAttachmentKey(item) === chatAttachmentKey(attachment))
              ? prev
              : [...prev, attachment].slice(0, MAX_CHAT_ATTACHMENTS),
          );
        }}
      />

      <div className="footnote mt-2 text-center text-[11px] text-muted-foreground">
        {t("composer.disclaimer")}
      </div>
    </div>
  );
};
