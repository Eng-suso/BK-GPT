import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

// Synthetic workspace: screenshots and interaction checks never use customer data.
const process = { id: "satin-process", project_id: "satin-project", bpmn_model_id: "satin-model", name: "Gestione richieste", stage: "AS-IS", status: "Da validare", owner: "Team Operations", readiness: 65 };
const project = { id: "satin-project", client_id: "satin-client", client: "Azienda Demo", name: "Ottimizzazione operativa", phase: "AS-IS", status: "In corso", progress: 45, processes: 1, next_step: "Validare il processo", milestones: [], open_issues: [], deliverables: [], process_items: [process] };
const client = { id: "satin-client", name: "Azienda Demo", sector: "Servizi", status: "Attivo", projects: 1, next_activity: "Revisione processo", owner: "Team Operations", contact: "", processes: [], documents: [] };
const xml = `<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" id="Definitions_satin" targetNamespace="https://example.test/satin">
<bpmn:process id="Process_satin" isExecutable="false"><bpmn:userTask id="Task_satin" name="Verifica richiesta" /></bpmn:process>
<bpmndi:BPMNDiagram id="Diagram_satin"><bpmndi:BPMNPlane id="Plane_satin" bpmnElement="Process_satin"><bpmndi:BPMNShape id="Shape_satin" bpmnElement="Task_satin"><dc:Bounds x="180" y="180" width="160" height="90" /></bpmndi:BPMNShape></bpmndi:BPMNPlane></bpmndi:BPMNDiagram></bpmn:definitions>`;

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => { window.localStorage.setItem("i18nextLng", "it"); });
  await page.route("http://127.0.0.1:8000/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let data: unknown = [];
    if (path === "/v1/workspace/projects") data = [project];
    else if (path === "/v1/workspace/clients") data = [client];
    else if (path === "/v1/workspace/projects/satin-project") data = project;
    else if (path.endsWith("/archive")) data = { clients: [], projects: [], processes: [] };
    else if (path.endsWith("/satin-model")) data = { id: "satin-model", process_id: "satin-process", name: "Modello demo", xml };
    else if (path.endsWith("/review")) data = null;
    else if (path.endsWith("/simulation-template")) data = { tasks: [{ element_id: "Task_satin", name: "Verifica richiesta", type: "userTask" }], gateways: [] };
    else if (path.endsWith("/simulation-provenance")) data = { has_discovery: false, elements: [] };
    await route.fulfill({ json: data });
  });
});

for (const width of [1440, 390]) {
  test(`history failure and recovery preserve the draft at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await page.route(/\/v1\/consultant-chat\/sessions(?:\?.*)?$/, async (route) => {
      const available = await page.evaluate(() => document.documentElement.dataset.historyAvailable === "true");
      return available ? route.fulfill({ json: [] }) : route.abort("connectionrefused");
    });
    await page.goto("/consultant");
    await page.locator("textarea").fill("Bozza conservata durante la riconnessione");
    const notice = page.locator(".chat-service-notice");
    await expect(notice).toBeVisible();
    await expect(notice).not.toContainText("127.0.0.1");
    expect((await notice.boundingBox())!.width).toBeLessThanOrEqual(900);
    expect((await new AxeBuilder({ page }).include(".chat-service-notice").withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
    await page.screenshot({ path: testInfo.outputPath(`history-unavailable-${width}.png`) });
    // Recovery starts with the user's click; background query retries cannot
    // remove the button between making the fixture available and clicking it.
    await notice.getByRole("button").evaluate((button) => button.addEventListener("click", () => {
      document.documentElement.dataset.historyAvailable = "true";
    }, { capture: true, once: true }));
    await notice.getByRole("button").click();
    await expect(notice).toBeHidden();
    await expect(page.locator("textarea")).toHaveValue("Bozza conservata durante la riconnessione");
  });

  test(`satin workspace remains usable at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    const routes = ["/home", "/projects", "/clients", "/consultant", "/models", "/archive", "/projects/satin-project", "/projects/satin-project/processes/satin-process?view=canvas", "/projects/satin-project/processes/satin-process/simulation/scenario"];
    for (const [index, route] of routes.entries()) {
      await page.goto(route);
      await expect(page.locator("main")).toBeVisible();
      await expect(page.locator('[data-slot="skeleton"]')).toHaveCount(0);
      if (route.includes("view=canvas")) await expect(page.locator('[data-element-id="Task_satin"]').first()).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({ path: testInfo.outputPath(`surface-${index}-${width}.png`) });
    }
    expect(errors).toEqual([]);
  });

  test(`composer menu and form keep keyboard access at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/consultant");
    const draft = "Bozza di verifica";
    await page.locator("textarea").fill(draft);
    const add = page.locator(".composer-add");
    await add.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("menu")).toBeVisible();
    await page.keyboard.press("ArrowDown");
    await expect(page.locator('[role="menuitem"]:focus')).toHaveCount(1);
    expect((await new AxeBuilder({ page }).include('[role="menu"]').withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
    await page.screenshot({ path: testInfo.outputPath(`composer-menu-${width}.png`) });
    await page.keyboard.press("Escape");
    await expect(add).toBeFocused();
    await expect(page.locator("textarea")).toHaveValue(draft);
    await page.goto("/projects");
    await page.getByRole("button", { name: /Nuovo progetto/i }).first().click();
    await expect(page.getByRole("dialog")).toBeVisible();
    const field = page.getByRole("dialog").locator('[data-slot="input"]').first();
    await field.focus();
    expect(await field.evaluate((element) => getComputedStyle(element).outlineStyle)).not.toBe("none");
    expect((await new AxeBuilder({ page }).include('[role="dialog"]').withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
    await page.screenshot({ path: testInfo.outputPath(`project-form-${width}.png`) });
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toBeHidden();
  });
}
