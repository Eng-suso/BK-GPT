import type { Page, Route } from "@playwright/test";

import { API, unhandled } from "./mockApi";
import { IDS, demoCase, type Lang } from "./vetrano";

/**
 * Il mock delle API per i nuovi video (caso `vetrano.ts`), in italiano o in
 * inglese. Copre le schermate che le scene mostrano; una richiesta scoperta
 * finisce in `unhandled` e lo spec la stampa, cosi' un buco si vede.
 */
export async function installCaseApi(page: Page, lang: Lang): Promise<void> {
  const data = demoCase(lang);
  await page.addInitScript(
    ({ base, lng }) => {
      Object.assign(window, { DELIR_API_BASE: base });
      window.localStorage.setItem("delir-language", lng);
    },
    { base: API, lng: lang },
  );

  await page.route(`${API}/**`, async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();
    const json = (body: unknown, headers?: Record<string, string>) => route.fulfill({ json: body, headers });
    const W = "/v1/workspace";

    if (path === "/v1/auth/me") {
      // L'etichetta in alto a destra e' lo spazio di lavoro del consulente.
      return json({ tenant_id: "Studio Bellini", auth_mode: "local", auth_enabled: false, is_admin: false, caller_id: "marco-bellini", has_user_identity: false });
    }
    if (path === `${W}/notifications`) return json([]);
    if (path === `${W}/projects` && method === "GET") return json(data.projects, { "X-DeliR-Total": String(data.projects.length) });
    if (path === `${W}/clients` && method === "GET") return json(data.clients, { "X-DeliR-Total": String(data.clients.length) });
    if (path === `${W}/clients/${IDS.client}`) return json(data.clients[0]);
    if (path === `${W}/clients/${IDS.client}/sources`) return json([]);
    if (path === `${W}/projects/${IDS.project}`) return json(data.project);
    if (path === `${W}/projects/${IDS.project}/sources`) return json(data.sources);
    if (path === `${W}/projects/${IDS.project}/processes`) return json(data.project.process_items);
    if (path === `${W}/projects/${IDS.project}/decisions`) return json([]);
    if (path === `${W}/processes/${IDS.process}`) return json(data.processItem);
    const sourceMatch = path.match(/^\/v1\/workspace\/sources\/([^/]+)(?:\/(claims|relations|document))?$/);
    if (sourceMatch) {
      const [, sourceId, part] = sourceMatch;
      if (part === "document") return json(data.sourceDocument(sourceId));
      if (part) return json([]);
      return json(data.sources.find((source) => source.id === sourceId) ?? null);
    }

    const M = `${W}/bpmn-models/${IDS.model}`;
    if (path === M && method === "GET") return json({ id: IDS.model, process_id: IDS.process, name: "As-Is v3", xml: data.bpmnXml, version_id: 3 });
    if (path === `${M}/versions`) return json(data.versions.map((version) => ({ ...version, xml: data.bpmnXml })));
    if (path === `${M}/review` && method === "GET") return json(data.review);
    if (path === `${M}/review/versions`) return json([]);
    if (path === `${W}/processes/${IDS.process}/provenance`) return json(data.provenance);
    if (path === `${W}/processes/${IDS.process}/conformance`) return json(data.conformance);
    if (path === `${M}/simulation-template`) return json(data.api.simulation_template);
    if (path === `${M}/simulation-compatibility`) return json(data.api.simulation_compatibility);
    if (path === `${M}/simulation-runs` && method === "GET") return json(data.simulationRuns);
    const runMatch = path.match(/^\/v1\/workspace\/simulation-runs\/(\d+)(?:\/(replay|experiments|model))?$/);
    if (runMatch) {
      const id = Number(runMatch[1]);
      const run = data.runData(id);
      if (!run) return route.fulfill({ status: 404, json: { detail: "not found" } });
      if (runMatch[2] === "replay") return json({ run_id: id, schema_version: 1, replay: run.replay });
      if (runMatch[2] === "experiments") return json(run.experiments);
      if (runMatch[2] === "model") return json({ run_id: id, model: run.model });
      return json(data.runById(id));
    }

    // La discussione del processo: una sessione vuota, la chat non e' in scena.
    if (path === "/v1/consultant-chat/sessions" && method === "GET") return json([]);

    unhandled.add(`${method} ${path}`);
    return route.fulfill({ status: 200, json: [] });
  });
}
