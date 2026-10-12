import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

/**
 * La pagina del cliente non deve contenere il codice con le credenziali dello
 * studio. Se un import la collegasse a `lib/security` (che legge il token
 * dell'API) o a `lib/http` (che lo allega a ogni richiesta), chi apre il link
 * potrebbe estrarre il token e leggere tutti i dati dello studio. Questo test
 * segue gli import veri a partire dall'ingresso della pagina.
 */
const SRC = path.resolve(__dirname, "..");
const IMPORT = /(?:^|\n)\s*(?:import|export)\s+(?!type\b)(?:[^'"]*?\sfrom\s+)?["']([^"']+)["']|import\(\s*["']([^"']+)["']\s*\)/g;
const EXTENSIONS = ["", ".ts", ".tsx", "/index.ts", "/index.tsx"];

function resolve(spec: string, from: string): string | null {
  const base = spec.startsWith("@/") ? path.join(SRC, spec.slice(2)) : spec.startsWith(".") ? path.resolve(path.dirname(from), spec) : null;
  if (!base) return null;
  for (const extension of EXTENSIONS) {
    const file = base + extension;
    if (existsSync(file) && /\.(ts|tsx)$/.test(file)) return file;
  }
  return null;
}

function reachable(entry: string): Set<string> {
  const seen = new Set<string>();
  const queue = [path.join(SRC, entry)];
  while (queue.length) {
    const file = queue.pop()!;
    if (seen.has(file)) continue;
    seen.add(file);
    for (const match of readFileSync(file, "utf8").matchAll(IMPORT)) {
      const next = resolve(match[1] ?? match[2], file);
      if (next) queue.push(next);
    }
  }
  return new Set([...seen].map((file) => path.relative(SRC, file).split(path.sep).join("/")));
}

const FORBIDDEN = ["lib/security.ts", "lib/http.ts", "features/process/handover/ownerDashboardApi.ts"];

describe("client share page isolation", () => {
  it("never reaches the code that holds or sends the studio credentials", () => {
    const files = reachable("share/main.tsx");
    expect(files).toContain("features/process/handover/OwnerDashboardView.tsx");
    expect(files).toContain("share/fetchSharedDashboard.ts");
    for (const forbidden of FORBIDDEN) expect(files, forbidden).not.toContain(forbidden);
    expect([...files].filter((file) => file.startsWith("app/"))).toEqual([]);
  });

  it("follows imports for real: the studio app does reach the credentials", () => {
    expect(reachable("main.tsx")).toContain("lib/security.ts");
  });
});
