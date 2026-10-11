import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

// Consegna al responsabile, con dati sintetici: nessun dato di clienti reali.
const API = "http://127.0.0.1:8000";
const BASE = "b".repeat(64);
const trace = (id: string) => `<b:documentation>DeliR traceability: {"source_refs":["steps:${id}"]}</b:documentation>`;
const XML = `<?xml version="1.0" encoding="UTF-8"?>
<b:definitions xmlns:b="http://www.omg.org/spec/BPMN/20100524/MODEL"><b:process id="P">
<b:userTask id="verify" name="Verificare dati">${trace("verify")}</b:userTask>
<b:userTask id="approve" name="Approvare richiesta">${trace("approve")}</b:userTask>
</b:process></b:definitions>`;

type Options = { owner?: string; status?: string; blocking?: boolean };

async function fixture(page: Page, options: Options = {}) {
  let status = options.status ?? "In corso";
  const patches: Array<Record<string, unknown>> = [];
  const actions: Array<Record<string, unknown>> = [
    { id: "change-1", node_id: "approve", node_name: "Approvare richiesta", base_revision: BASE, kind: "candidate", title: "Togliere la seconda firma sotto 5.000 €", detail: "L'approvazione richiede troppo tempo: due firme anche per importi bassi.", created_at: "2026-10-05T10:00:00Z", created_by: "consulente" },
  ];
  const processItem = () => ({ id: "handover-process", project_id: "handover-project", bpmn_model_id: "handover-model", name: "Acquisti indiretti", stage: "TO-BE", status, owner: options.owner ?? "Amministrazione", readiness: 80, archived_at: null, archive_reason: null });
  await page.addInitScript(() => Object.assign(window, { DELIR_API_BASE: "http://127.0.0.1:8000" }));
  await page.route(`${API}/**`, async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/v1/workspace/projects/handover-project") return route.fulfill({ json: {
      id: "handover-project", client_id: "example", client: "Azienda demo", name: "Acquisti", objective: "Ridisegno", lead: "Consulente", start_date: null, end_date: null,
      phase: "TO-BE", status: "In corso", progress: 70, processes: 1, next_step: "Consegna", milestones: [], open_issues: [], deliverables: [], archived_at: null, archive_reason: null,
      process_items: [processItem()],
    } });
    if (path === "/v1/workspace/processes/handover-process" && request.method() === "PATCH") {
      const body = request.postDataJSON() as Record<string, unknown>;
      patches.push(body);
      status = String(body.status);
      return route.fulfill({ json: processItem() });
    }
    if (path.endsWith("/impact-review/actions") && request.method() === "POST") {
      const body = request.postDataJSON() as Record<string, unknown>;
      const action = { ...body, node_name: "Verificare dati", created_at: "2026-10-07T10:00:00Z", created_by: "consulente" };
      actions.push(action);
      return route.fulfill({ status: 201, json: action });
    }
    if (path.endsWith("/impact-review")) return route.fulfill({ json: {
      process_id: "handover-process", base_revision: BASE, xml: XML, actions,
      plan: { title: "Acquisti", actors: [], steps: [], data_objects: [], controls: [], structured_business_rules: [],
        consultant_findings: [{ id: "f1", finding: "L'approvazione richiede troppo tempo.", severity: "warning", recommendation: null }] },
    } });
    if (path.endsWith("/provenance")) return route.fulfill({ json: {
      process_id: "handover-process", snapshot_id: "s", snapshot_label: "V2", has_plan: true, total: 2, verified: 2, paraphrased: 0, label_grounded: 0, unverified: 0, awaiting_confirmation: 0, grounded_ratio: 0.94, sources_checked: 1, unused_sources: [],
      elements: [{ kind: "step", element_id: "approve", label: "Approvare richiesta", source_ref: "steps:approve", status: "verified", mark_status: "verified", source_id: "proc", source_name: "Procedura PROC-14 · esempio", quote: "Ogni richiesta è firmata dal responsabile e dall'Amministrazione.", consultant_decision: null, removable: false }],
    } });
    if (path.endsWith("/conformance")) return route.fulfill({ json: {
      process_id: "handover-process", running: false, is_current: true,
      report: { verdict: options.blocking ? "not_conformant" : "conformant", findings: options.blocking ? [{ layer: "source_contradiction", severity: "blocking", message: "Contrasto", source_name: "PROC-14" }] : [], sources_audited: 1, sources_with_text: 1, llm_audit_note: "", audited_at: "2026-10-06T10:00:00Z" },
    } });
    if (path.endsWith("/versions")) return route.fulfill({ json: [{ id: 7, bpmn_model_id: "handover-model", process_id: "handover-process", change_summary: "To-Be", source: "canvas", created_at: "2026-10-06T09:00:00Z" }] });
    return route.fulfill({ json: [] });
  });
  return { patches, actions };
}

