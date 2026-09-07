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

