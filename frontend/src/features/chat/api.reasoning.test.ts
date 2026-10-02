import { describe, expect, it, vi } from "vitest";

// Il confine e' la richiesta HTTP: e' li' che l'impegno di ragionamento smetteva
// di esistere. Il selettore cambiava uno stato che nessuno inviava, e il
// consulente che sceglieva "Profondo" riceveva comunque la risposta rapida.
const httpStream = vi.fn<(path: string, init: { body?: unknown }) => Promise<Response>>();

vi.mock("@/lib/http", () => ({
  http: vi.fn(),
  httpStream: (path: string, init: { body?: unknown }) => httpStream(path, init),
}));

const { streamChatMessage } = await import("./api");

function bodyOf(): Record<string, unknown> {
  const [, init] = httpStream.mock.calls.at(-1) ?? [];
  return (init?.body ?? {}) as Record<string, unknown>;
}

describe("streamChatMessage", () => {
  it("sends the reasoning level the consultant picked", async () => {
    httpStream.mockResolvedValue(new Response());

    await streamChatMessage("thread-1", {
      message: "Analizza le contraddizioni fra le interviste",
      modelName: "gpt-5.6-luna",
      scope: { type: "consultant" },
      choices: { posture: "auto", autonomy: "auto", reasoning: "high" },
    });

    expect(bodyOf().reasoning_effort).toBe("high");
  });

  it("keeps the level out of the thread: it travels with each turn", async () => {
    httpStream.mockResolvedValue(new Response());

    await streamChatMessage("thread-1", {
      message: "E adesso riassumi",
      modelName: "gpt-5.6-luna",
      scope: { type: "consultant" },
      choices: { posture: "auto", autonomy: "auto", reasoning: "low" },
    });

    expect(bodyOf().reasoning_effort).toBe("low");
  });
});
