import { describe, expect, it } from "vitest";

import {
  activityDurationMs,
  completeAgentActivity,
  formatElapsed,
  nextAgentActivity,
  readProgressEvent,
} from "./agentActivity";
import type { AgentActivity } from "../types";

describe("readProgressEvent", () => {
  it("legge fase, etichetta e dettaglio dal payload", () => {
    const progress = readProgressEvent({
      message: "Leggo le fonti raccolte",
      payload: {
        activity_id: "phase-2-reading_sources",
        phase: "reading_sources",
        label: "Leggo le fonti raccolte",
        detail: "Intervista Laura",
        icon: "document",
      },
    });

    expect(progress).toEqual({
      activityId: "phase-2-reading_sources",
      phase: "reading_sources",
      label: "Leggo le fonti raccolte",
      detail: "Intervista Laura",
      icon: "document",
    });
  });

  it("scarta un evento senza etichetta invece di inventarne una", () => {
    expect(readProgressEvent({ payload: { phase: "recalling" } })).toBeNull();
    expect(readProgressEvent({ message: "   " })).toBeNull();
  });

  it("ignora un dettaglio vuoto", () => {
    const progress = readProgressEvent({
      payload: { phase: "recalling", label: "Cerco nella memoria", detail: "  " },
    });

    expect(progress?.detail).toBeUndefined();
  });
});

describe("nextAgentActivity", () => {
  it("chiude il passo in corso e apre quello nuovo", () => {
    const first = nextAgentActivity(
      undefined,
      { phase: "recalling", label: "Cerco nella memoria" },
      1_000,
    );
    const second = nextAgentActivity(
      first,
      { phase: "drafting", label: "Preparo la risposta" },
      4_000,
    );

    expect(second).toHaveLength(2);
    expect(second[0]).toMatchObject({ status: "completed", endedAtMs: 4_000 });
    expect(second[1]).toMatchObject({ status: "running", startedAtMs: 4_000 });
  });

  it("non ripete la stessa fase su righe diverse", () => {
    const timeline = nextAgentActivity(
      undefined,
      { phase: "recalling", label: "Cerco nella memoria" },
      1_000,
    );
    const again = nextAgentActivity(
      timeline,
      { phase: "recalling", label: "Cerco nella memoria" },
      2_000,
    );

    expect(again).toHaveLength(1);
    expect(again[0].startedAtMs).toBe(1_000);
  });

  it("aggiorna il dettaglio della fase in corso senza aggiungere una riga", () => {
    const timeline = nextAgentActivity(
      undefined,
      { phase: "reading_sources", label: "Leggo le fonti", detail: "Intervista Laura" },
      1_000,
    );
    const updated = nextAgentActivity(
      timeline,
      { phase: "reading_sources", label: "Leggo le fonti", detail: "Verbale kickoff" },
      2_000,
    );

    expect(updated).toHaveLength(1);
    expect(updated[0].detail).toBe("Verbale kickoff");
  });

  it("riapre una fase che torna piu' avanti nel turno", () => {
    let timeline = nextAgentActivity(
      undefined,
      { phase: "recalling", label: "Cerco nella memoria" },
      1_000,
    );
    timeline = nextAgentActivity(
      timeline,
      { phase: "reading_sources", label: "Leggo le fonti" },
      2_000,
    );
    timeline = nextAgentActivity(
      timeline,
      { phase: "recalling", label: "Cerco nella memoria" },
      3_000,
    );

    expect(timeline).toHaveLength(3);
    expect(timeline[2].status).toBe("running");
  });
});

describe("completeAgentActivity", () => {
  it("chiude ogni passo ancora aperto", () => {
    const timeline: AgentActivity[] = [
      { key: "a", label: "Cerco", status: "completed", startedAtMs: 0, endedAtMs: 500 },
      { key: "b", label: "Scrivo", status: "running", startedAtMs: 500 },
    ];

    const closed = completeAgentActivity(timeline, 2_000);

    expect(closed?.every((item) => item.status === "completed")).toBe(true);
    expect(closed?.[1].endedAtMs).toBe(2_000);
  });
});

describe("durate", () => {
  it("misura il passo in corso fino a adesso", () => {
    const running: AgentActivity = {
      key: "a",
      label: "Cerco",
      status: "running",
      startedAtMs: 1_000,
    };

    expect(activityDurationMs(running, 13_000)).toBe(12_000);
  });

  it("scrive i tempi come li legge un consulente", () => {
    expect(formatElapsed(900)).toBe("0s");
    expect(formatElapsed(12_400)).toBe("12s");
    expect(formatElapsed(65_000)).toBe("1:05");
  });
});
