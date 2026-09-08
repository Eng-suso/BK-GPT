import { expect, test, type Page, type Route } from "@playwright/test";

/**
 * Dalla discussione al piano, dal punto di vista del consulente.
 *
 * Il backend e' finto ma tiene lo stato come quello vero: le interviste
 * raccolte in chat diventano le voci del registro, il piano si prepara su
 * quelle voci, e la risposta a una domanda del piano resta scritta. Senza
 * stato, questi test non direbbero niente sul fatto che le due cose siano lo
 * stesso processo visto da due punti.
 *
 * Idempotenti per costruzione: lo stato nasce e muore dentro `fixture`, ogni
 * test riparte dal registro che dichiara, nessuno stream dipende dal
 * precedente e non ci sono screenshot da riconciliare. Eseguirli due volte,
 * in qualsiasi ordine, da' lo stesso esito.
 */

const API = "http://127.0.0.1:8000";
const PROJECT = "p1";
const PROCESS = "pr1";
const MODEL = "bpmn-1";
const THREAD = "thread-process-e2e";

/** La contraddizione che le tre interviste hanno davvero prodotto. */
const GROUNDED_QUESTION =
  "Paolo dice che per importi piccoli l'approvazione può non essere formalizzata, " +
  "Francesca dice che l'autorizzazione è sempre richiesta: quale descrive il processo effettivo?";

type ReviewQuestion = {
  question_id: string;
  question: string;
  severity: string;
  options: { label: string; implication?: string }[];
  answer: string | null;
  answered_at?: string | null;
};

type Review = {
  bpmn_model_id: string;
  process_id: string;
  version: number;
  source_text: string;
  bpmn_brief: string;
  readiness_score: number;
  missing_information: string[];
  open_questions: ReviewQuestion[];
  process_understanding: {
    title: string;
    actors: { id: string; label: string; kind: string }[];
    unknowns: { question: string; severity: string }[];
  };
  bpmn_semantic_model: {
    lanes: { id: string; name: string }[];
    flowNodes: { id: string; type: string; name: string }[];
    sequenceFlows: { id: string; sourceRef: string; targetRef: string }[];
  };
  quality_report: { approval_recommendation: string };
  status: string;
  created_at: string;
  updated_at: string;
};

/**
 * Il piano che il backend consegna quando le tre interviste sono agli atti.
 *
 * Porta gli attori e le corsie che le fonti hanno nominato - e' il contrario
 * esatto del "zero attori, zero lane" che aveva fermato la V2 - e una sola
 * domanda, quella che nasce dalla contraddizione registrata.
 */
function reviewFromInterviews(): Review {
  return {
    bpmn_model_id: MODEL,
    process_id: PROCESS,
    version: 1,
    source_text:
      "Francesca Neri: Acquisti crea e invia l'ordine al fornitore. " +
      "Paolo Ricci: per importi piccoli l'approvazione può non essere formalizzata. " +
      "Marco Villa: per le urgenze il reparto contatta direttamente il fornitore.",
    bpmn_brief:
      "## Ciclo passivo\n\nAcquisti crea e invia l'ordine al fornitore. " +
      "Sulle approvazioni le fonti divergono.",
    readiness_score: 6,
    missing_information: ["Chi autorizza l'ordine retroattivo dopo un'urgenza"],
    open_questions: [
      {
        question_id: "approvazione-importi-piccoli",
        question: GROUNDED_QUESTION,
        severity: "blocking",
        options: [
          {
            label: "L'autorizzazione è sempre richiesta",
            implication: "Il passaggio di approvazione resta sul percorso principale",
          },
          {
            label: "Sotto soglia si procede senza formalizzare",
            implication: "Nasce un percorso alternativo per gli importi piccoli",
          },
        ],
        answer: null,
      },
    ],
    process_understanding: {
      title: "Ciclo passivo",
      actors: [
        { id: "acquisti", label: "Acquisti", kind: "team" },
        { id: "produzione", label: "Produzione", kind: "team" },
        { id: "fornitore", label: "Fornitore", kind: "external_party" },
      ],
      unknowns: [{ question: GROUNDED_QUESTION, severity: "blocking" }],
    },
    bpmn_semantic_model: {
      lanes: [
        { id: "lane_acquisti", name: "Acquisti" },
        { id: "lane_produzione", name: "Produzione" },
      ],
      flowNodes: [
        { id: "start", type: "startEvent", name: "Fabbisogno rilevato" },
        { id: "crea_ordine", type: "userTask", name: "Crea e invia l'ordine" },
        { id: "end", type: "endEvent", name: "Ordine inviato" },
      ],
      sequenceFlows: [
        { id: "f1", sourceRef: "start", targetRef: "crea_ordine" },
        { id: "f2", sourceRef: "crea_ordine", targetRef: "end" },
      ],
    },
    quality_report: { approval_recommendation: "needs_user_clarification" },
    status: "pending",
    created_at: "2026-09-08T09:00:00Z",
    updated_at: "2026-09-08T09:00:00Z",
  };
}

