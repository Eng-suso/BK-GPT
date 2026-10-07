import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const http = vi.fn();

vi.mock("@/lib/http", async () => {
  const actual = await vi.importActual<typeof import("@/lib/http")>("@/lib/http");
  return { ...actual, http: (path: string, options?: unknown) => http(path, options) };
});

const { projectKeys, useUploadClientSourceMutation } = await import("./api");

const UPLOADED = {
  created: true,
  suggested_roles: ["policy"],
  id: "src-policy",
  project_id: null,
  client_id: "esaote",
  process_id: null,
  name: "policy-acquisti.pdf",
  type: "File",
  meta: "In lettura: testo ed evidenze arrivano tra poco.",
  roles: ["policy"],
  retention: "persistent",
  scopes: [{ type: "client", id: "esaote" }],
  status: "extracted",
  byte_size: 18,
  content_hash: "hash",
  mime_type: "application/pdf",
  acquisition_status: "pending",
  acquisition_error: null,
};

describe("useUploadClientSourceMutation", () => {
  it("carica per il cliente e rilegge le Fonti di ogni progetto in cache, non il resto", async () => {
    http.mockResolvedValue(UPLOADED);
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const cached = [
      projectKeys.sources("acquisti"),
      projectKeys.sources("tesoreria"),
      projectKeys.detail("acquisti"),
    ];
    for (const key of cached) {
      queryClient.setQueryData(key, []);
    }
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useUploadClientSourceMutation("esaote"), { wrapper });

    let uploaded: Awaited<ReturnType<typeof result.current.mutateAsync>> | undefined;
    await act(async () => {
      uploaded = await result.current.mutateAsync({
        file: new File(["policy"], "policy-acquisti.pdf", { type: "application/pdf" }),
        roles: ["policy"],
        retention: "persistent",
      });
    });

    const [path, options] = http.mock.calls[0] as [string, { method: string; body: FormData }];
    expect(path).toBe("/v1/workspace/clients/esaote/sources/upload");
    expect(options.method).toBe("POST");
    expect(options.body.get("scopes")).toBe("[]");
    expect(uploaded).toMatchObject({ id: "src-policy", projectId: null, clientId: "esaote", created: true });
    expect(queryClient.getQueryState(projectKeys.sources("acquisti"))?.isInvalidated).toBe(true);
    expect(queryClient.getQueryState(projectKeys.sources("tesoreria"))?.isInvalidated).toBe(true);
    expect(queryClient.getQueryState(projectKeys.detail("acquisti"))?.isInvalidated).toBe(false);
  });
});
