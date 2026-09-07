import { expect, test, type Page, type Route } from "@playwright/test";

/**
 * Il turno della Consulting Chat, dal punto di vista del consulente.
 *
 * Il backend qui e' finto ma parla il protocollo vero (NDJSON, un evento per
 * riga), e viene rilasciato a pezzi: senza questo, uno stream che arriva tutto
 * insieme non direbbe niente su quello che il consulente vede *mentre* aspetta,
 * che e' esattamente cio' che questi test verificano.
 */

const API = "http://127.0.0.1:8000";
const THREAD = "thread-e2e";

type StreamStep = { wait?: number; line?: Record<string, unknown> };

function ndjson(steps: StreamStep[]): string {
  return steps
    .filter((step) => step.line)
    .map((step) => `${JSON.stringify(step.line)}\n`)
    .join("");
}

async function fixture(
  page: Page,
  options: { steps: StreamStep[]; onStream?: (body: unknown) => void } = {
    steps: [],
  },
) {
  await page.addInitScript(() =>
    Object.assign(window, { DELIR_API_BASE: "http://127.0.0.1:8000" }),
  );

  // Il finto backend ricorda il trascritto, come quello vero: senza questo,
  // ricaricare la sessione dopo un turno riuscito lo mostrerebbe vuoto e i test
  // proverebbero il contrario di quello che devono provare.
  const transcript: { role: string; content: string }[] = [];

  await page.route(`${API}/**`, async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;

    if (path === "/v1/consultant-chat/sessions" && request.method() === "GET") {
      return route.fulfill({ json: [] });
    }
    if (path === "/v1/consultant-chat/sessions" && request.method() === "POST") {
      return route.fulfill({
        json: {
          thread_id: THREAD,
          model_name: "gpt-5.6-luna",
          title: "Nuova chat",
          scope_type: "consultant",
          project_id: null,
          process_id: null,
          bpmn_model_id: null,
          scope_key: "consultant",
        },
      });
    }
    if (path.endsWith("/messages/stream")) {
      const body = request.postDataJSON() as { message: string };
      options.onStream?.(body);
      transcript.push({ role: "user", content: body.message });
      const answer = options.steps
        .map((step) => step.line)
        .filter((line) => line && line.type === "done")
        .map((line) => String((line as { message?: string }).message ?? ""))
        .at(-1);
      if (answer) transcript.push({ role: "assistant", content: answer });
      // Le pause vivono qui: il body arriva gia' completo al browser, ma il
      // ritardo prima della risposta tiene il turno "in corso" abbastanza a
      // lungo da poterci interagire.
      const totalWait = options.steps.reduce(
        (sum, step) => sum + (step.wait ?? 0),
        0,
      );
      if (totalWait > 0) {
        await new Promise((resolve) => setTimeout(resolve, totalWait));
      }
      return route.fulfill({
        status: 200,
        contentType: "application/x-ndjson",
        body: ndjson(options.steps),
      });
    }
    if (path.startsWith("/v1/consultant-chat/sessions/")) {
      return route.fulfill({
        json: {
          thread_id: THREAD,
          title: "Nuova chat",
          model_name: "gpt-5.6-luna",
          messages: transcript,
        },
      });
    }

    return route.fulfill({ status: 200, json: null });
  });
}

async function ask(page: Page, text: string) {
  const composer = page.getByRole("textbox", { name: /scrivi un messaggio/i });
  await composer.fill(text);
  await composer.press("Enter");
}

test("il consulente vede le fasi del lavoro, una per volta e con il tempo", async ({
  page,
}) => {
  await fixture(page, {
    steps: [
      { wait: 300 },
      {
        line: {
          type: "activity",
          message: "Leggo la richiesta",
          payload: { phase: "understanding", label: "Leggo la richiesta", icon: "brain" },
        },
      },
      {
        line: {
          type: "activity",
          message: "Leggo le fonti raccolte",
          payload: {
            phase: "reading_sources",
            label: "Leggo le fonti raccolte",
            detail: "Intervista Laura",
            icon: "document",
          },
        },
      },
      { line: { type: "delta", content: "Dalle interviste risultano tre snodi." } },
      { line: { type: "done", message: "Dalle interviste risultano tre snodi." } },
    ],
  });

  await page.goto("/consultant");
  await ask(page, "Cosa emerge dalle interviste?");

  const progress = page.getByLabel("Avanzamento del lavoro");
  await expect(progress).toBeVisible();
  await expect(progress.getByText("Leggo la richiesta")).toBeVisible();
  await expect(progress.getByText("Leggo le fonti raccolte")).toBeVisible();
  // Il dettaglio e' un nome di dominio, non un identificativo.
  await expect(progress.getByText("Intervista Laura")).toBeVisible();
  // Una riga per fase: niente frasi ripetute.
  await expect(progress.getByText("Leggo la richiesta")).toHaveCount(1);
  // Ogni riga porta quanto e' durata.
  await expect(progress.getByText(/^\d+s$/).first()).toBeVisible();

  await expect(
    page.getByText("Dalle interviste risultano tre snodi."),
  ).toBeVisible();
});