type StreamLine = Record<string, unknown>;

type FixtureOptions = {
  /** Il piano gia' preparato su questo processo, o `null` se non c'e' ancora. */
  review?: Review | null;
  /** Cosa risponde il turno successivo. */
  turn?: StreamLine[];
};

async function fixture(page: Page, options: FixtureOptions = {}) {
  const state = {
    review: options.review === undefined ? reviewFromInterviews() : options.review,
    transcript: [] as { role: string; content: string }[],
    answered: [] as { question: string; answer: string }[],
  };

  await page.addInitScript(() =>
    Object.assign(window, { DELIR_API_BASE: "http://127.0.0.1:8000" }),
  );

  await page.route(`${API}/**`, async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();

    if (path === `/v1/workspace/projects/${PROJECT}` && method === "GET") {
      return route.fulfill({
        json: {
          id: PROJECT,
          client_id: "esaote",
          client: "Esaote",
          name: "Mappatura ciclo passivo",
          objective: "Mappare l'AS-IS del ciclo passivo",
          lead: "Marco Bianchi",
          start_date: null,
          end_date: null,
          phase: "Discovery",
          status: "In corso",
          progress: 40,
          processes: 1,
          next_step: "Chiudere le interviste",
          milestones: [],
          open_issues: [],
          deliverables: [],
          archived_at: null,
          archive_reason: null,
          process_items: [
            {
              id: PROCESS,
              project_id: PROJECT,
              bpmn_model_id: MODEL,
              name: "Ciclo passivo",
              stage: "AS-IS",
              status: "In corso",
              owner: "Francesca Neri",
              readiness: 6,
              archived_at: null,
              archive_reason: null,
            },
          ],
        },
      });
    }

    if (path === "/v1/consultant-chat/sessions" && method === "GET") {
      return route.fulfill({ json: [] });
    }
    if (path === "/v1/consultant-chat/sessions" && method === "POST") {
      return route.fulfill({
        json: {
          thread_id: THREAD,
          model_name: "gpt-5.6-luna",
          title: "Discussione processo",
          scope_type: "process",
          project_id: PROJECT,
          process_id: PROCESS,
          bpmn_model_id: null,
          scope_key: `process:${PROJECT}:${PROCESS}`,
        },
      });
    }
    if (path.endsWith("/messages/stream")) {
      const body = request.postDataJSON() as { message: string };
      state.transcript.push({ role: "user", content: body.message });
      const lines = options.turn ?? [
        { type: "delta", content: "Registrato." },
        { type: "done", message: "Registrato." },
      ];
      const answer = lines
        .filter((line) => line.type === "done")
        .map((line) => String(line.message ?? ""))
        .at(-1);
      if (answer) state.transcript.push({ role: "assistant", content: answer });
      return route.fulfill({
        status: 200,
        contentType: "application/x-ndjson",
        body: lines.map((line) => `${JSON.stringify(line)}\n`).join(""),
      });
    }
    if (path.startsWith("/v1/consultant-chat/sessions/")) {
      return route.fulfill({
        json: {
          thread_id: THREAD,
          title: "Discussione processo",
          model_name: "gpt-5.6-luna",
          messages: state.transcript,
        },
      });
    }

    if (path === `/v1/workspace/bpmn-models/${MODEL}/review` && method === "GET") {
      return route.fulfill({ json: state.review });
    }
    if (path === `/v1/workspace/bpmn-models/${MODEL}/review/versions`) {
      return route.fulfill({ json: [] });
    }
    if (path === `/v1/workspace/bpmn-models/${MODEL}/review/answers` && method === "POST") {
      const body = request.postDataJSON() as { question: string; answer: string };
      state.answered.push(body);
      if (state.review) {
        // Come il backend vero: la risposta entra nel piano e la domanda smette
        // di essere aperta. Il piano che torna e' quello aggiornato.
        state.review = {
          ...state.review,
          version: state.review.version + 1,
          updated_at: "2026-09-08T09:05:00Z",
          open_questions: state.review.open_questions.map((item) =>
            item.question === body.question
              ? { ...item, answer: body.answer, answered_at: "2026-09-08T09:05:00Z" }
              : item,
          ),
        };
      }
      return route.fulfill({ json: state.review });
    }

    return route.fulfill({ status: 200, json: null });
  });

  return state;
}

