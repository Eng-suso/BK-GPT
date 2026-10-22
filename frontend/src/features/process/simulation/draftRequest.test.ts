import { writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import cases from "../../../../../tests/fixtures/simulation/draft_request_cases.json";
import { runRequestBody } from "./simulationApi";
import { parseScenarioDraft, scenarioToInput, seedDraftFromTemplate } from "./simulationScenario";
import type { ScenarioTemplate } from "./simulationTypes";

/**
 * La richiesta che il pannello invia per una bozza salvata nel workspace. Il
 * server rifa' la stessa traduzione (backend/simulation/draft_request.py) per
 * verificare il run: i casi del file valgono per entrambe. Cambiando la
 * traduzione qui, si rigenera `expected` con `UPDATE_DRAFT_REQUEST_CASES=1` e
 * il test Python dice se il backend la segue.
 */
// Si rigenera da `frontend/`, come girano i test.
const FIXTURE = resolve(process.cwd(), "../tests/fixtures/simulation/draft_request_cases.json");

type DraftRequestCase = { name: string; scenarioName: string; template: unknown; draft: unknown; expected?: unknown };

function bodyFor(c: DraftRequestCase) {
  const draft = seedDraftFromTemplate(parseScenarioDraft(structuredClone(c.draft)), c.template as ScenarioTemplate);
  const body = runRequestBody({ ...scenarioToInput({ ...draft, scenarioName: c.scenarioName }, null), idempotencyKey: "" });
  // Fuori cio' che non viene dalla bozza: BPMN, chiave, seed e scenario li aggiunge chi invia.
  const fromDraft: Record<string, unknown> = { ...body };
  for (const key of ["current_bpmn_xml", "idempotency_key", "seed", "workspace_scenario"]) delete fromDraft[key];
  return JSON.parse(JSON.stringify(fromDraft));
}

const all = cases as DraftRequestCase[];

if (process.env.UPDATE_DRAFT_REQUEST_CASES) {
  writeFileSync(FIXTURE, `${JSON.stringify(all.map((c) => ({ ...c, expected: bodyFor(c) })), null, 2)}\n`);
}

describe("la richiesta di una bozza del workspace: gli stessi casi del backend", () => {
  it.each(all.map((c) => [c.name, c] as const))("%s", (_name, c) => {
    expect(c.expected).toBeDefined();
    expect(bodyFor(c)).toEqual(c.expected);
  });
});
