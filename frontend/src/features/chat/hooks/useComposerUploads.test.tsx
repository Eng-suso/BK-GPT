import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mutateAsync = vi.fn();
const discardSource = vi.fn((_id: string) => Promise.resolve());

vi.mock("../../projects/api", () => ({
  discardSource: (id: string) => discardSource(id),
  useProjectSourcesQuery: () => ({
    data: [{ id: "src-nuova", acquisitionStatus: "pending" }],
  }),
  useUploadProjectSourceMutation: () => ({ mutateAsync }),
}));

import { useComposerUploads } from "./useComposerUploads";

const PROCESS_SCOPE = {
  type: "process" as const,
  projectId: "p-1",
  processId: "proc-1",
  processName: "Acquisti",
};

function file(name: string) {
  return new File(["contenuto"], name, { type: "application/octet-stream" });
}

beforeEach(() => {
  mutateAsync.mockReset();
  discardSource.mockClear();
});

describe("useComposerUploads", () => {
  it("in una chat di processo carica come evidenza del processo e restituisce l'allegato", async () => {
    mutateAsync.mockResolvedValue({ id: "src-nuova", name: "ordini.xlsx", projectId: "p-1", created: true });
    const { result } = renderHook(() => useComposerUploads(PROCESS_SCOPE, true));

    let attachment = null;
    await act(async () => {
      attachment = await result.current.uploadFile(file("ordini.xlsx"));
    });

    expect(mutateAsync).toHaveBeenCalledWith({
      file: expect.any(File),
      roles: ["process_evidence"],
      retention: "persistent",
      scopes: [{ type: "process", id: "proc-1" }],
    });
    expect(attachment).toEqual({ kind: "source", id: "src-nuova", label: "ordini.xlsx", projectId: "p-1" });
    expect(result.current.statusOf("src-nuova")).toBe("pending");
  });

  it("togliere la card scarta solo un file creato qui, e mai dopo l'invio", async () => {
    mutateAsync
      .mockResolvedValueOnce({ id: "src-nuova", name: "a.pdf", projectId: "p-1", created: true })
      .mockResolvedValueOnce({ id: "src-esistente", name: "b.pdf", projectId: "p-1", created: false })
      .mockResolvedValueOnce({ id: "src-inviata", name: "c.pdf", projectId: "p-1", created: true });
    const { result } = renderHook(() => useComposerUploads(PROCESS_SCOPE, true));

    await act(async () => {
      await result.current.uploadFile(file("a.pdf"));
      await result.current.uploadFile(file("b.pdf"));
    });
    act(() => {
      result.current.forget({ kind: "source", id: "src-nuova", label: "a.pdf", projectId: "p-1" });
      result.current.forget({ kind: "source", id: "src-esistente", label: "b.pdf", projectId: "p-1" });
    });
    expect(discardSource).toHaveBeenCalledTimes(1);
    expect(discardSource).toHaveBeenCalledWith("src-nuova");

    await act(async () => {
      await result.current.uploadFile(file("c.pdf"));
    });
    act(() => {
      result.current.keepAll();
      result.current.forget({ kind: "source", id: "src-inviata", label: "c.pdf", projectId: "p-1" });
    });
    expect(discardSource).toHaveBeenCalledTimes(1);
  });

  it("un caricamento rifiutato resta a vista con il motivo", async () => {
    mutateAsync.mockRejectedValue(new Error("Il PDF è protetto da password."));
    const { result } = renderHook(() => useComposerUploads(PROCESS_SCOPE, false));

    await act(async () => {
      await result.current.uploadFile(file("cifrato.pdf"));
    });

    expect(result.current.inFlight).toHaveLength(1);
    expect(result.current.inFlight[0].error).toBeTruthy();
  });

  it("la chat del consulente non carica: non sa in quale progetto", () => {
    const { result } = renderHook(() => useComposerUploads({ type: "consultant" }, false));
    expect(result.current.canUpload).toBe(false);
  });
});
