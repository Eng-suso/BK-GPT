import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const studio = "/projects/layout-project/processes/layout-process";
const tasks = Array.from({ length: 18 }, (_, index) => ({
  element_id: `Task_${index + 1}`,
  name: `Attività ${index + 1}: verifica della documentazione e approvazione della richiesta`,
  type: "userTask",
}));
const xml = `<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" xmlns:di="http://www.omg.org/spec/DD/20100524/DI" id="Definitions_layout" targetNamespace="https://example.test/layout">
<bpmn:process id="Process_layout" isExecutable="false">${tasks.map((task) => `<bpmn:userTask id="${task.element_id}" name="${task.name}" />`).join("")}${tasks.slice(1).map((task, i) => `<bpmn:sequenceFlow id="Flow_${i}" sourceRef="${tasks[i].element_id}" targetRef="${task.element_id}" />`).join("")}</bpmn:process>
<bpmndi:BPMNDiagram id="Diagram_layout"><bpmndi:BPMNPlane id="Plane_layout" bpmnElement="Process_layout">${tasks.map((task, i) => `<bpmndi:BPMNShape id="${task.element_id}_di" bpmnElement="${task.element_id}"><dc:Bounds x="${80 + (i % 6) * 210}" y="${80 + Math.floor(i / 6) * 180}" width="160" height="90" /></bpmndi:BPMNShape>`).join("")}${tasks.slice(1).map((task, i) => `<bpmndi:BPMNEdge id="Flow_${i}_di" bpmnElement="Flow_${i}"><di:waypoint x="${240 + (i % 6) * 210}" y="${125 + Math.floor(i / 6) * 180}" /><di:waypoint x="${80 + ((i + 1) % 6) * 210}" y="${125 + Math.floor((i + 1) / 6) * 180}" /></bpmndi:BPMNEdge>`).join("")}</bpmndi:BPMNPlane></bpmndi:BPMNDiagram></bpmn:definitions>`;

async function fixture(page: Page) {
  await page.addInitScript(() => Object.assign(window, { DELIR_API_BASE: "http://127.0.0.1:8000" }));
  await page.route("http://127.0.0.1:8000/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    let data: unknown = null;
    if (path === "/v1/workspace/projects/layout-project") data = {
      id: "layout-project", client_id: "demo", client: "Azienda Demo", name: "Progetto dimostrativo", phase: "AS-IS", status: "In corso", progress: 50, processes: 1,
      next_step: "Validare il modello", milestones: [], open_issues: [], deliverables: [],
      process_items: [{ id: "layout-process", project_id: "layout-project", bpmn_model_id: "layout-model", name: "Gestione richieste e approvazioni", stage: "AS-IS", status: "Da validare", owner: "Team Operations", readiness: 65 }],
    };
    else if (path.endsWith("/simulation-template")) data = { tasks, gateways: [] };
    else if (path.endsWith("/simulation-provenance")) data = { has_discovery: false, elements: [] };
    else if (path.endsWith("/simulation-runs") && request.method() === "POST") data = {
      id: 1, bpmn_model_id: "layout-model", process_id: "layout-process", scenario_name: "Scenario demo", engine: "prosimos", status: "completed", request: request.postDataJSON(), scenario: {}, result: {}, outputs: [], error: null, created_at: "2026-09-06T10:00:00Z", completed_at: "2026-09-06T10:00:01Z",
    };
    else if (path.endsWith("/versions") || path.endsWith("/sessions") || path.endsWith("/simulation-runs")) data = [];
    else if (path.endsWith("/layout-model")) data = { id: "layout-model", process_id: "layout-process", name: "Modello demo", xml };
    else if (!path.endsWith("/review")) return route.fulfill({ status: 503, json: { detail: "Synthetic fixture: endpoint unavailable" } });
    await route.fulfill({ json: data });
  });
}

test.beforeEach(async ({ page }) => { await fixture(page); });

test("laptop tools preserve canvas space and unsaved model edits", async ({ page }) => {
  await page.setViewportSize({ width: 1366, height: 768 });
  await page.goto(studio);
  const canvas = page.locator(".process-bpmn-canvas");
  await page.locator('[data-element-id="Task_1"]').first().click();
  await page.getByRole("textbox", { name: "Etichetta / Nome" }).fill("Modifica da conservare");
  await page.getByRole("button", { name: "Chat canvas", exact: true }).click();
  await expect(page.locator(".process-studio-chat")).toBeVisible();
  await expect.poll(async () => (await canvas.boundingBox())?.width ?? 0).toBeGreaterThan(720);
  await page.getByRole("button", { name: "Proprietà", exact: true }).click();
  await expect(page.locator(".process-studio-chat")).toBeHidden();
  await expect(page.locator(".process-studio-properties")).toBeVisible();
  await expect.poll(async () => (await canvas.boundingBox())?.width ?? 0).toBeGreaterThan(720);
  const before = (await canvas.boundingBox())!.width;
  await page.getByRole("button", { name: "Importa, esporta, cronologia" }).click();
  await page.getByRole("menuitem", { name: "Cronologia versioni" }).click();
  await expect(page.getByRole("dialog", { name: "Cronologia versioni" })).toBeVisible();
  expect((await canvas.boundingBox())!.width).toBeCloseTo(before, 0);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "Importa, esporta, cronologia" })).toBeFocused();
  await page.getByRole("button", { name: "Chiudi i pannelli", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "Etichetta / Nome" })).toHaveValue("Modifica da conservare");
  const saved = page.waitForRequest((req) => req.method() === "PUT" && req.url().endsWith("/layout-model"));
  await page.getByRole("button", { name: "Salva", exact: true }).click();
  expect((await saved).postDataJSON().xml).toContain("Modifica da conservare");
});