/**
 * Apre la discussione del processo.
 *
 * Un piano appena arrivato apre la sua review a tutto schermo: e' voluto, ma
 * qui copre la chat e duplica le domande (la scheda le mostra anche dentro).
 * Chiuderla e' cio' che fa un consulente prima di scrivere, quindi lo fa anche
 * il test - a meno che sia proprio la scheda l'oggetto della verifica.
 */
async function openProcessDiscussion(
  page: Page,
  options: { keepReviewOpen?: boolean } = {},
) {
  await page.goto(`/projects/${PROJECT}/processes/${PROCESS}`);
  await expect(page.getByLabel("Chat processo")).toBeVisible();

  // La scheda si apre da sola quando il piano arriva, quindi si aspetta che sia
  // arrivato: chiudere prima e' una gara che il test perde a intermittenza.
  const sheet = page.getByRole("dialog");
  await expect(sheet).toBeVisible();
  if (options.keepReviewOpen) return;

  await sheet.getByRole("button", { name: "Chiudi review" }).click();
  await expect(sheet).toHaveCount(0);
}

async function ask(page: Page, text: string) {
  const composer = page.getByPlaceholder(/scrivi un messaggio/i);
  await composer.fill(text);
  await composer.press("Enter");
}

test("il piano porta quello che le interviste hanno detto, non il solo titolo", async ({
  page,
}) => {
  // PROCESS-V2-11: dopo tre interviste il piano dichiarava di conoscere
  // "esclusivamente il titolo del processo", con zero attori e zero corsie.
  await fixture(page);
  await openProcessDiscussion(page, { keepReviewOpen: true });

  const sheet = page.getByRole("dialog");
  // Il colpo d'occhio del piano: quante persone e quante corsie ha capito.
  await expect(sheet).toContainText("Attori coinvolti");
  await expect(sheet).not.toContainText("0Attori coinvolti");
  await expect(sheet).not.toContainText("0Lane da disegnare");

  await sheet.getByRole("button", { name: /Come lo disegno/ }).click();
  for (const actor of ["Acquisti", "Produzione", "Fornitore"]) {
    await expect(sheet).toContainText(actor);
  }
});

test("la discussione e il piano raccontano lo stesso processo", async ({ page }) => {
  // PROCESS-V2-13: le domande del piano vivevano nella sola scheda del canvas,
  // e la conversazione che le aveva generate non le vedeva.
  await fixture(page);
  await openProcessDiscussion(page);

  await expect(page.getByLabel("Domande aperte sul piano")).toBeVisible();
  await expect(page.getByText(GROUNDED_QUESTION)).toBeVisible();
});

test("la domanda cita la contraddizione che l'ha generata", async ({ page }) => {
  // PROCESS-V2-15: le domande bloccanti proponevano sourcing, budget,
  // conformita' e soglie - temi di settore che nessuna fonte aveva nominato.
  await fixture(page);
  await openProcessDiscussion(page);

  const asked = page.getByLabel("Domande aperte sul piano");
  await expect(asked).toContainText("Paolo");
  await expect(asked).toContainText("Francesca");

  const text = (await asked.innerText()).toLowerCase();
  for (const template of ["sourcing", "verifica budget", "conformità"]) {
    expect(text).not.toContain(template);
  }
});

