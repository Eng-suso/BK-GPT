/**
 * Il turno in corso vive fuori da React.
 *
 * Prima lo stream era uno `useState` dentro `useChatStream`: cambiare pagina
 * smontava il componente, la risposta a meta' spariva e il turno andava perso
 * anche se il backend lo stava ancora scrivendo. Qui il turno sta in un piccolo
 * store a livello di modulo — i componenti si iscrivono, ma nessun componente lo
 * possiede. Cosi':
 *
 * - navigare via e tornare ritrova il turno dov'era;
 * - fermare vuol dire annullare la richiesta e tenersi il pezzo gia' scritto;
 * - scrivere mentre l'agente lavora mette il messaggio in coda invece di
 *   perderlo o di forzare due turni sovrapposti sullo stesso thread.
 */

import { httpErrorMessage } from "@/lib/http";
import type { ChatAttachment } from "@/contracts/chat";
import type { ChatMessage } from "../types";
import {
  completeAgentActivity,
  nextAgentActivity,
  readProgressEvent,
} from "../lib/agentActivity";

export type ChatRunStatus = "streaming" | "stopped" | "done" | "error";

export type QueuedMessage = {
  content: string;
  attachments: ChatAttachment[];
};

export type ChatRun = {
  threadId: string;
  status: ChatRunStatus;
  /** Trascritto vivo: base della sessione + turno in corso. */
  messages: ChatMessage[];
  /** Messaggi scritti mentre l'agente lavorava, non ancora inviati. */
  queued: QueuedMessage[];
  error: string | null;
  startedAtMs: number;
  /** Ultimo turno inviato, per il retry. */
  lastPrompt: string;
  lastAttachments: ChatAttachment[];
};

/** Come si parla col backend. Iniettato, cosi' i test non toccano la rete. */
export type RunTransport = (
  threadId: string,
  input: { message: string; attachments: ChatAttachment[] },
  signal: AbortSignal,
) => Promise<Response>;

export type StartRunInput = {
  threadId: string;
  /** Messaggi gia' consolidati della sessione. */
  base: ChatMessage[];
  content: string;
  attachments: ChatAttachment[];
  transport: RunTransport;
  commit: (threadId: string, messages: ChatMessage[]) => Promise<void>;
  onSettled?: (threadId: string) => void;
};

const runs = new Map<string, ChatRun>();
const controllers = new Map<string, AbortController>();
const listeners = new Set<() => void>();
let version = 0;

function emit(): void {
  version += 1;
  for (const listener of listeners) listener();
}

/** Cambia a ogni scrittura: e' lo snapshot stabile che vuole React. */
export function getRunsVersion(): number {
  return version;
}

function write(threadId: string, patch: Partial<ChatRun>): void {
  const current = runs.get(threadId);
  if (!current) return;
  runs.set(threadId, { ...current, ...patch });
  emit();
}

