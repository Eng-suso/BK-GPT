import { afterEach, describe, expect, it, vi } from "vitest";

import { HttpError, http, httpErrorMessage, httpStream } from "./http";

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
    ...init,
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("http", () => {
  it("returns the parsed JSON body on success", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(jsonResponse({ ok: true }));

    await expect(http("/thing")).resolves.toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("throws HttpError carrying status and parsed body on a non-2xx response", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ detail: "nope" }, { status: 422, statusText: "Unprocessable" }),
    );

    const error = await http("/thing").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(HttpError);
    expect((error as HttpError).status).toBe(422);
    expect((error as HttpError).body).toEqual({ detail: "nope" });
  });

  it("sends a JSON body with a Content-Type header", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(null, { status: 204 }));

    await http("/thing", { method: "POST", body: { a: 1 } });

    const [, init] = fetchMock.mock.calls[0];
    expect(init?.body).toBe(JSON.stringify({ a: 1 }));
    expect(new Headers(init?.headers).get("Content-Type")).toBe(
      "application/json",
    );
  });

  it("passes FormData through untouched, without forcing a JSON Content-Type", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(jsonResponse({ text: "hi" }));
    const form = new FormData();
    form.append("file", new Blob(["x"]), "a.wav");

    await http("/audio", { method: "POST", body: form });

    const [, init] = fetchMock.mock.calls[0];
    expect(init?.body).toBeInstanceOf(FormData);
    expect(new Headers(init?.headers).has("Content-Type")).toBe(false);
  });

  it("adds the admin token header when asked", async () => {
    (window as unknown as { DELIR_ADMIN_TOKEN?: string }).DELIR_ADMIN_TOKEN =
      "secret-admin";
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(null, { status: 204 }));

    await http("/thing", { method: "DELETE", admin: true });

    const [, init] = fetchMock.mock.calls[0];
    expect(new Headers(init?.headers).get("X-DeliR-Admin-Token")).toBe(
      "secret-admin",
    );
    delete (window as unknown as { DELIR_ADMIN_TOKEN?: string })
      .DELIR_ADMIN_TOKEN;
  });
});

describe("httpStream", () => {
  it("resolves with the raw Response so the caller can read the body", async () => {
    const streamed = new Response("a\nb\n", { status: 200 });
    vi.spyOn(globalThis, "fetch").mockResolvedValue(streamed);

    const res = await httpStream("/stream", { method: "POST", body: {} });
    expect(res).toBe(streamed);
    expect(res.body).not.toBeNull();
  });

  it("throws HttpError on a non-2xx response", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ detail: "boom" }, { status: 500, statusText: "err" }),
    );

    await expect(httpStream("/stream")).rejects.toBeInstanceOf(HttpError);
  });
});

describe("httpErrorMessage", () => {
  it("prefers the backend `detail` field", () => {
    const err = new HttpError(400, "400 Bad Request", { detail: "too long" });
    expect(httpErrorMessage(err, "fallback")).toBe("too long");
  });

  it("falls back to the error message, then the provided default", () => {
    expect(httpErrorMessage(new HttpError(500, "500 err", {}), "fallback")).toBe(
      "500 err",
    );
    expect(httpErrorMessage("not an error", "fallback")).toBe("fallback");
  });
});
