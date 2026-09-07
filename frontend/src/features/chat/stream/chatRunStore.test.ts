import { afterEach, describe, expect, it, vi } from "vitest";

import {
  enqueueMessage,
  getRun,
  isRunning,
  resetRunsForTests,
  startRun,
  stopRun,
  subscribeToRuns,
  type RunTransport,
} from "./chatRunStore";
import type { ChatMessage } from "../types";

/** Uno stream NDJSON che rilascia le righe una alla volta, su richiesta. */
function controllableStream() {
  let push!: (line: string) => void;
  let close!: () => void;
  let fail!: (error: Error) => void;

  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      const encoder = new TextEncoder();
      push = (line: string) => controller.enqueue(encoder.encode(`${line}\n`));
      close = () => controller.close();
      fail = (error: Error) => controller.error(error);
    },
  });

  return { stream, push, close, fail };
}

function ndjson(event: Record<string, unknown>): string {
  return JSON.stringify(event);
}

afterEach(() => {
  resetRunsForTests();
});

describe("il turno vive fuori dal componente", () => {
  it("arriva in fondo e consolida il trascritto anche se nessuno lo osserva", async () => {
    const pipe = controllableStream();
    const transport: RunTransport = () =>
      Promise.resolve(new Response(pipe.stream));
    const commit = vi.fn(async () => {});

    const run = startRun({
      threadId: "t-1",
      base: [],
      content: "Cosa sappiamo di Esaote?",
      attachments: [],
      transport,
      commit,
    });

    await vi.waitFor(() => expect(isRunning("t-1")).toBe(true));

    pipe.push(
      ndjson({
        type: "activity",
        message: "Cerco nella memoria di lavoro",
        payload: { phase: "recalling", label: "Cerco nella memoria di lavoro" },
      }),
    );
    pipe.push(ndjson({ type: "delta", content: "Esaote " }));
    pipe.push(ndjson({ type: "delta", content: "ha tre processi." }));
    pipe.push(ndjson({ type: "done", message: "Esaote ha tre processi." }));
    pipe.close();

    await run;

    expect(commit).toHaveBeenCalledTimes(1);
    const [threadId, messages] = commit.mock.calls[0] as unknown as [string, ChatMessage[]];
    expect(threadId).toBe("t-1");
    expect(messages.at(-1)).toMatchObject({
      role: "assistant",
      content: "Esaote ha tre processi.",
    });
    expect(messages.at(-1)?.activity?.[0]).toMatchObject({
      phase: "recalling",
      status: "completed",
    });
    // La traccia di lavoro resta leggibile a turno finito.
    expect(getRun("t-1")?.status).toBe("done");
    expect(getRun("t-1")?.messages.at(-1)?.activity).toHaveLength(1);
  });

  it("notifica gli iscritti a ogni scrittura", async () => {
    const pipe = controllableStream();
    const listener = vi.fn();
    subscribeToRuns(listener);

    const run = startRun({
      threadId: "t-notify",
      base: [],
      content: "ciao",
      attachments: [],
      transport: () => Promise.resolve(new Response(pipe.stream)),
      commit: async () => {},
    });

    await vi.waitFor(() => expect(listener).toHaveBeenCalled());
    pipe.push(ndjson({ type: "delta", content: "ok" }));
    pipe.close();
    await run;
  });
});

describe("fermare il turno", () => {
  it("tiene la risposta parziale invece di buttarla", async () => {
    const pipe = controllableStream();
    const commit = vi.fn(async () => {});

    const run = startRun({
      threadId: "t-stop",
      base: [],
      content: "Scrivi il brief",
      attachments: [],
      transport: () => Promise.resolve(new Response(pipe.stream)),
      commit,
    });

    await vi.waitFor(() => expect(isRunning("t-stop")).toBe(true));
    pipe.push(ndjson({ type: "delta", content: "Prima parte" }));
    await vi.waitFor(() =>
      expect(getRun("t-stop")?.messages.at(-1)?.content).toBe("Prima parte"),
    );

    stopRun("t-stop");
    await run;

    const stopped = getRun("t-stop");
    expect(stopped?.status).toBe("stopped");
    expect(stopped?.messages.at(-1)).toMatchObject({
      role: "assistant",
      content: "Prima parte",
      stoppedByUser: true,
    });
    expect(commit).toHaveBeenCalledTimes(1);
  });
});

describe("la coda dei messaggi", () => {
  it("manda in coda quello che si scrive durante il turno, e lo invia dopo", async () => {
    const first = controllableStream();
    const second = controllableStream();
    const streams = [first, second];
    const sent: string[] = [];

    const transport: RunTransport = (_threadId, input) => {
      sent.push(input.message);
      const pipe = streams[sent.length - 1];
      return Promise.resolve(new Response(pipe.stream));
    };

    const run = startRun({
      threadId: "t-queue",
      base: [],
      content: "Prima domanda",
      attachments: [],
      transport,
      commit: async () => {},
    });

    await vi.waitFor(() => expect(isRunning("t-queue")).toBe(true));
    enqueueMessage("t-queue", "Aggiungo un dettaglio");
    expect(getRun("t-queue")?.queued).toHaveLength(1);

    first.push(ndjson({ type: "delta", content: "Risposta uno" }));
    first.close();

    await vi.waitFor(() => expect(sent).toHaveLength(2));
    second.push(ndjson({ type: "delta", content: "Risposta due" }));
    second.close();
    await run;

    expect(sent).toEqual(["Prima domanda", "Aggiungo un dettaglio"]);
  });

  it("non svuota la coda se il turno e' fallito", async () => {
    const pipe = controllableStream();
    const sent: string[] = [];

    const run = startRun({
      threadId: "t-queue-error",
      base: [],
      content: "Prima domanda",
      attachments: [],
      transport: (_threadId, input) => {
        sent.push(input.message);
        return Promise.resolve(new Response(pipe.stream));
      },
      commit: async () => {},
    });

    await vi.waitFor(() => expect(isRunning("t-queue-error")).toBe(true));
    enqueueMessage("t-queue-error", "Aggiungo un dettaglio");
    pipe.fail(new Error("connessione caduta"));
    await run;

    expect(sent).toEqual(["Prima domanda"]);
    expect(getRun("t-queue-error")?.queued).toHaveLength(1);
    expect(getRun("t-queue-error")?.status).toBe("error");
  });
});

describe("errori", () => {
  it("mostra l'errore al posto della bolla vuota", async () => {
    const run = startRun({
      threadId: "t-error",
      base: [],
      content: "ciao",
      attachments: [],
      transport: () => Promise.reject(new Error("backend spento")),
      commit: async () => {},
    });

    await run;

    const failed = getRun("t-error");
    expect(failed?.status).toBe("error");
    expect(failed?.messages.at(-1)?.role).toBe("error");
    expect(failed?.error).toContain("backend spento");
  });

  it("non butta il turno per una riga NDJSON troncata", async () => {
    const pipe = controllableStream();
    const commit = vi.fn(async () => {});

    const run = startRun({
      threadId: "t-partial",
      base: [],
      content: "ciao",
      attachments: [],
      transport: () => Promise.resolve(new Response(pipe.stream)),
      commit,
    });

    await vi.waitFor(() => expect(isRunning("t-partial")).toBe(true));
    pipe.push('{"type": "delta", "conte');
    pipe.push(ndjson({ type: "delta", content: "va bene" }));
    pipe.close();
    await run;

    const [, messages] = commit.mock.calls[0] as unknown as [string, ChatMessage[]];
    expect(messages.at(-1)?.content).toBe("va bene");
  });
});
