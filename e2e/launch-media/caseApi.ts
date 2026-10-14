import type { Page, Route } from "@playwright/test";

import { API, unhandled } from "./mockApi";
import { IDS, demoCase, portfolio, simulationLayout, simulationLayoutKey, vetranoModel, type Lang, type SimulationLayoutKind } from "./vetrano";

/**
 * Il mock delle API per i nuovi video (caso `vetrano.ts`), in italiano o in
 * inglese. Copre le schermate che le scene mostrano; una richiesta scoperta
 * finisce in `unhandled` e lo spec la stampa, cosi' un buco si vede.
 */
export async function installCaseApi(page: Page, lang: Lang, options: { layout?: SimulationLayoutKind } = {}): Promise<void> {
  const data = demoCase(lang);
  // Il resto dello studio: Home, Modelli, ricerca e Archivio non mostrano un solo cliente.
  const studio = portfolio(lang);
  const projects = [data.project, ...studio.projects];
  const clients = [data.clients[0], ...studio.clients];
  // Le conversazioni con DeliR: il tipo (consulente, processo, review) sta nel
  // `thread_id`, cosi' lo streaming in pagina sceglie il copione (filmChat.ts).
  type Session = { thread_id: string; scope_key: string; title: string; model_name: string; created_at: string; updated_at: string; messages: { role: string; content: string }[] };
  const sessions: Session[] = [];
  let ownerLink: Record<string, unknown> = { active: false, view_count: 0 };
  await page.addInitScript(
    ({ base, lng, layoutKey, layout }) => {
      Object.assign(window, { DELIR_API_BASE: base });
      window.localStorage.setItem("delir-language", lng);
      // La tela di simulazione salvata dal consulente: processo e KPI a tutto schermo.
      window.localStorage.setItem(layoutKey, layout);
    },
    { base: API, lng: lang, layoutKey: simulationLayoutKey, layout: JSON.stringify(simulationLayout(lang, options.layout)) },
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
    if (path === `${W}/projects` && method === "GET") return json(projects, { "X-DeliR-Total": String(projects.length) });
    if (path === `${W}/clients` && method === "GET") return json(clients, { "X-DeliR-Total": String(clients.length) });
    if (path === `${W}/clients/${IDS.client}`) return json(data.clients[0]);
    const other = studio.projects.find((item) => path.startsWith(`${W}/projects/${item.id}`));
    if (other) return json(path === `${W}/projects/${other.id}` ? other : path.endsWith("/processes") ? other.process_items : []);
    const otherClient = studio.clients.find((item) => path.startsWith(`${W}/clients/${item.id}`));
    if (otherClient) return json(path === `${W}/clients/${otherClient.id}` ? otherClient : []);
    if (path === `${W}/models`) return json([vetranoModel(lang), ...studio.models]);
    if (path === `${W}/archive`) return json(studio.archive);
    // La pagina del consulente senza progetto scelto.
    if (path === `${W}/projects/` || path === `${W}/projects//sources`) return json([]);
    if (path === `${W}/clients/${IDS.client}/sources`) return json([]);
    if (path === `${W}/projects/${IDS.project}`) return json(data.project);
    if (path === `${W}/projects/${IDS.project}/sources`) return json(data.sources);
    if (path === `${W}/projects/${IDS.project}/processes`) return json(data.project.process_items);
    if (path === `${W}/projects/${IDS.project}/decisions`) return json([]);
    if (path === `${W}/processes/${IDS.process}`) {
      // Consegna: "Ho inviato il link" porta il processo in attesa della risposta.
      if (method === "PATCH") {
        const body = request.postDataJSON() as { status?: string };
        if (body.status) data.processItem.status = body.status;
      }
      return json(data.processItem);
    }
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
    if (path === `${W}/processes/${IDS.process}/impact-review`) return json(data.impactReview);
    if (path === `${W}/processes/${IDS.process}/owner-dashboard`) return json(data.ownerDashboard);
    // Il link privato per il responsabile: non esiste finche' il consulente non lo crea.
    if (path === `${W}/processes/${IDS.process}/owner-link`) {
      if (method === "POST") {
        ownerLink = { active: true, created_at: "2026-10-13T09:30:00Z", expires_at: "2026-11-12T09:30:00Z", last_viewed_at: null, view_count: 0 };
        return json({ token: "demo-vetrano-link", created_at: ownerLink.created_at, expires_at: ownerLink.expires_at });
      }
      if (method === "DELETE") {
        ownerLink = { active: false, view_count: 0 };
        return route.fulfill({ status: 204 });
      }
      return json(ownerLink);
    }
    if (path === `${M}/simulation-template`) return json(data.api.simulation_template);
    if (path === `${M}/simulation-compatibility`) return json(data.api.simulation_compatibility);
    if (path === `${M}/simulation-runs` && method === "GET") return json(data.simulationRuns);
    if (path === `${M}/simulation-claims`) return json({ sources: data.sources.length, activities: [] });
    if (path === `${M}/simulation-provenance`) return json({ has_discovery: false, elements: [] });
    if (path === `${M}/simulation-scenarios` && method === "GET") return json({ bpmn_model_id: IDS.model, seed: 7, baseline: null, alternatives: [] });
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

    const C = "/v1/consultant-chat/sessions";
    if (path === C && method === "GET") {
      const scopeKey = new URL(request.url()).searchParams.get("scope_key") ?? "";
      return json(sessions.filter((session) => session.scope_key === scopeKey));
    }
    if (path === C && method === "POST") {
      const scope = (request.postDataJSON() as { scope?: Record<string, string> }).scope ?? {};
      const kind = scope.review_node_id ? "review" : scope.type === "consultant" ? "consultant" : "process";
      const scopeKey = scope.type === "consultant" ? "consultant"
        : scope.type === "project" ? `project:${scope.project_id}`
        : scope.type === "process" ? `process:${scope.project_id}:${scope.process_id}`
        : `canvas:${scope.project_id}:${scope.process_id}:${scope.bpmn_model_id}${scope.review_node_id ? `:review:${scope.review_node_id}` : ""}`;
      const now = "2026-10-14T09:30:00Z";
      const session: Session = { thread_id: `film-${kind}-${sessions.length + 1}`, scope_key: scopeKey, title: "", model_name: "delir", created_at: now, updated_at: now, messages: [] };
      sessions.push(session);
      return json(session);
    }
    const recordMatch = path.match(/^\/v1\/consultant-chat\/sessions\/([^/]+)\/messages\/__record$/);
    if (recordMatch) {
      const body = request.postDataJSON() as { message: string; answer: string };
      const session = sessions.find((item) => item.thread_id === recordMatch[1]);
      session?.messages.push({ role: "user", content: body.message }, { role: "assistant", content: body.answer });
      if (session && !session.title) session.title = body.message.slice(0, 40);
      return json({ ok: true });
    }
    const session = sessions.find((item) => path === `${C}/${item.thread_id}`);
    if (session) return json(session);
    if (path === `${C}/search`) return json([]);

    unhandled.add(`${method} ${path}`);
    return route.fulfill({ status: 200, json: [] });
  });
}
