import { expect, test, type Page, type Route } from "@playwright/test";

/**
 * Chiudere un incarico, riaprirlo, eliminarlo.
 *
 * Il backend e' finto ma tiene lo stato come quello vero: archiviare toglie il
 * cliente dall'elenco operativo e lo fa comparire in Archivio, ripristinare lo
 * riporta indietro, eliminare lo perde. Senza stato, i test non direbbero
 * niente sul fatto che le due liste siano davvero due facce dello stesso record.
 */

const API = "http://127.0.0.1:8000";

type ClientRow = {
  id: string;
  name: string;
  sector: string;
  status: string;
  projects: number;
  next_activity: string;
  owner: string;
  contact: string;
  processes: string[];
  documents: string[];
  archived_at: string | null;
  archive_reason: string | null;
};

function client(overrides: Partial<ClientRow> = {}): ClientRow {
  return {
    id: "esaote",
    name: "Esaote",
    sector: "Medicale",
    status: "Attivo",
    projects: 2,
    next_activity: "Validare l'AS-IS",
    owner: "Marco Bianchi",
    contact: "laura@esaote.example",
    processes: [],
    documents: [],
    archived_at: null,
    archive_reason: null,
    ...overrides,
  };
}

async function fixture(page: Page) {
  const state = { clients: [client()], deleted: [] as string[] };

  await page.addInitScript(() =>
    Object.assign(window, { DELIR_API_BASE: "http://127.0.0.1:8000" }),
  );

  await page.route(`${API}/**`, async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();

    if (path === "/v1/workspace/clients" && method === "GET") {
      return route.fulfill({
        json: state.clients.filter((row) => row.archived_at === null),
      });
    }

    if (path === "/v1/workspace/archive" && method === "GET") {
      return route.fulfill({
        json: {
          clients: state.clients.filter((row) => row.archived_at !== null),
          projects: [],
          processes: [],
        },
      });
    }

    const impact = path.match(/^\/v1\/workspace\/clients\/([^/]+)\/impact$/);
    if (impact && method === "GET") {
      return route.fulfill({
        json: {
          id: impact[1],
          name: "Esaote",
          projects: 2,
          processes: 3,
          sources: 4,
          decisions: 1,
        },
      });
    }

    const archive = path.match(/^\/v1\/workspace\/clients\/([^/]+)\/archive$/);
    if (archive && method === "POST") {
      const body = request.postDataJSON() as { reason: string | null };
      const row = state.clients.find((item) => item.id === archive[1])!;
      row.archived_at = "2026-09-07T10:00:00Z";
      row.archive_reason = body.reason;
      return route.fulfill({ json: row });
    }

    const restore = path.match(/^\/v1\/workspace\/clients\/([^/]+)\/restore$/);
    if (restore && method === "POST") {
      const row = state.clients.find((item) => item.id === restore[1])!;
      row.archived_at = null;
      row.archive_reason = null;
      return route.fulfill({ json: row });
    }

    const remove = path.match(/^\/v1\/workspace\/clients\/([^/]+)$/);
    if (remove && method === "DELETE") {
      state.clients = state.clients.filter((item) => item.id !== remove[1]);
      state.deleted.push(remove[1]);
      return route.fulfill({
        json: {
          id: remove[1],
          name: "Esaote",
          projects: 2,
          processes: 3,
          sources: 4,
          decisions: 1,
        },
      });
    }

    if (path === "/v1/workspace/projects") return route.fulfill({ json: [] });

    return route.fulfill({ status: 200, json: null });
  });

  return state;
}

async function openRowMenu(page: Page, name: string) {
  await page.getByRole("button", { name: `Altre azioni: ${name}` }).click();
}

test("il consulente chiude un cliente e lo ritrova in Archivio", async ({ page }) => {
  await fixture(page);

  await page.goto("/clients");
  await expect(page.getByRole("cell", { name: "Esaote" }).first()).toBeVisible();

  await openRowMenu(page, "Esaote");
  await page.getByRole("menuitem", { name: "Archivia" }).click();

  // La conferma dice cosa coinvolge, contato dal backend.
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("Cosa coinvolge")).toBeVisible();
  await expect(dialog.getByText("Progetti")).toBeVisible();
  await expect(dialog.getByText("2", { exact: true })).toBeVisible();

  await dialog
    .getByRole("textbox", { name: /motivo della chiusura/i })
    .fill("Incarico concluso a giugno");
  await dialog.getByRole("button", { name: "Archivia", exact: true }).click();

  await expect(dialog).toBeHidden();
  await expect(page.getByRole("cell", { name: "Esaote" })).toHaveCount(0);

  await page.getByRole("button", { name: "Archivio" }).click();
  await expect(page.getByText("Esaote")).toBeVisible();
  await expect(page.getByText("Incarico concluso a giugno")).toBeVisible();
});

test("un cliente archiviato si riapre dall'Archivio", async ({ page }) => {
  const state = await fixture(page);
  state.clients[0].archived_at = "2026-09-07T10:00:00Z";
  state.clients[0].archive_reason = "Incarico concluso";

  await page.goto("/archive");
  await expect(page.getByText("Esaote")).toBeVisible();

  await page.getByRole("button", { name: "Ripristina" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "Ripristina", exact: true }).click();

  await expect(dialog).toBeHidden();
  await page.getByRole("button", { name: "Clienti" }).click();
  await expect(page.getByRole("cell", { name: "Esaote" }).first()).toBeVisible();
});

test("eliminare chiede di scrivere il nome, e senza quello non elimina", async ({
  page,
}) => {
  const state = await fixture(page);

  await page.goto("/clients");
  await openRowMenu(page, "Esaote");
  await page.getByRole("menuitem", { name: "Elimina" }).click();

  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText(/non si può annullare/i)).toBeVisible();

  // Nome sbagliato: niente viene eliminato.
  await dialog.getByRole("textbox", { name: /scrivi/i }).fill("Esaot");
  await dialog.getByRole("button", { name: "Elimina definitivamente" }).click();
  await expect(dialog.getByText(/il nome non corrisponde/i)).toBeVisible();
  expect(state.deleted).toEqual([]);

  await dialog.getByRole("textbox", { name: /scrivi/i }).fill("Esaote");
  await dialog.getByRole("button", { name: "Elimina definitivamente" }).click();

  await expect(dialog).toBeHidden();
  expect(state.deleted).toEqual(["esaote"]);
  await expect(page.getByRole("cell", { name: "Esaote" })).toHaveCount(0);
});