test("scenario supports long activity lists, model reference and execution", async ({ page }) => {
  await page.setViewportSize({ width: 1366, height: 768 });
  await page.goto(`${studio}/simulation/scenario`);
  const row = page.locator('[data-sim-el="Task_18"]');
  await row.scrollIntoViewIfNeeded();
  await expect(row).toBeVisible();
  const run = page.getByRole("button", { name: "Avvia simulazione", exact: true });
  await expect(run).toBeInViewport();
  await row.getByRole("spinbutton").fill("37");
  expect((await row.getByRole("spinbutton").boundingBox())!.width).toBeGreaterThanOrEqual(100);
  await page.getByRole("button", { name: "Mostra modello" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  expect((await page.getByRole("dialog").boundingBox())!.width).toBeGreaterThan(1100);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "Mostra modello" })).toBeFocused();
  await expect(row.getByRole("spinbutton")).toHaveValue("37");
  await page.getByRole("button", { name: "Mostra modello" }).click();
  await page.getByRole("dialog").locator('[data-element-id="Task_18"]').first().click();
  await expect(row.getByRole("spinbutton")).toBeFocused();
  const request = page.waitForRequest((req) => req.method() === "POST" && req.url().endsWith("/simulation-runs"));
  await run.click();
  const body = (await request).postDataJSON();
  expect(body.tasks.find((task: { element_id: string }) => task.element_id === "Task_18").mean_seconds).toBe(2220);
});

test("mobile tools are reachable and scenario controls stay inside the viewport", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(studio);
  await page.getByRole("button", { name: "Chat canvas", exact: true }).click();
  await expect(page.locator(".process-studio-chat")).toBeVisible();
  await expect(page.getByRole("button", { name: "Chiudi i pannelli", exact: true })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "Chat canvas", exact: true })).toBeFocused();
  await page.getByRole("button", { name: "Proprietà", exact: true }).click();
  await page.getByRole("button", { name: "Chiudi i pannelli", exact: true }).click();
  await page.goto(`${studio}/simulation/scenario`);
  await page.locator('[data-sim-el="Task_18"]').scrollIntoViewIfNeeded();
  await expect(page.getByRole("button", { name: "Avvia simulazione", exact: true })).toBeInViewport();
  const overflow = await page.locator("main input, main [role=combobox]").evaluateAll((elements) => elements.filter((element) => {
    const box = element.getBoundingClientRect();
    return box.width > 0 && (box.right > innerWidth + 1 || box.left < 0);
  }).length);
  expect(overflow).toBe(0);
  const scan = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag22aa"]).analyze();
  expect(scan.violations).toEqual([]);
  expect(errors).toEqual([]);
});

