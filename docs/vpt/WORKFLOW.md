# Engineering workflow del VPT

Regole vincolanti per chiunque lavori sul simulatore e sul Verified Process Twin,
persone o agenti. Obiettivo: il miglior prodotto sul mercato, costruito un punto
del piano alla volta, ognuno verificato prima di passare al successivo.

## I tre file

| File | Cosa contiene | Chi lo aggiorna e quando |
| --- | --- | --- |
| [`PLAN.md`](./PLAN.md) | i punti del piano: meta, comando di misura, dipendenze, stato | chi prende un punto (stato `in corso`) e chi lo chiude (`fatto`) |
| [`HANDOFF.md`](./HANDOFF.md) | **dove siamo adesso**: punto attivo, ultima misura, cosa resta, come riprendere | durante la sessione, a ogni checkpoint, e alla fine. Si riscrive, non si accoda |
| [`LOG.md`](./LOG.md) | la storia: una voce per sessione, la più recente in cima | alla fine di ogni sessione |

Chi arriva legge `HANDOFF.md` per primo: in un minuto deve sapere da dove ripartire.

## Il ciclo di un punto

1. **Inizio sessione**
   - leggi `HANDOFF.md`, poi `PLAN.md`, poi le ultime tre voci di `LOG.md`;
   - controlla i branch aperti rispetto a `main`: rivedi quello che c'è, mergia ciò che è pronto, segnala ciò che non lo è;
   - riallinea il tuo branch a `main`.
2. **Prendi un punto** con stato `da fare` e dipendenze chiuse. Mettilo `in corso`
   in `PLAN.md` e scrivi in `HANDOFF.md` chi lo sta facendo e da quando.
3. **Itera fino alla meta**
   - implementa a piccoli passi, un commit per passo;
   - dopo ogni tentativo lancia il comando di misura del punto;
   - scrivi il numero ottenuto in `HANDOFF.md`;
   - meta non raggiunta: diagnosi, correzione, nuova misura;
   - la meta non si abbassa per chiudere: cambiarla è una decisione di Sohayb, scritta in `LOG.md` con data e motivo.
4. **Checkpoint durante la sessione.** Aggiorna `HANDOFF.md` almeno dopo ogni
   misura, prima di un'operazione lunga e prima di fermarti per qualsiasi motivo.
   Se la sessione si interrompe, il prossimo riparte da lì senza ricostruire nulla.
5. **Verifica del punto**
   - **test:** i test del dominio toccato, più quelli nuovi che dimostrano la meta;
   - **gate UX:** se il punto tocca qualcosa che il cliente vede, vedi sotto;
   - **code review:** skill `code-review`, checklist, ast-grep e `simplify` (sezione sotto).
6. **Chiusura**
   - PR con tanti commit piccoli e la misura finale nel testo;
   - CI verde, poi merge su `main` e push;
   - il branch di lavoro resta allineato a `main`;
   - `PLAN.md` passa a `fatto`, `HANDOFF.md` riscritto per il prossimo, voce in cima a `LOG.md`;
   - poi la sessione si chiude e il prossimo prende il punto successivo.
   - **Una sessione, un punto.** A punto chiuso l'agente scrive a Sohayb un
     riassunto di 3-4 righe (cosa è cambiato, misura finale, PR, prossimo punto) e
     si ferma: non prende un altro punto. Il punto successivo parte in una sessione
     nuova, che riprende da `HANDOFF.md` con il contesto pulito.
7. **Bloccato?** Scrivi in `HANDOFF.md` e `LOG.md` cosa blocca e chi lo sblocca,
   metti il punto `bloccato` e passa a un altro.

Commit a nome di Sohayb Raqaq, senza trailer di coautore.

## Più agenti in parallelo

Si può lavorare su più punti insieme, uno per sessione, se non toccano gli stessi file.

- In `PLAN.md` ognuno modifica solo la riga del proprio punto.
- In `HANDOFF.md` ognuno tiene una sezione `## <punto>` sua: non riscrive il file
  intero e non tocca le sezioni degli altri. Chi chiude l'ultimo punto aperto
  ricompone il file.
- In `LOG.md` ognuno aggiunge solo la propria voce in cima.
- Prima della PR e prima del merge si mergia `origin/main` nel proprio branch e si
  risolvono i conflitti tenendo il lavoro degli altri.

## Stack reale: database e Prosimos, niente mock

Il simulatore si verifica sulla stessa pipeline del prodotto: Postgres con le
migrazioni di produzione e il runner Prosimos 2.1. Nelle sessioni cloud (senza
Docker) e su Linux:

```bash
scripts/vpt_stack.sh start           # Postgres 16 + migrazioni, runner su 127.0.0.1:5000
eval "$(scripts/vpt_stack.sh env)"   # URL dei database e del runner nella shell
uv run pytest tests/simulation       # la suite intera, con il database vero
scripts/vpt_stack.sh status          # cosa gira
scripts/vpt_stack.sh stop
```

- La prima volta installa `postgresql-16-pgvector` e crea il venv del runner
  (Python 3.12, Prosimos 2.1): circa un minuto. Dopo, l'avvio prende pochi secondi.