const URL_HANDOVER = "/projects/handover-project/processes/handover-process/handover";

test("the consultant marks a ready process as sent and records the client approval", async ({ page }) => {
  const api = await fixture(page);
  await page.goto(URL_HANDOVER);
  await expect(page.getByRole("heading", { name: "Disegno completato · Pronto per la consegna" })).toBeVisible();
  await expect(page.getByText("Togliere la seconda firma sotto 5.000 €")).toBeVisible();
  await expect(page.getByText("Procedura PROC-14 · esempio")).toBeVisible();

  await page.getByRole("button", { name: "Segna come inviato al cliente" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Segna come inviato al cliente" }).click();
  await expect(page.getByRole("heading", { name: "Inviato a Amministrazione · In attesa della risposta del cliente" })).toBeVisible();
  expect(api.patches.at(-1)).toMatchObject({ status: "Da validare", owner: "Amministrazione" });

  await page.getByRole("button", { name: "Il cliente ha approvato" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Il cliente ha approvato" }).click();
  await expect(page.getByRole("heading", { name: "Approvato dal cliente · Da ora si misurano i risultati" })).toBeVisible();
  expect(api.patches.at(-1)).toMatchObject({ status: "Validato" });
});

test("the consultant records a client change request without editing the diagram", async ({ page }) => {
  const api = await fixture(page, { status: "Da validare" });
  await page.goto(URL_HANDOVER);
  await page.getByRole("button", { name: "Il cliente chiede modifiche" }).click();
  const dialog = page.getByRole("dialog", { name: "Il cliente chiede modifiche" });
  await dialog.getByRole("combobox").click();
  await page.getByRole("option", { name: "Verificare dati" }).click();
  await dialog.getByLabel("In breve").fill("La responsabilità deve restare all'Amministrazione");
  await dialog.getByLabel("Cosa ha chiesto il cliente e perché").fill("Il controllo dei dati è oggi in carico all'Amministrazione.");
  await dialog.getByRole("button", { name: "Registra la richiesta" }).click();
  await expect(dialog).toBeHidden();
  expect(api.actions.at(-1)).toMatchObject({ kind: "clarification", node_id: "verify", base_revision: BASE });
  expect(api.patches.at(-1)).toMatchObject({ status: "In corso" });
  await expect(page.getByText("La responsabilità deve restare all'Amministrazione")).toBeVisible();
});

test("a process without owner or with conflicting documents cannot be sent", async ({ page }) => {
  await fixture(page, { owner: "", blocking: true });
  await page.goto(URL_HANDOVER);
  await expect(page.getByRole("heading", { name: "Non ancora pronto per la consegna" })).toBeVisible();
  await expect(page.getByText("2 controlli importanti non sono superati.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Segna come inviato al cliente" })).toBeDisabled();
});

for (const viewport of [{ name: "desktop", width: 1440, height: 1000 }, { name: "mobile", width: 390, height: 844 }]) {
  test(`hand over page is accessible and does not overflow on ${viewport.name}`, async ({ page }, info) => {
    await page.setViewportSize(viewport);
    await fixture(page);
    await page.goto(URL_HANDOVER);
    await expect(page.getByRole("heading", { name: "Pronto per la consegna?" })).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);
    const results = await new AxeBuilder({ page }).include(".handover").analyze();
    expect(results.violations.map((violation) => violation.id)).toEqual([]);
    await page.screenshot({ path: info.outputPath(`handover-${viewport.name}.png`), fullPage: true });
  });
}
