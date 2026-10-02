import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mutateAsync = vi.fn();
const discardSource = vi.fn((_id: string) => Promise.resolve());

vi.mock("../../projects/api", () => ({
  discardSource: (id: string) => discardSource(id),
  useProjectSourcesQuery: () => ({
    data: [
      { id: "src-nuova", acquisitionStatus: "pending", acquisitionError: null },
      { id: "src-rotta", acquisitionStatus: "failed", acquisitionError: "Il PDF è protetto da password." },
    ],
  }),
  useUploadProjectSourceMutation: () => ({ mutateAsync }),
}));

import { useComposerUploads, type UploadDestination } from "./useComposerUploads";

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

  it("se lo scarto non riesce per un guasto la card torna, se la fonte e' confermata no", async () => {
    const { HttpError } = await import("@/lib/http");
    mutateAsync
      .mockResolvedValueOnce({ id: "src-rete", name: "a.pdf", projectId: "p-1", created: true })
      .mockResolvedValueOnce({ id: "src-confermata", name: "b.pdf", projectId: "p-1", created: true });
    const { result } = renderHook(() => useComposerUploads(PROCESS_SCOPE, true));
    await act(async () => {
      await result.current.uploadFile(file("a.pdf"));
      await result.current.uploadFile(file("b.pdf"));
    });

    const restoreNetwork = vi.fn();
    const restoreConfirmed = vi.fn();
    discardSource.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    discardSource.mockRejectedValueOnce(new HttpError(409, "gia' confermata"));
    await act(async () => {
      result.current.forget({ kind: "source", id: "src-rete", label: "a.pdf", projectId: "p-1" }, restoreNetwork);
      result.current.forget(
        { kind: "source", id: "src-confermata", label: "b.pdf", projectId: "p-1" },
        restoreConfirmed,
      );
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(restoreNetwork).toHaveBeenCalledOnce();
    expect(restoreConfirmed).not.toHaveBeenCalled();
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

  it("una lettura fallita porta il suo motivo, una in corso no", () => {
    const { result } = renderHook(() => useComposerUploads(PROCESS_SCOPE, true));
    expect(result.current.failureOf("src-rotta")).toBe("Il PDF è protetto da password.");
    expect(result.current.failureOf("src-nuova")).toBeNull();
  });

  it("la chat del consulente carica solo dopo aver scelto dove", async () => {
    const { result, rerender } = renderHook(
      ({ chosen }: { chosen: UploadDestination | null }) =>
        useComposerUploads({ type: "consultant" }, false, chosen),
      { initialProps: { chosen: null as UploadDestination | null } },
    );
    expect(result.current.needsDestination).toBe(true);
    expect(result.current.canUpload).toBe(false);

    rerender({ chosen: { projectId: "p-9", processId: "proc-9" } });
    expect(result.current.canUpload).toBe(true);
    mutateAsync.mockResolvedValue({ id: "src-c", name: "nota.md", projectId: "p-9", created: true });
    await act(async () => {
      await result.current.uploadFile(file("nota.md"));
    });
    // messo in un processo: evidenza di quel processo
    expect(mutateAsync).toHaveBeenCalledWith(
      expect.objectContaining({ roles: ["process_evidence"], scopes: [{ type: "process", id: "proc-9" }] }),
    );

    rerender({ chosen: { projectId: "p-9" } });
    await act(async () => {
      await result.current.uploadFile(file("contesto.md"));
    });
    // messo nel progetto: contesto
    expect(mutateAsync).toHaveBeenLastCalledWith(
      expect.objectContaining({ roles: ["context"], scopes: [{ type: "project", id: "p-9" }] }),
    );
  });
});