- Lo stato vive in `/var/tmp/delir-vpt-stack` (`VPT_STACK_DIR` per cambiarlo); le
  password sono quelle di test della CI e lo stack ascolta solo su `127.0.0.1`.
- I test che usano Prosimos direttamente girano nel venv del runner:
  `/var/tmp/delir-vpt-stack/runner-venv/bin/python -m pytest --noconftest tests/simulation/test_simulation_ir_engine.py`.
- Una misura del simulatore (B2 e successivi) si fa su questo stack, non su un
  motore finto.

## Skill e code review

- **Skill giuste, ogni volta.** Prima di lavorare carica le skill che `CLAUDE.md`
  indica per quel tipo di lavoro, e solo quelle:

  | Lavoro | Skill |
  | --- | --- |
  | schermata nuova o flusso | `ui-ux-pro-max`, `frontend-developer`, `react-ui-patterns`, `tailwind-design-system` |
  | componente o stato React | `react-ui-patterns`, `react-best-practices`, `react-state-management` (`zustand-store-ts` se tocca uno store) |
  | canvas BPMN | `react-flow-node-ts`, `react-ui-patterns`, `ui-ux-designer` |
  | gate UX e chiusura di un punto con UI | `ui-visual-validator`, `web-design-guidelines`, `accessibility-compliance-accessibility-audit` |
  | grafici e dashboard dei risultati | `dataviz` |
  | backend, simulazione, ricerca | nessuna skill di frontend; per l'API dei modelli `claude-api` |

  Scrivi in `LOG.md` quali skill hai usato.
- **Code review sempre, prima del merge.** La fa chi chiude il punto, sul diff
  completo rispetto a `main`, e la scrive nella PR:
  1. skill `code-review` sul diff (correttezza e regole di `CLAUDE.md`), poi
     rileggi ogni file come un revisore esigente: casi limite, errori gestiti,
     test che dimostrano la meta, nessun codice morto;
  2. per il backend applica la checklist di `backend/CODE_QUALITY.md` e lancia le
     regole ast-grep (`.ast-grep-rules/README.md`); due sono già bloccanti in CI;
  3. skill `simplify` sul diff per riuso, semplicità ed efficienza;
  4. skill `security-review` se il punto tocca autenticazione, sicurezza o
     isolamento fra clienti;
  5. ogni rilievo si corregge o si motiva nella PR. Nessun merge con rilievi aperti.

## Regola di prodotto: mangiare la complessità del cliente

Il motore è complesso; il prodotto no. Chi lo usa è un consulente o un'azienda,
spesso con formazione tecnica ma senza il gergo della simulazione e del process
mining. DeliR assorbe la complessità dei dati e degli strumenti del cliente: il
consulente pensa al problema e alla decisione, mai all'interfaccia.

- **I componenti ci sono già: il lavoro è su come si leggono le cose.** Non si
  creano componenti nuovi per un punto del piano; si usano quelli del design
  system. Si lavora su parole, etichette, ordine, raggruppamento, unità, numeri
  arrotondati in modo leggibile, spiegazioni accanto al dato e stati vuoti.
- **Linguaggio di business.** Il percorso ordinario parla di casi, tempi, persone,
  costi, rischi e decisioni. Termini come distribuzione lognormale, seed, gateway,
  ID BPMN, JSON, W1, NGD compaiono solo nei dettagli per specialisti, aperti su
  richiesta, e accanto a una spiegazione in parole semplici.
- **Prima la risposta, poi i dettagli.** Ogni schermata dice cosa abbiamo letto,
  cosa è cambiato e cosa serve decidere. La precisione completa resta disponibile,
  un livello sotto.
- **Il percorso normale è automatico.** Se DeliR può proporre un valore, lo propone
  con la fonte; il consulente approva, modifica o rifiuta.
- **Gli errori dicono cosa fare.** Mai un import parziale silenzioso: si spiega la
  parte non supportata e lo scenario resta com'era.
- **Prova del consulente.** Prima di chiudere un punto con UI, un consulente non
  tecnico deve poter completare il flusso con un file realistico senza decodificare
  nulla. Se servono spiegazioni a voce, il punto non è finito.

## Gate UX: guardare il prodotto

Ogni punto che cambia ciò che il cliente vede si chiude solo dopo averlo guardato
davvero, non solo testato.

1. Cattura gli screenshot del flusso con Playwright (gli e2e in `e2e/` simulano il
   backend, quindi basta il frontend): desktop 1440 × 900 e mobile (Pixel 7).
2. **Apri ogni immagine e leggila**, testo compreso. Controlla:
   - le parole che il cliente legge: niente gergo nel percorso ordinario;
   - la gerarchia: la risposta e l'azione principale si vedono per prime;
   - testo tagliato, sovrapposizioni, scroll orizzontale, stati vuoti ed errori;
   - focus visibile e navigazione da tastiera (axe, già usato negli e2e);
   - che sembri un prodotto enterprise, non una demo.
3. Salva le immagini in `docs/vpt/ux/<punto>/` (prima e dopo, se è un cambiamento)
   e scrivi in `LOG.md` cosa hai controllato e cosa hai corretto.
4. Se una schermata non passa, il punto torna al passo 3 del ciclo.

Le skill locali per questo lavoro sono elencate in `CLAUDE.md` (UI/UX, accessibilità,
visual QA).