test("le alternative sono numerate in ordine e l'ultima è sempre Altro", async ({
  page,
}) => {
  await fixture(page);
  await openProcessDiscussion(page);

  const asked = page.getByLabel("Domande aperte sul piano");
  const choices = await asked.getByRole("button").allInnerTexts();

  expect(choices[0].replace(/\s+/g, " ")).toMatch(/^1 L'autorizzazione è sempre richiesta/);
  expect(choices[1].replace(/\s+/g, " ")).toMatch(/^2 Sotto soglia/);
  expect(choices.at(-1)?.replace(/\s+/g, " ")).toMatch(/^3 Altro/);
});

test("il consulente può rispondere con parole sue, e la risposta resta scritta", async ({
  page,
}) => {
  const state = await fixture(page);
  await openProcessDiscussion(page);

  const asked = page.getByLabel("Domande aperte sul piano");
  await asked.getByRole("button", { name: /Altro/ }).click();
  await asked.getByRole("textbox").fill("Dipende dalla categoria merceologica");
  await asked.getByRole("button", { name: /^Rispondi$/ }).click();

  // Registrata dove conta: nel piano, non solo sullo schermo.
  await expect
    .poll(() => state.answered)
    .toEqual([
      { question: GROUNDED_QUESTION, answer: "Dipende dalla categoria merceologica" },
    ]);
  // E una domanda decisa non torna a chiedere.
  await expect(page.getByLabel("Domande aperte sul piano")).toHaveCount(0);
});

test("una risposta già data non riappare quando si riapre il processo", async ({
  page,
}) => {
  // L'idempotenza vista dal consulente: riaprire non riporta indietro il lavoro.
  const answered = reviewFromInterviews();
  answered.open_questions[0].answer = "L'autorizzazione è sempre richiesta";
  await fixture(page, { review: answered });

  await openProcessDiscussion(page);

  await expect(page.getByLabel("Piano BPMN pronto")).toBeVisible();
  await expect(page.getByLabel("Domande aperte sul piano")).toHaveCount(0);
});

test("un turno che non chiude non viene raccontato come backend spento", async ({
  page,
}) => {
  // PROCESS-V2-14: il lock del thread di checkpoint faceva comparire "backend
  // scollegato", e il consulente andava a cercare un server spento mentre il
  // problema era il giro di lavoro precedente ancora in corso.
  await fixture(page, {
    turn: [
      {
        type: "error",
        error: {
          code: "agent_thread_busy",
          message:
            "Il turno precedente di questa conversazione sta ancora lavorando. " +
            "Aspetta che finisca e reinvia: il backend risponde.",
          retryable: true,
        },
      },
    ],
  });
  await openProcessDiscussion(page);
  await ask(page, "prepara il piano");

  // Il motivo vero compare due volte, e va bene: nel filo della conversazione
  // e nell'avviso in testa. Quello che non deve comparire e' un backend spento.
  const notice = page.getByRole("alert");
  await expect(notice).toContainText(/il turno precedente di questa conversazione/i);

  const shell = page.getByLabel("Chat processo");
  const text = (await shell.innerText()).toLowerCase();
  for (const misleading of ["backend non raggiungibile", "scollegat", "offline"]) {
    expect(text).not.toContain(misleading);
  }
});

test("un turno fallito non fa passare per fresco il piano di prima", async ({
  page,
}) => {
  // Lo stato incoerente: la pagina sembrava contemporaneamente fallita e pronta.
  await fixture(page, {
    turn: [
      {
        type: "error",
        error: {
          code: "agent_thread_busy",
          message: "Il turno precedente di questa conversazione sta ancora lavorando.",
          retryable: true,
        },
      },
    ],
  });
  await openProcessDiscussion(page);

  await expect(page.getByLabel("Piano BPMN pronto")).toBeVisible();
  await ask(page, "prepara il piano");

  const stale = page.getByLabel("Piano BPMN dell'ultimo giro riuscito");
  await expect(stale).toBeVisible();
  await expect(stale).toContainText("non è arrivata in fondo");
  await expect(page.getByLabel("Piano BPMN pronto")).toHaveCount(0);
});
