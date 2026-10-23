import type { Page, Route } from "@playwright/test";

import type { ChatScript, SimpleCase } from "./case";

export const API = "http://127.0.0.1:8000";

/** Richieste che il caso non copre: lo spec le stampa, cosi' un buco si vede. */
export const unhandled = new Set<string>();

/**
 * Il backend del caso semplice, per le riprese della landing. Stesse rotte di
 * `../mockApi.ts`, dati di `case.ts`. Le risposte dell'agente arrivano in
 * streaming da `../streamServer.mjs`, come dal backend vero.
 */
export async function installSimpleApi(page: Page, demo: SimpleCase): Promise<void> {
  const { IDS } = demo;
  const sessions: { thread_id: string; scope_key: string; title: string; messages: { role: string; content: string }[] }[] = [];
  let ownerLink = { active: false, created_at: null as string | null, expires_at: null as string | null, last_viewed_at: null as string | null, view_count: 0 };

  await page.addInitScript(
    ({ base, lng, layoutKey, layout }) => {
      Object.assign(window, { DELIR_API_BASE: base });
      window.localStorage.setItem("delir-language", lng);
      window.localStorage.setItem(layoutKey, layout);
    },
    { base: API, lng: demo.lang, layoutKey: demo.simulationLayoutKey, layout: JSON.stringify(demo.simulationLayout) },
  );

  await page.route(`${API}/**`, async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();
    const json = (body: unknown, headers?: Record<string, string>) => route.fulfill({ json: body, headers });

    if (path === "/v1/workspace/projects" && method === "GET") return json(demo.projects, { "X-DeliR-Total": String(demo.projects.length) });
    if (path === "/v1/workspace/clients" && method === "GET") return json(demo.clients, { "X-DeliR-Total": String(demo.clients.length) });
    const clientMatch = path.match(/^\/v1\/workspace\/clients\/([^/]+)$/);
    if (clientMatch && method === "GET") return json(demo.clients.find((client) => client.id === clientMatch[1]) ?? demo.clients[0]);
    if (path.match(/^\/v1\/workspace\/clients\/[^/]+\/sources$/)) return json([]);
    const projectMatch = path.match(/^\/v1\/workspace\/projects\/([^/]+)$/);
    if (projectMatch && method === "GET") return json(demo.projects.find((item) => item.id === projectMatch[1]) ?? demo.project);
    if (path === `/v1/workspace/projects/${IDS.project}/sources`) return json(demo.sources);
    if (path === `/v1/workspace/projects/${IDS.project}/processes`) return json(demo.project.process_items);
    if (path === `/v1/workspace/projects/${IDS.project}/decisions`) return json([]);
    if (path === `/v1/workspace/processes/${IDS.process}`) return json(demo.processItem);

    const sourceMatch = path.match(/^\/v1\/workspace\/sources\/([^/]+)(?:\/(claims|relations|document))?$/);
    if (sourceMatch) {
      const [, sourceId, part] = sourceMatch;
      if (part === "claims") return json(demo.claimsOf(sourceId));
      if (part === "relations") return json(demo.relationsOf(sourceId));
      if (part === "document") return json(demo.sourceDocument(sourceId));
      return json(demo.sources.find((source) => source.id === sourceId) ?? null);
    }

    if (path === `/v1/workspace/bpmn-models/${IDS.model}` && method === "GET") {
      return json({ id: IDS.model, process_id: IDS.process, name: "As-Is v3", xml: demo.bpmnXml, version_id: 3 });
    }
    if (path === `/v1/workspace/bpmn-models/${IDS.model}/versions`) return json(demo.versions.map((version) => ({ ...version, xml: demo.bpmnXml })));
    if (path === `/v1/workspace/bpmn-models/${IDS.model}/review` && method === "GET") return json(demo.review);
    if (path === `/v1/workspace/bpmn-models/${IDS.model}/review/versions`) return json([]);
    if (path === `/v1/workspace/processes/${IDS.process}/provenance`) return json(demo.provenance);
    if (path === `/v1/workspace/processes/${IDS.process}/conformance`) return json(demo.conformance);
    if (path === `/v1/workspace/processes/${IDS.process}/impact-review`) return json(demo.impactReview);
    if (path === `/v1/workspace/processes/${IDS.process}/event-logs` && method === "GET") return json([]);
    if (path === "/v1/workspace/event-log-templates") return json([]);

    if (path === `/v1/workspace/processes/${IDS.process}/owner-link`) {
      if (method === "POST") {
        ownerLink = { active: true, created_at: "2026-10-15T11:00:00Z", expires_at: "2026-11-14T11:00:00Z", last_viewed_at: null, view_count: 0 };
        return json({ token: "vetrano-richiesta-acquisto-7f3a", created_at: ownerLink.created_at, expires_at: ownerLink.expires_at });
      }
      if (method === "DELETE") {
        ownerLink = { ...ownerLink, active: false };
        return route.fulfill({ status: 204, body: "" });
      }
      return json(ownerLink);
    }
    if (path === `/v1/workspace/processes/${IDS.process}/owner-dashboard`) return json(demo.ownerDashboard);

    const api = demo.api as Record<string, unknown>;
    if (path === `/v1/workspace/bpmn-models/${IDS.model}/simulation-template`) return json(api.simulation_template);
    if (path === `/v1/workspace/bpmn-models/${IDS.model}/simulation-provenance`) return json(api.simulation_provenance);
    if (path === `/v1/workspace/bpmn-models/${IDS.model}/simulation-compatibility`) return json(api.simulation_compatibility);
    if (path === `/v1/workspace/bpmn-models/${IDS.model}/simulation-claims`) return json([]);
    if (path === `/v1/workspace/bpmn-models/${IDS.model}/simulation-model`) return json({ bpmn_model_id: IDS.model, model: demo.runs.as_is.model });
    if (path === `/v1/workspace/bpmn-models/${IDS.model}/simulation-runs` && method === "GET") return json(demo.workspaceRuns);
    if (path === `/v1/workspace/bpmn-models/${IDS.model}/simulation-scenarios` && method === "GET") return json(demo.workspace);

    const runMatch = path.match(/^\/v1\/workspace\/simulation-runs\/(\d+)(?:\/(replay|experiments|model))?$/);
    if (runMatch) {
      const id = Number(runMatch[1]);
      const data = demo.runData(id);
      if (!runMatch[2]) return json(demo.runById(id));
      if (!data) return route.fulfill({ status: 404, json: { detail: "Simulazione non trovata." } });
      if (runMatch[2] === "replay") return json({ run_id: id, schema_version: 1, replay: data.replay });
      if (runMatch[2] === "experiments") return json(data.experiments);
      return json({ run_id: id, model: data.model });
    }

    // La chat di review e' per task (scope_key con ":review:"): sessioni sue, separate dalla discussione.
    if (path === "/v1/consultant-chat/sessions" && method === "GET") {
      const scopeKey = url.searchParams.get("scope_key") ?? "";
      if (scopeKey.includes(":review:")) return json(sessions.filter((session) => session.scope_key === scopeKey));
      return json(sessions.filter((session) => !session.scope_key.includes(":review:")));
    }
    if (path === "/v1/consultant-chat/sessions" && method === "POST") {
      const scope = (request.postDataJSON() as { scope?: Record<string, string> }).scope ?? {};
      const session = {
        thread_id: `thread-${sessions.length + 1}`,
        scope_key: scope.review_node_id
          ? `canvas:${scope.project_id}:${scope.process_id}:${scope.bpmn_model_id}:review:${scope.review_node_id}`
          : `${scope.type}:${scope.project_id}:${scope.process_id}`,
        title: scope.review_node_id ? "Review" : demo.chatSession.title,
        messages: [] as { role: string; content: string }[],
      };
      sessions.push(session);
      return json(session);
    }
    const streamMatch = path.match(/^\/v1\/consultant-chat\/sessions\/([^/]+)\/messages\/stream$/);
    if (streamMatch) {
      const session = sessions.find((item) => item.thread_id === streamMatch[1]);
      const body = request.postDataJSON() as Record<string, unknown>;
      const script: ChatScript = session?.scope_key.includes(":review:") ? demo.reviewScript : demo.discoveryScript;
      session?.messages.push({ role: "user", content: String(body.message ?? "") }, { role: "assistant", content: script.answer });
      return route.continue({ postData: JSON.stringify({ ...body, __script: script }) });
    }
    const session = sessions.find((item) => path === `/v1/consultant-chat/sessions/${item.thread_id}`);
    if (session) return json(session);

    if (path === "/v1/auth/me") {
      return json({ tenant_id: "Studio Bellini", auth_mode: "local", auth_enabled: false, is_admin: false, caller_id: "marco-bellini", has_user_identity: false });
    }
    if (path === "/v1/workspace/notifications") return json([]);

    unhandled.add(`${method} ${path}`);
    return route.fulfill({ status: 200, json: [] });
  });
}