test("nessun nome interno finisce sotto gli occhi del consulente", async ({
  page,
}) => {
  await fixture(page, {
    steps: [
      { wait: 200 },
      {
        line: {
          type: "node",
          node: "canvas_layout_consultant_agent",
          payload: { event_type: "node" },
        },
      },
      {
        line: {
          type: "activity",
          message: "Disegno il diagramma",
          payload: { phase: "drawing", label: "Disegno il diagramma", icon: "draw" },
        },
      },
      { line: { type: "delta", content: "Fatto." } },
      { line: { type: "done", message: "Fatto." } },
    ],
  });

  await page.goto("/consultant");
  await ask(page, "aggiorna il canvas");

  await expect(page.getByText("Fatto.")).toBeVisible();
  const body = (await page.locator("main, .shell").first().innerText()).toLowerCase();
  for (const leak of ["canvas_layout", "subgraph", "langgraph", "_agent"]) {
    expect(body).not.toContain(leak);
  }
});

test("cambiare pagina non azzera il turno in corso", async ({ page }) => {
  await fixture(page, {
    steps: [
      { wait: 1500 },
      { line: { type: "delta", content: "Risposta arrivata dopo il cambio pagina." } },
      { line: { type: "done", message: "Risposta arrivata dopo il cambio pagina." } },
    ],
  });

  await page.goto("/consultant");
  await ask(page, "Prepara il brief");

  // Via mentre l'agente lavora, e ritorno — dentro l'app, come farebbe un
  // consulente che va a controllare un progetto mentre aspetta.
  await page.getByRole("button", { name: "Progetti" }).click();
  await expect(page).toHaveURL(/\/projects/);
  await page.getByRole("button", { name: "Consulente" }).click();
  await expect(page).toHaveURL(/\/consultant/);

  await expect(
    page.getByText("Risposta arrivata dopo il cambio pagina."),
  ).toBeVisible({ timeout: 15_000 });
});

test("il turno si puo' fermare e la parte gia' scritta resta", async ({
  page,
}) => {
  await fixture(page, {
    steps: [
      { wait: 6_000 },
      { line: { type: "delta", content: "Non deve mai arrivare." } },
    ],
  });

  await page.goto("/consultant");
  await ask(page, "Scrivi un documento lungo");

  const stop = page.getByRole("button", { name: "Ferma" });
  await expect(stop).toBeVisible();
  await stop.click();

  await expect(stop).toBeHidden();
  await expect(page.getByText("Non deve mai arrivare.")).toHaveCount(0);
  // La riga di composizione torna disponibile senza ricaricare la pagina.
  await expect(
    page.getByRole("button", { name: "Invia", exact: true }),
  ).toBeVisible();
});

test("si puo' scrivere mentre l'agente lavora: il messaggio si accoda", async ({
  page,
}) => {
  const sent: string[] = [];
  await fixture(page, {
    steps: [
      { wait: 1_200 },
      { line: { type: "delta", content: "Prima risposta." } },
      { line: { type: "done", message: "Prima risposta." } },
    ],
    onStream: (body) => sent.push((body as { message: string }).message),
  });

  await page.goto("/consultant");
  await ask(page, "Prima domanda");

  const composer = page.getByRole("textbox", { name: /scrivi un messaggio/i });
  await expect(composer).toBeEnabled();
  await composer.fill("Aggiungo un dettaglio");
  await composer.press("Enter");

  const queue = page.getByLabel("Messaggi in coda");
  await expect(queue).toBeVisible();
  await expect(queue.getByText("Aggiungo un dettaglio")).toBeVisible();

  // Chiuso il primo turno, la coda parte da sola.
  await expect.poll(() => sent, { timeout: 20_000 }).toEqual([
    "Prima domanda",
    "Aggiungo un dettaglio",
  ]);
  await expect(queue).toBeHidden();
});