export function subscribeToRuns(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function getRun(threadId: string | null | undefined): ChatRun | null {
  if (!threadId) return null;
  return runs.get(threadId) ?? null;
}

/** Un turno e' in corso su questo thread. */
export function isRunning(threadId: string | null | undefined): boolean {
  const run = getRun(threadId);
  return run?.status === "streaming";
}

/** Toglie dallo store un turno finito, una volta consolidato nella sessione. */
export function clearRun(threadId: string): void {
  runs.delete(threadId);
  controllers.delete(threadId);
  emit();
}

/** Annulla la richiesta in corso; il testo gia' arrivato resta. */
export function stopRun(threadId: string): void {
  controllers.get(threadId)?.abort();
}

/** Accoda un messaggio scritto mentre l'agente sta ancora lavorando. */
export function enqueueMessage(
  threadId: string,
  content: string,
  attachments: ChatAttachment[] = [],
): void {
  const run = runs.get(threadId);
  if (!run) return;
  write(threadId, { queued: [...run.queued, { content, attachments }] });
}

/** Toglie dalla coda un messaggio non ancora partito. */
export function dropQueuedMessage(threadId: string, index: number): void {
  const run = runs.get(threadId);
  if (!run) return;
  write(threadId, { queued: run.queued.filter((_, i) => i !== index) });
}

function pendingAssistant(): ChatMessage {
  return { role: "assistant", content: "", activity: [] };
}

/**
 * Avvia un turno e lo porta a termine, anche se chi l'ha avviato se ne va.
 *
 * @returns Una promessa che si chiude quando il turno (e la sua coda) e' finito.
 */
export async function startRun(input: StartRunInput): Promise<void> {
  const { threadId, transport, commit, onSettled } = input;

  const controller = new AbortController();
  controllers.set(threadId, controller);

  const previous = runs.get(threadId);
  const userMessage: ChatMessage = { role: "user", content: input.content };
  let messages: ChatMessage[] = [...input.base, userMessage, pendingAssistant()];

  runs.set(threadId, {
    threadId,
    status: "streaming",
    messages,
    queued: previous?.queued ?? [],
    error: null,
    startedAtMs: Date.now(),
    lastPrompt: input.content,
    lastAttachments: input.attachments,
  });
  emit();

  const update = (updater: (current: ChatMessage[]) => ChatMessage[]) => {
    messages = updater(messages);
    write(threadId, { messages });
  };

  const patchAssistant = (patch: Partial<ChatMessage>) => {
    update((current) => {
      const next = [...current];
      const last = next[next.length - 1];
      if (!last || last.role !== "assistant") return current;
      next[next.length - 1] = { ...last, ...patch };
      return next;
    });
  };

  let answer = "";
  let stoppedByUser = false;

  const finishStopped = async () => {
    // Interruzione voluta: la risposta parziale e' comunque lavoro fatto, e
    // buttarla via renderebbe il tasto Stop una punizione.
    stoppedByUser = true;
    update((current) => {
      const next = [...current];
      const last = next[next.length - 1];
      if (last && last.role === "assistant") {
        next[next.length - 1] = {
          ...last,
          content: answer,
          stoppedByUser: true,
          activity: completeAgentActivity(last.activity),
        };
      }
      return next;
    });
    if (answer.trim()) {
      await commit(threadId, messages);
    }
    write(threadId, { status: "stopped" });
  };

  try {
    const response = await transport(
      threadId,
      { message: input.content, attachments: input.attachments },
      controller.signal,
    );
    if (!response.body) throw new Error("Streaming non disponibile");

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    // `fetch` interrompe da solo la lettura quando il segnale scatta, ma non
    // tutti i trasporti lo fanno: chiudere il reader qui rende Stop immediato
    // in ogni caso, invece di lasciare la lettura appesa.
    const cancelReader = () => void reader.cancel().catch(() => {});
    controller.signal.addEventListener("abort", cancelReader);

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (!line.trim()) continue;

        let event: Record<string, unknown>;
        try {
          event = JSON.parse(line);
        } catch {
          // Una riga troncata non deve buttare via il turno.
          continue;
        }

        if (event.type === "activity") {
          const progress = readProgressEvent(event);
          if (progress) {
            update((current) => {
              const next = [...current];
              const last = next[next.length - 1];
              if (!last || last.role !== "assistant") return current;
              next[next.length - 1] = {
                ...last,
                activity: nextAgentActivity(last.activity, progress),
              };
              return next;
            });
          }
        }

        if (event.type === "delta") {
          answer += String(event.content ?? "");
          patchAssistant({ content: answer });
        }

        if (event.type === "done") {
          answer = String(event.message ?? answer);
          patchAssistant({ content: answer });
        }

        if (event.type === "error") {
          const error = event.error as { detail?: string; message?: string } | undefined;
          throw new Error(
            error?.detail ||
              error?.message ||
              String(event.detail ?? "") ||
              "Errore backend",
          );
        }
      }
    }

    controller.signal.removeEventListener("abort", cancelReader);

    if (controller.signal.aborted) {
      await finishStopped();
    } else {
      update((current) => {
        const next = [...current];
        const last = next[next.length - 1];
        if (last && last.role === "assistant") {
          next[next.length - 1] = {
            ...last,
            content: answer,
            activity: completeAgentActivity(last.activity),
          };
        }
        return next;
      });

      await commit(threadId, messages);
      write(threadId, { status: "done" });
      onSettled?.(threadId);
    }
  } catch (error) {
    if (controller.signal.aborted) {
      await finishStopped();
    } else {
      const detail = httpErrorMessage(error, "Errore sconosciuto");
      update((current) => {
        const trimmed =
          current.at(-1)?.role === "assistant" && !current.at(-1)?.content?.trim()
            ? current.slice(0, -1)
            : current;
        return [
          ...trimmed,
          {
            role: "error",
            content: `Non sono riuscito a completare questa richiesta. ${detail}`,
          },
        ];
      });
      write(threadId, {
        status: "error",
        error: `Backend non raggiungibile o richiesta fallita: ${detail}`,
      });
    }
  } finally {
    controllers.delete(threadId);
  }

  const settled = runs.get(threadId);
  if (settled?.status !== "done" || stoppedByUser) {
    // La coda esiste per aggiungere contesto, non per insistere dopo un errore:
    // se il turno e' fallito o e' stato fermato, i messaggi in coda restano
    // visibili e partono solo quando il consulente lo decide.
    return;
  }

  const [next, ...rest] = settled.queued;
  if (next) {
    write(threadId, { queued: rest });
    await startRun({
      ...input,
      base: messages,
      content: next.content,
      attachments: next.attachments,
    });
  }

  // Il turno finito resta nello store finche' dura la sessione del browser: e'
  // l'unico posto dove sopravvive la traccia di lavoro (il backend salva la
  // risposta, non le fasi), e sparire appena arriva l'ultima parola e' proprio
  // cio' che rendeva il progresso inutile da leggere.
}

/** Svuota tutto. Solo per i test. */
export function resetRunsForTests(): void {
  runs.clear();
  controllers.clear();
  listeners.clear();
}
