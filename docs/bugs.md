# Bug log

Un bug per sezione, con la frase che lo ha prodotto. Lo stato dice se la
regressione e' coperta da un test, non se "sembra a posto".

## CLIENT-01 — Status cliente non inferito dal linguaggio

- **Severity**: P2
- **Stato**: risolto (2026-09-06) — coperto da `tests/test_client_status.py`
- **Input**: "Ho acquisito un nuovo cliente: Esaote S.p.A."
- **Expected**: cliente registrato con uno stato coerente con "acquisito" (`Attivo`).
- **Actual**: `Prospect`. L'agente rispondeva "Ho acquisito un nuovo cliente" mentre
  scriveva a database il contrario: un prospect e' qualcuno che stai *ancora*
  cercando di acquisire.
- **Causa**: `status="Prospect"` era il default hard-coded di ogni punto di
  ingresso — `ClientRecordInput`, `InitialWorkspaceSetupInput`,
  `CreateClientRequest`, `create_client`, piu' le istruzioni in
  `how_to_act.md`. Il modello non aveva una scelta da fare: il campo era gia'
  risposto.

### Fix

`backend/workspace_defaults.py` raccoglie il vocabolario degli stati e il
significato di "non lo so":

- ogni punto di ingresso ha default `None` = "non dichiarato";
- il tool schema espone `Literal["Attivo", "Da seguire", "Prospect"]` con una
  descrizione che dice *quando* valorizzarlo, quindi il modello sceglie;
- il placeholder (`Prospect`) si applica una volta sola, al confine col
  database, e significa solo "nessuno lo ha deciso";
- `create_client` resta idempotente per nome e riempie i soli campi rimasti al
  placeholder: una create ripetuta non duplica e non butta via l'informazione
  arrivata dopo, ma non sovrascrive un valore gia' deciso (cambiarlo e' un
  update, e `create_client` non lo e').

### Verifica