for (const [surface, path] of [
  ["consultant", "/consultant"],
  ["project", "/projects/layout-project?tab=chat"],
  ["process", `${studio}?view=chat`],
  ["canvas", studio],
] as const) {
  test(`${surface} chat keeps long conversations and composer usable on laptop and mobile`, async ({ page }) => {
    const session = {
      thread_id: "layout-chat", title: "Analisi del processo dimostrativo con un titolo esteso",
      created_at: "2026-09-06T10:00:00Z", updated_at: "2026-09-06T10:00:00Z",
      messages: Array.from({ length: 12 }, (_, i) => ({
        id: i, role: i % 2 ? "assistant" : "user",
        content: i % 2 ? "Ogni passaggio ha un responsabile e un esito esplicito. ".repeat(24) : `Analizziamo il passaggio ${i + 1}.`,
      })),
    };
    await page.route("**/v1/consultant-chat/sessions**", (route) => route.fulfill({
      json: new URL(route.request().url()).pathname.endsWith("/sessions") ? [session] : session,
    }));
    await page.setViewportSize({ width: 1366, height: 768 });
    await page.goto(path);
    if (surface === "canvas") await page.getByRole("button", { name: "Chat canvas", exact: true }).click();
    const composer = page.locator(".composer-wrap");
    const input = composer.getByRole("textbox");
    await expect(input).toBeVisible();
    await expect(page.locator(".message-list")).toContainText("Analizziamo il passaggio 11.");

    for (const size of [{ width: 1366, height: 768 }, { width: 390, height: 844 }]) {
      await page.setViewportSize(size);
      await input.fill("Bozza da conservare\n".repeat(20));
      await expect(composer.getByRole("button", { name: "Invia", exact: true })).toBeInViewport();
      await expect.poll(() => composer.locator("button").evaluateAll((buttons) => buttons.filter((button) => {
        const rect = button.getBoundingClientRect();
        return rect.width > 0 && (rect.right > innerWidth + 1 || rect.left < 0 || rect.bottom > innerHeight + 1);
      }).length)).toBe(0);
      // La modalita' di lavoro sta dietro un menu, non piu' su tre radio a
      // vista: la barra dice cosa e' scelto e le alternative stanno a un click.
      // Il menu si apre in un portal fuori da `.composer-wrap`, e i suoi item
      // sono `menuitemradio`. Qui conta che si apra, che stia dentro il
      // viewport anche a 390px, e che la scelta arrivi al trigger.
      const modeTrigger = composer.locator(".chat-mode-trigger");
      await expect(modeTrigger).toBeInViewport();
      await modeTrigger.click();
      const modeMenu = page.getByRole("menu");
      await expect(modeMenu).toBeVisible();
      expect(await modeMenu.evaluate((element) => {
        const rect = element.getBoundingClientRect();
        return rect.right > innerWidth + 1 || rect.left < -1
          || rect.bottom > innerHeight + 1 || rect.top < -1;
      })).toBe(false);
      const chosen = modeMenu.getByRole("menuitemradio", { name: /Modifica/ });
      await chosen.click();
      await expect(modeMenu).toBeHidden();
      await expect(modeTrigger).toContainText("Modifica");
      // Riaperto, il menu ricorda la scelta invece di ripartire dal default.
      await modeTrigger.click();
      await expect(page.getByRole("menuitemradio", { name: /Modifica/ })).toBeChecked();
      await page.keyboard.press("Escape");
      await expect(page.getByRole("menu")).toBeHidden();
      const messages = page.locator(".messages, .embedded-chat-body");
      expect(await messages.evaluate((element) => element.scrollHeight > element.clientHeight)).toBe(true);
      await messages.evaluate((element) => element.scrollTo(0, 0));
      await expect(input).toHaveValue("Bozza da conservare\n".repeat(20));
      await expect(composer.getByRole("button", { name: "Invia", exact: true })).toBeInViewport();
    }
    if (surface === "consultant") {
      const history = page.getByRole("button", { name: "Cronologia", exact: true });
      await history.click();
      await expect(page.getByRole("dialog")).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(history).toBeFocused();
    }
    await page.route("**/v1/audio/transcriptions", (route) => route.fulfill({ json: { text: "Trascrizione dimostrativa del processo." } }));
    await composer.locator('input[type="file"]').setInputFiles({ name: "synthetic-audio.wav", mimeType: "audio/wav", buffer: Buffer.from("synthetic fixture") });
    await expect(input).toHaveValue(/Trascrizione dimostrativa del processo\./);
    await expect(composer.getByRole("button", { name: "Invia", exact: true })).toBeInViewport();
    const transcript = page.getByRole("button", { name: "Apri trascrizione", exact: true });
    await transcript.click();
    await expect(page.getByRole("dialog", { name: "Trascrizione audio" })).toContainText("Trascrizione dimostrativa del processo.");
    await page.keyboard.press("Escape");
    await expect(transcript).toBeFocused();
    const scan = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag22aa"]).analyze();
    expect(scan.violations).toEqual([]);
  });
}

test("mobile heatmap preserves a readable diagram above populated metrics", async ({ page }) => {
  const summary = {
    casesCompleted: 100, cycle: { avg: 7200, p50: 6600, p90: 10000, p95: 12000 },
    waiting: { avg: 4200, p95: 9000, share: 0.58 }, processing: { avg: 3000 },
    cost: { total: 3000, perCase: 30 }, throughputPerHour: 12,
    byActivity: tasks.map((task) => ({ el: task.element_id, name: task.name, count: 100, wait: { avg: 2000, p95: 4200 } })),
    byResource: [], bottleneck: { el: "Task_1", score: 0.8 },
  };
  await page.route("**/simulation-runs", (route) => route.fulfill({ json: [{
    id: 1, bpmn_model_id: "layout-model", process_id: "layout-process", scenario_name: "Scenario demo", engine: "prosimos", status: "completed", request: {}, scenario: {}, result: {}, outputs: [], summary, error: null, created_at: "2026-09-06T10:00:00Z", completed_at: "2026-09-06T10:00:01Z",
  }] }));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${studio}/simulation/heatmap/1`);
  await expect(page.locator(".djs-container")).toBeVisible();
  expect((await page.locator(".djs-container").boundingBox())!.height).toBeGreaterThan(300);
  await page.getByRole("button", { name: /Attività 18:/ }).scrollIntoViewIfNeeded();
  await expect(page.getByRole("button", { name: /Attività 18:/ })).toBeInViewport();
  const scan = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag22aa"]).analyze();
  expect(scan.violations).toEqual([]);
});
