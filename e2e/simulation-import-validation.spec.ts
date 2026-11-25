import { readFileSync } from "node:fs";

import { test, expect, type Locator, type Page, type TestInfo } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

/**
 * VAL-01: all'import DeliR rifiuta un processo in cui qualche caso non arriverebbe mai
 * alla fine (qui un ciclo con l'uscita a probabilita' 0) e lo dice in parole del
 * consulente, con cosa fare; lo scenario resta com'era. Vale per lo scenario SIMOD che
 * legge il server e per il file che l'editor legge da solo.
 */
const studio = "/projects/val-project/processes/val-process/simulation";
const FIXTURES = "e2e/fixtures/val-01";
const ACADEMIC = "tests/simulation/benchmark/g3/discovered/AcademicCredentials_diff/AcademicCredentials";
const json = (path: string) => JSON.parse(readFileSync(path, "utf8"));

// Risposte del backend vero (e2e/fixtures/val-01/generate.py).
const files = {
  academic: {
    xml: readFileSync(`${ACADEMIC}.bpmn`, "utf8"), file: readFileSync(`${ACADEMIC}.json`, "utf8"), name: "AcademicCredentials.json",
    template: json(`${FIXTURES}/academic.template.json`), refusal: json(`${FIXTURES}/academic.refusal.json`), accepted: null,
  },
  loop: {
    xml: readFileSync(`${FIXTURES}/loop.bpmn`, "utf8"), file: readFileSync(`${FIXTURES}/loop.json`, "utf8"), name: "pratiche.json",
    template: json(`${FIXTURES}/loop.template.json`), refusal: json(`${FIXTURES}/loop.refusal.json`), accepted: null,
  },
  fixed: {
    xml: readFileSync(`${FIXTURES}/loop.bpmn`, "utf8"), file: readFileSync(`${FIXTURES}/loop-fixed.json`, "utf8"), name: "pratiche.json",
    template: json(`${FIXTURES}/loop.template.json`), refusal: null, accepted: json(`${FIXTURES}/loop-fixed.import.json`),
  },
};
type Kind = keyof typeof files;

// Cio' che il consulente non deve leggere nel percorso ordinario.
const JARGON = /node[_-]|gateway|livelock|deadlock|gettoni|token|prosimos|json|bpmn/i;

const draft = { scenarioName: "Pratiche", totalCases: 50, arrivalIntervalMinutes: 30, defaultTaskMinutes: 15, resources: [], tasks: {}, gateways: {} };

type State = { importRequests: number; modelRuns: number };

async function fixture(page: Page, kind: Kind): Promise<State> {
  const state: State = { importRequests: 0, modelRuns: 0 };
  const { xml, template, refusal, accepted } = files[kind];
  await page.addInitScript((stored) => {
    Object.assign(window, { DELIR_API_BASE: "http://127.0.0.1:8000" });
    localStorage.setItem("delir-language", "it");
    if (!sessionStorage.getItem("seeded")) {
      localStorage.setItem("delir-sim-scenario:val-model", stored);
      sessionStorage.setItem("seeded", "1");
    }
  }, JSON.stringify(draft));
  await page.route("http://127.0.0.1:8000/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let data: unknown = [];
    if (path === "/v1/workspace/projects/val-project") data = {
      id: "val-project", client_id: "demo", client: "Azienda Demo", name: "Back office", phase: "AS-IS", status: "In corso", progress: 40, processes: 1,
      next_step: "Simulare le pratiche", milestones: [], open_issues: [], deliverables: [],
      process_items: [{ id: "val-process", project_id: "val-project", bpmn_model_id: "val-model", name: "Pratiche", stage: "AS-IS", status: "Da validare", owner: "Back office", readiness: 80 }],
    };
    else if (path.endsWith("/prosimos-import")) {
      state.importRequests += 1;
      if (refusal) return route.fulfill({ status: 400, json: refusal });
      data = accepted;
    }
    else if (path.endsWith("/simulation-model-runs")) state.modelRuns += 1;
    else if (path.endsWith("/simulation-template")) data = template;
    else if (path.endsWith("/simulation-provenance")) data = { has_discovery: false, elements: [] };
    else if (path.endsWith("/simulation-runs")) data = [];
    else if (path.endsWith("/val-model")) data = { id: "val-model", process_id: "val-process", name: "Pratiche", xml };
    await route.fulfill({ json: data });
  });
  return state;
}

