import type { Page, Route } from "@playwright/test";

import {
  IDS,
  api,
  bpmnXml,
  chatMessages,
  chatSession,
  claimsOf,
  clients,
  conformance,
  impactReview,
  project,
  projects,
  provenance,
  relationsOf,
  review,
  runById,
  simulationLayout,
  simulationLayoutKey,
  runData,
  simulationRuns,
  sourceDocument,
  sources,
  versions,
} from "./demo";

export const API = "http://127.0.0.1:8000";

/** Richieste che il caso non copre: lo spec le stampa, cosi' un buco si vede. */
export const unhandled = new Set<string>();

export async function installDemoApi(page: Page, language: "it" | "en" = "it"): Promise<void> {
  await page.addInitScript(
    ({ base, lng, layoutKey, layout }) => {
      Object.assign(window, { DELIR_API_BASE: base });
      window.localStorage.setItem("delir-language", lng);
      // Il layout che il consulente ha salvato per la tela di simulazione.
      window.localStorage.setItem(layoutKey, layout);
    },
    { base: API, lng: language, layoutKey: simulationLayoutKey, layout: JSON.stringify(simulationLayout) },
  );

  await page.route(`${API}/**`, async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();
    const json = (body: unknown, headers?: Record<string, string>) => route.fulfill({ json: body, headers });

    if (path === "/v1/workspace/projects" && method === "GET") {
      return json(projects, { "X-DeliR-Total": String(projects.length) });
    }
    if (path === "/v1/workspace/clients" && method === "GET") {
      return json(clients, { "X-DeliR-Total": String(clients.length) });
    }
    const clientMatch = path.match(/^\/v1\/workspace\/clients\/([^/]+)$/);
    if (clientMatch && method === "GET") {
      return json(clients.find((client) => client.id === clientMatch[1]) ?? clients[0]);
    }
    if (path.match(/^\/v1\/workspace\/clients\/[^/]+\/sources$/)) return json([]);
    const projectMatch = path.match(/^\/v1\/workspace\/projects\/([^/]+)$/);
    if (projectMatch && method === "GET") {
      return json(projects.find((item) => item.id === projectMatch[1]) ?? project);
    }
    if (path === `/v1/workspace/projects/${IDS.project}/sources`) return json(sources);
    if (path === `/v1/workspace/projects/${IDS.project}/processes`) return json(project.process_items);
    if (path === `/v1/workspace/projects/${IDS.project}/decisions`) return json([]);
    if (path === `/v1/workspace/processes/${IDS.process}`) return json(project.process_items[0]);

    const sourceMatch = path.match(/^\/v1\/workspace\/sources\/([^/]+)(?:\/(claims|relations|document))?$/);
    if (sourceMatch) {
      const [, sourceId, part] = sourceMatch;
      if (part === "claims") return json(claimsOf(sourceId));
      if (part === "relations") return json(relationsOf(sourceId));
      if (part === "document") return json(sourceDocument(sourceId));
      return json(sources.find((source) => source.id === sourceId) ?? null);
    }

    if (path === `/v1/workspace/bpmn-models/${IDS.model}` && method === "GET") {
      return json({ id: IDS.model, process_id: IDS.process, name: "As-Is v3", xml: bpmnXml, version_id: 3 });
    }
    if (path === `/v1/workspace/bpmn-models/${IDS.model}/versions`) {
      return json(versions.map((version) => ({ ...version, xml: bpmnXml })));
    }
    if (path === `/v1/workspace/bpmn-models/${IDS.model}/review` && method === "GET") return json(review);
    if (path === `/v1/workspace/bpmn-models/${IDS.model}/review/versions`) return json([]);
    if (path === `/v1/workspace/processes/${IDS.process}/provenance`) return json(provenance);
    if (path === `/v1/workspace/processes/${IDS.process}/conformance`) return json(conformance);
    if (path === `/v1/workspace/processes/${IDS.process}/impact-review`) return json(impactReview);

    if (path === `/v1/workspace/bpmn-models/${IDS.model}/simulation-template`) return json(api.simulation_template);
    if (path === `/v1/workspace/bpmn-models/${IDS.model}/simulation-provenance`) return json(api.simulation_provenance);
    if (path === `/v1/workspace/bpmn-models/${IDS.model}/simulation-compatibility`) return json(api.simulation_compatibility);
    if (path === `/v1/workspace/bpmn-models/${IDS.model}/simulation-model`) {
      return json({ bpmn_model_id: IDS.model, model: runs().as_is.model });
    }
    if (path === `/v1/workspace/bpmn-models/${IDS.model}/simulation-runs` && method === "GET") return json(simulationRuns);

    const runMatch = path.match(/^\/v1\/workspace\/simulation-runs\/(\d+)(?:\/(replay|experiments|model))?$/);
    if (runMatch) {
      const id = Number(runMatch[1]);
      const data = runData(id);
      if (!data) return route.fulfill({ status: 404, json: { detail: "Simulazione non trovata." } });
      if (runMatch[2] === "replay") return json({ run_id: id, schema_version: 1, replay: data.replay });
      if (runMatch[2] === "experiments") return json(data.experiments);
      if (runMatch[2] === "model") return json({ run_id: id, model: data.model });
      return json(runById(id));
    }

    if (path === "/v1/consultant-chat/sessions" && method === "GET") return json([chatSession]);
    if (path === `/v1/consultant-chat/sessions/${IDS.thread}`) {
      return json({ ...chatSession, model_name: "delir", messages: chatMessages });
    }

    if (path === "/v1/auth/me") {
      // L'etichetta in alto a destra e' lo spazio di lavoro: quello del consulente.
      return json({
        tenant_id: "Studio Bellini",
        auth_mode: "local",
        auth_enabled: false,
        is_admin: false,
        caller_id: "marco-bellini",
        has_user_identity: false,
      });
    }
    if (path === "/v1/workspace/notifications") return json([]);

    unhandled.add(`${method} ${path}`);
    return route.fulfill({ status: 200, json: [] });
  });
}

function runs() {
  return { as_is: runData(IDS.asIsRun)!, to_be: runData(IDS.toBeRun)! };
}