`tests/test_client_status.py` copre vocabolario, contratto dei quattro punti di
ingresso (il default hard-coded non puo' tornare) e comportamento reale su
Postgres, idempotenza inclusa.

Controllo con modello reale, fuori CI (`gpt-4.1-mini`, tool `manage_client_record`):

| frase | `status` scelto |
| --- | --- |
| "Ho acquisito un nuovo cliente: Esaote S.p.A." | `Attivo` |
| "Sto cercando di acquisire Barilla, per ora e' solo un contatto." | `Prospect` |
| "Aggiungi Ferrari come cliente." | non valorizzato → placeholder `Prospect` |

L'ultima riga resta un caso limite noto: "come cliente" e' debole, il modello
non se la sente e lascia decidere al placeholder. Accettabile finche' il
placeholder significa "sconosciuto"; se dovesse diventare fastidioso, la leva e'
la descrizione del campo, non un default nuovo.

## PROJECT-01 — L'obiettivo dell'incarico non era un campo del progetto

- **Severity**: P1
- **Stato**: risolto (2026-09-07) — coperto da `tests/test_project_record.py` e
  `frontend/src/features/projects/components/ProjectFormDialog.test.tsx`
- **Input**: "Ricostruire l'AS-IS, validarlo con gli stakeholder, simularlo e
  misurare i KPI."
- **Expected**: il record di progetto conserva il brief dell'incarico.
- **Actual**: il progetto nasceva con nome, fase, stato, avanzamento, prossimo
  passo, milestone, issue e deliverable. L'obiettivo restava nella chat history:
  entrando nella Project Chat il giorno dopo, DeliR conosceva il contenitore ma
  non il mandato.
- **Causa**: `WorkspaceProject` non aveva un campo per il perche'. Non era una
  perdita di informazione dell'agente: non c'era il posto dove scriverla.

### Fix

- `objective` e' una colonna del progetto (migration `0004_project_objective`),
  esposta da `ProjectResponse`, dal tool e dalla PATCH HTTP;
- non ha placeholder: una frase inventata al posto del consulente sarebbe
  peggio di un campo vuoto. Quando manca, la `create` avvisa l'agente e lo scope
  prompt della Project Chat lo dice, indicando `update_workspace_project`;
- fase e stato smettono di essere stringhe libere con un default per punto di
  ingresso: `workspace_defaults.py` tiene i due vocabolari **con la definizione
  di ogni voce**, che il modello legge nello schema del tool e il consulente
  legge nel form.

### Il consulente non dipende dall'agente

Stessa origine, difetto gemello: clienti, progetti e processi si potevano
creare e modificare solo dalla chat. Ora esistono `PATCH
/v1/workspace/clients/{id}`, `PATCH /v1/workspace/projects/{id}` e `PATCH
/v1/workspace/processes/{id}` (patch parziale: un campo non dichiarato non si
tocca, una lista dichiarata sostituisce quella corrente) e la PWA ha i form:
nuovo/modifica cliente dall'anagrafica, nuovo/modifica progetto dal portafoglio
e dal dettaglio con l'obiettivo in cima alla panoramica, nuovo/modifica
processo dalla tab Processi. Anche il processo ha i suoi due vocabolari
definiti: lo stadio dice *quale* processo si sta descrivendo, lo stato a che
punto e' quella descrizione. L'agente resta autonomo — stesso record, stessi
vocabolari, `update_workspace_project` e `update_workspace_process` fra i suoi
tool — ma non e' piu' l'unica strada.

Ogni salvataggio lo conferma un toast (il `<Toaster />` non era montato da
nessuna parte: `toast.success` non sarebbe comparso).

### Verifica

`tests/test_project_record.py` copre vocabolari (progetto e processo),
contratto dei punti di ingresso, persistenza dell'obiettivo, il prompt della
Project Chat (con e senza obiettivo), la semantica della patch parziale e le
tre PATCH su HTTP. `ProjectFormDialog.test.tsx` e `ProcessFormDialog.test.tsx`
coprono i form: campi precompilati dal record, salvataggio che scrive davvero,
e creazione rifiutata senza cliente o senza nome.

Verifica visiva con Playwright (desktop 1280 e mobile), che ha trovato tre
difetti poi corretti: il corpo del dialog non scrollava (il `DialogContent` e'
una griglia, il form sfondava il `max-h` e il footer usciva dallo schermo); il
trigger dei select stampava anche la definizione della voce, sfondando il
controllo; e il `<Toaster />` montato dentro la griglia della shell prendeva
una riga implicita, schiacciando di 125px sidebar e contenuto.

## PROJECT-02 — Readiness di processo su un progetto senza processi

- **Severity**: P2
- **Stato**: risolto (2026-09-07) — coperto da `tests/test_project_chat_boundaries.py`
- **Input**: "Elenca i processi in scope e la loro readiness."
- **Expected**: "Nessun processo registrato; readiness non valutabile. Prossimo
  passo: definire i processi in scope."
- **Actual**: quello, piu' un elenco di lacune interne di un processo che non
  esiste.
- **Causa**: niente diceva alla Project Chat cosa significa `process_count = 0`.
  Lo snapshot del progetto arrivava nel prompt come una lista vuota, che il
  modello leggeva come "non lo so ancora" invece di "non c'e' niente da
  valutare", e la capability `project.process_coordination` non aveva
  prerequisiti: coordinare zero processi era una route autorizzata.

## PROJECT-03 — Il progetto non poteva creare i propri processi

- **Severity**: P0 sul flusso di chat
- **Stato**: risolto (2026-09-07) — coperto da `tests/test_project_chat_boundaries.py`
- **Input**: "crea questo processo nel progetto"
- **Expected**: il `WorkspaceProcess` viene registrato, senza iniziare la
  discovery.
- **Actual**: il Project Macro non aveva il tool e tentava un handoff al Process
  Macro, che pero' pretende un `process_id` esistente. Vicolo cieco: la frase
  "la richiesta e' stata preparata per il Process Macro" descriveva un lavoro
  di process discovery che non era ancora cominciato.
- **Causa**: `tools_by_scope["project"] = project_tools`, e `project_tools` non
  esponeva nessuna capacita' di creazione. L'elenco dei processi e' pero' un
  record *di progetto*: crearlo e' workspace setup, non discovery.

## PROJECT-04 — Riferimento perso al turno dopo

- **Severity**: P1 alto
- **Stato**: risolto (2026-09-07) — coperto da `tests/test_project_chat_boundaries.py`
- **Input**: nome, perimetro e tipologia del processo dichiarati dal consulente
  e *riformulati da DeliR stesso*; poi "aggiungi il processo".
- **Expected**: usare il processo appena discusso.
- **Actual**: "Quale processo vuoi aggiungere al progetto?"
- **Causa**: il router di ogni scope riceveva `latest_user_text(state)` e niente
  altro. Su "aggiungi il processo" letto da solo la risposta corretta *e'*
  chiedere quale: il referente era nel turno precedente, che il router non
  vedeva. In una chat operativa "aggiungilo", "approvalo", "usa quello",
  "correggi il secondo" sono la norma, e obbligano a ripetere nomi e id.

## PROJECT-05 — Workaround inventato nella UI

- **Severity**: P1 alto
- **Stato**: risolto (2026-09-07) — coperto da `tests/test_project_chat_boundaries.py`
- **Actual**: mancando la capability, DeliR suggeriva comandi dell'interfaccia
  ("Aggiungi processo", "Nuovo processo") che non esistono.
- **Causa**: nessuna regola diceva che l'interfaccia non e' materia su cui
  ipotizzare. Un limite dichiarato costa una frase; un pulsante inventato costa
  al consulente il tempo di cercarlo, e la fiducia nel resto della risposta.

### Fix

Tre cambiamenti, uno per livello.

*Il router legge la conversazione.* `recent_conversation_digest` in
`backend/graphs/common.py` passa ai quattro router (consulting, project,
process, canvas) le ultime battute umane e assistente — senza traffico dei tool,
che il router non deve instradare. Il prompt chiede di risolvere il referente e
di scriverlo in `entity_hints`; la clarification resta per l'ambiguita' vera,
non per il messaggio corto.

*Il progetto possiede i propri processi.* `create_project_process` in
`backend/graphs/project/tools.py` registra il record e il suo modello BPMN
vuoto, e si ferma li': niente discovery, niente XML, niente domande di
discovery nello stesso turno. E' idempotente per nome, e un perimetro
dichiarato diventa una fonte di progetto legata al processo invece di restare
nella chat (stessa lezione di PROJECT-01).

*Il runtime verifica cio' che e' verificabile.* Due prerequisiti nuovi in
`routing_contracts.py`: `existing_project_process` (coordinamento e delega
hanno bisogno di processi che esistano) e un `unambiguous_process_target` che
ora risolve l'hint *contro i processi registrati* — un nome che il progetto non
ha e' una richiesta di creazione, non un bersaglio di delega. Il rifiuto torna
al router con la ragione, che ridecide una volta.

Il resto e' prompt e skill: lo scope prompt dice cosa significa `process_count:
0`, vieta di inventare percorsi nell'interfaccia e chiede di risolvere i
riferimenti; `project_scope_governance.md` e `project_delegation_policy.md`
mettono la creazione del processo dalla parte del progetto e vietano la delega
usata per farsi creare un record.

### Verifica

`tests/test_project_chat_boundaries.py`: gate di routing (rifiuto con zero
processi, hint non registrato, delega sbloccata dopo la creazione), digest
(ordine, esclusione dei tool, budget), prompt di scope, e il tool su Postgres —
modello BPMN vuoto, perimetro salvato come fonte, idempotenza per nome.
