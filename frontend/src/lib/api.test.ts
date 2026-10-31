import { describe, expect, it } from "vitest";

import { resolveApiBase } from "./api";

function at(url: string) {
  const { protocol, hostname, port } = new URL(url);
  return { protocol, hostname, port };
}

describe("resolveApiBase", () => {
  it("su un dominio vero chiama lo stesso dominio, non il computer di chi apre la pagina", () => {
    expect(resolveApiBase(at("https://app.delir.it/projects"))).toBe("");
  });

  it("su un dominio vero con porta resta sullo stesso dominio", () => {
    expect(resolveApiBase(at("http://pilota.example.com:8080/"))).toBe("");
  });

  it("servito dal backend locale sulla 8000 resta sullo stesso dominio", () => {
    expect(resolveApiBase(at("http://127.0.0.1:8000/"))).toBe("");
    expect(resolveApiBase(at("http://localhost:8000/"))).toBe("");
  });

  it("con Vite in sviluppo chiama il backend locale sulla 8000", () => {
    expect(resolveApiBase(at("http://127.0.0.1:3030/projects"))).toBe("http://127.0.0.1:8000");
    expect(resolveApiBase(at("http://localhost:3030/"))).toBe("http://127.0.0.1:8000");
  });

  it("aperto da file chiama il backend locale sulla 8000", () => {
    expect(resolveApiBase({ protocol: "file:", hostname: "", port: "" })).toBe("http://127.0.0.1:8000");
  });

  it("un indirizzo configurato vince sempre", () => {
    expect(resolveApiBase(at("https://app.delir.it/"), "https://api.delir.it")).toBe("https://api.delir.it");
    expect(resolveApiBase(at("http://127.0.0.1:3030/"), "http://127.0.0.1:9999")).toBe("http://127.0.0.1:9999");
  });
});