async function upload(page: Page, kind: Kind): Promise<Locator> {
  await page.goto(`${studio}/scenario`);
  await page.getByRole("button", { name: "Origine parametri" }).click();
  await page.getByRole("button", { name: /Importa una configurazione/ }).click();
  const dialog = page.getByRole("dialog", { name: "Importa una configurazione" });
  await expect(dialog).toBeVisible();
  const { name, file } = files[kind];
  await dialog.getByLabel("Seleziona configurazione").setInputFiles({ name, mimeType: "application/json", buffer: Buffer.from(file) });
  return dialog;
}

/** Gate UX (DELIR_UX_SHOTS): la schermata com'e', poi l'elemento intero per leggerne ogni riga. */
async function shoot(page: Page, testInfo: TestInfo, name: string, element: Locator) {
  if (!process.env.DELIR_UX_SHOTS) return;
  const path = `${process.env.DELIR_UX_SHOTS}/${name}-${testInfo.project.name}`;
  if (page.viewportSize()!.width > 1199) await page.setViewportSize({ width: 1440, height: 900 });
  await page.screenshot({ path: `${path}.png` });
  await element.screenshot({ path: `${path}-panel.png` });
}

async function expectRefusal(dialog: Locator, kind: Kind, activity: string) {
  const alert = dialog.getByRole("alert");
  await expect(alert).toContainText("Il file non è stato applicato: alcuni casi non arriverebbero mai alla fine");
  await expect(alert).toContainText(`I casi che arrivano a «${activity}» non escono più da quel tratto`);
  await expect(alert).toContainText("ha probabilità 0");
  await expect(alert).toContainText("Cosa fare: dai a quella strada una probabilità maggiore di zero");
  await expect(alert).toContainText("Lo scenario non è cambiato");
  // Il percorso ordinario e' in parole del consulente; gli id stanno nel motivo tecnico, chiuso.
  // Il nome del file e' quello del consulente: si mostra com'e'.
  const ordinary = (await alert.innerText()).replace(/Mostra il motivo tecnico[\s\S]*$/, "").replace(files[kind].name, "");
  expect(ordinary).not.toMatch(JARGON);
  await expect(alert.locator("details")).not.toHaveAttribute("open", "");
  return alert;
}

test("the SIMOD scenario of AcademicCredentials with a loop that never exits is refused in plain words", async ({ page }, testInfo) => {
  const state = await fixture(page, "academic");
  const dialog = await upload(page, "academic");

  const alert = await expectRefusal(dialog, "academic", "Avanzar recepcion documentos");
  await shoot(page, testInfo, "academic-credentials-refused", alert);
  await alert.getByText("Mostra il motivo tecnico").click();
  await expect(alert).toContainText("node_59fc62b1-3b4e-4c11-ba7b-1cab3392cdaa");

  const axe = await new AxeBuilder({ page }).include('[role="dialog"]').withTags(["wcag2a", "wcag2aa"]).analyze();
  expect(axe.violations).toEqual([]);
  // Nessun pannello "simula così com'è": lo scenario non si simula.
  await expect(dialog.getByRole("button", { name: "Simula così com'è" })).toHaveCount(0);
  expect(state.importRequests).toBe(1);
  expect(state.modelRuns).toBe(0);
});

test("a file the editor can read on its own is checked too, and the scenario stays as it was", async ({ page }, testInfo) => {
  const state = await fixture(page, "loop");
  const dialog = await upload(page, "loop");

  const alert = await expectRefusal(dialog, "loop", "Controlla documenti");
  await expect(alert).toContainText("alla decisione «Documenti completi?»");
  await expect(alert).toContainText("verso «Archivia pratica»");
  await shoot(page, testInfo, "editor-file-refused", alert);
  expect(state.importRequests).toBe(1);

  const axe = await new AxeBuilder({ page }).include('[role="dialog"]').withTags(["wcag2a", "wcag2aa"]).analyze();
  expect(axe.violations).toEqual([]);

  // Lo scenario resta com'era: chiuso il dialogo, nessuna configurazione applicata.
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(page.getByText("Configurazione applicata")).toHaveCount(0);
});

test("the same file with the exit reopened is applied", async ({ page }) => {
  const state = await fixture(page, "fixed");
  const dialog = await upload(page, "fixed");

  await expect(dialog).toBeHidden();
  await expect(page.getByText("Configurazione applicata")).toBeVisible();
  expect(state.importRequests).toBe(1);
});
